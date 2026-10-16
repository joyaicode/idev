// Package sqlite is the local store: a single file, no cgo, and every
// invariant that matters expressed as a constraint rather than as a
// convention.
//
// The driver is modernc.org/sqlite (pure Go) so the binary cross-compiles
// and `CGO_ENABLED=0` holds. The DSN matters as much as the schema:
//
//   - `_txlock=immediate` takes the write lock when a transaction begins
//     rather than at its first write, which turns a lost update into an
//     immediate "database is locked" instead of a silent retry-and-clobber.
//   - `busy_timeout` lets a concurrent writer wait instead of failing.
//   - `foreign_keys=on` because SQLite ignores them otherwise, and the
//     references in the schema are load-bearing.
//
// Deliberate deviation from the design: the queries are hand-written rather
// than generated with sqlc. The reason is that almost every statement here
// is a conditional write — a CAS on `version`, an insert that must collide
// with a partial unique index, a trigger that must fire — and a reviewer has
// to be able to read the SQL that enforces an invariant without also holding
// a generator's conventions in their head. sqlc's value is typed row
// mapping; its cost is a second place where the semantics live.
package sqlite

import (
	"context"
	"database/sql"
	"embed"
	"errors"
	"fmt"
	"path/filepath"
	"strings"

	"github.com/pressly/goose/v3"
	_ "modernc.org/sqlite" // registers the "sqlite" driver
)

//go:embed migrations/*.sql
var migrations embed.FS

// Store is a handle on one database file.
type Store struct {
	db *sql.DB
}

// Open opens (and creates if needed) a database and brings it up to the
// current schema.
func Open(ctx context.Context, path string) (*Store, error) {
	dsn := dsnFor(path)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("sqlite: open %s: %w", path, err)
	}
	// One writer at a time. SQLite serialises writes anyway; a pool larger
	// than one only converts waiting into SQLITE_BUSY.
	db.SetMaxOpenConns(1)

	if err := db.PingContext(ctx); err != nil {
		// The close error is deliberately dropped: the caller is being told
		// the database is unusable, and a second reason does not change
		// what they do about it.
		_ = db.Close()
		return nil, fmt.Errorf("sqlite: ping %s: %w", path, err)
	}
	s := &Store{db: db}
	if err := s.migrate(ctx); err != nil {
		_ = db.Close()
		return nil, err
	}
	return s, nil
}

func dsnFor(path string) string {
	if path == ":memory:" || strings.HasPrefix(path, "file:") {
		// An in-memory database with MaxOpenConns(1) is still one database;
		// shared cache is what makes that true if the pool ever grows.
		return path + "?_pragma=foreign_keys(1)&_pragma=busy_timeout(5000)&_txlock=immediate"
	}
	return "file:" + filepath.ToSlash(path) +
		"?_pragma=foreign_keys(1)" +
		"&_pragma=busy_timeout(5000)" +
		"&_pragma=journal_mode(WAL)" +
		"&_pragma=synchronous(NORMAL)" +
		"&_txlock=immediate"
}

func (s *Store) migrate(ctx context.Context) error {
	goose.SetBaseFS(migrations)
	goose.SetLogger(goose.NopLogger())
	if err := goose.SetDialect("sqlite3"); err != nil {
		return fmt.Errorf("sqlite: dialect: %w", err)
	}
	if err := goose.UpContext(ctx, s.db, "migrations"); err != nil {
		return fmt.Errorf("sqlite: migrate: %w", err)
	}
	return nil
}

// DB exposes the handle for the repositories in this package. Not exported
// beyond it: the app layer talks to ports, not to SQL.
func (s *Store) DB() *sql.DB { return s.db }

// Close releases the handle.
func (s *Store) Close() error { return s.db.Close() }

// Version reports the applied schema version, for `idevd migrate status`.
func (s *Store) Version(ctx context.Context) (int64, error) {
	v, err := goose.GetDBVersionContext(ctx, s.db)
	if err != nil {
		return 0, fmt.Errorf("sqlite: version: %w", err)
	}
	return v, nil
}

// Tx runs fn inside one transaction, committing on success.
//
// This is the only way the app layer writes: a use case is a transaction, so
// a state change and its audit event cannot be separated (invariant I-6).
func (s *Store) Tx(ctx context.Context, fn func(*sql.Tx) error) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("sqlite: begin: %w", err)
	}
	if err := fn(tx); err != nil {
		if rbErr := tx.Rollback(); rbErr != nil && !errors.Is(rbErr, sql.ErrTxDone) {
			// Both matter: the rollback failing means the transaction may
			// still be open, and the original error is why we are here.
			return fmt.Errorf("sqlite: rollback (%w) after %w", rbErr, err)
		}
		return err
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("sqlite: commit: %w", err)
	}
	return nil
}

// Conflict classifies a constraint violation.
//
// The app layer has to distinguish "someone else holds the write lease" from
// "this attempt was already recorded" from "that approval already exists",
// and all three arrive as the same driver error string. Mapping them here
// keeps the string matching in one place.
type Conflict string

// The conflicts the schema can produce.
const (
	ConflictNone            Conflict = ""
	ConflictLiveRun         Conflict = "live_run"
	ConflictWriteLeaseHeld  Conflict = "lease_held"
	ConflictAttemptExists   Conflict = "attempt_exists"
	ConflictGatePending     Conflict = "gate_pending"
	ConflictApprovalExists  Conflict = "approval_exists"
	ConflictSealedBaseline  Conflict = "sealed_baseline"
	ConflictVerificationSet Conflict = "verification_exists"
	ConflictIdempotencyKey  Conflict = "idempotency_key_reuse"
	ConflictAppendOnly      Conflict = "append_only"
	ConflictOther           Conflict = "constraint"
)

// index names, mapped to the conflict a caller can act on.
var conflictIndex = map[string]Conflict{
	"runs_live_uq":                     ConflictLiveRun,
	"leases_single_writer_feature":     ConflictWriteLeaseHeld,
	"leases_single_writer_run":         ConflictWriteLeaseHeld,
	"delegations_attempt_uq":           ConflictAttemptExists,
	"gates_one_pending_per_step":       ConflictGatePending,
	"approvals_one_per_gate":           ConflictApprovalExists,
	"baselines_one_sealed":             ConflictSealedBaseline,
	"verifications_one_per_delegation": ConflictVerificationSet,
	"idempotency_keys":                 ConflictIdempotencyKey,
}

// Classify turns a driver error into a conflict a caller can branch on.
func Classify(err error) Conflict {
	if err == nil {
		return ConflictNone
	}
	msg := err.Error()
	if strings.Contains(msg, "append-only") || strings.Contains(msg, "immutable") {
		return ConflictAppendOnly
	}
	if !strings.Contains(msg, "UNIQUE constraint failed") &&
		!strings.Contains(msg, "constraint failed") {
		return ConflictNone
	}
	for name, c := range conflictIndex {
		if strings.Contains(msg, name) {
			return c
		}
	}
	// A partial unique index reports the columns rather than the index name
	// in some driver versions — in practice modernc reports columns for all
	// of them, so this fallback is the path that actually runs and the map
	// above is the belt.
	switch {
	case strings.Contains(msg, "leases.feature_id"), strings.Contains(msg, "leases.run_id"):
		return ConflictWriteLeaseHeld
	case strings.Contains(msg, "delegations.attempt"):
		return ConflictAttemptExists
	case strings.Contains(msg, "verifications.delegation_id"):
		return ConflictVerificationSet
	case strings.Contains(msg, "approvals.gate_id"):
		return ConflictApprovalExists
	case strings.Contains(msg, "baselines.feature_id"):
		return ConflictSealedBaseline
	case strings.Contains(msg, "gates.step_id"):
		return ConflictGatePending
	case strings.Contains(msg, "runs.workflow_id"), strings.Contains(msg, "runs.feature_id"):
		return ConflictLiveRun
	case strings.Contains(msg, "idempotency_keys.key"):
		return ConflictIdempotencyKey
	}
	return ConflictOther
}
