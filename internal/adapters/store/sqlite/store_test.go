package sqlite_test

import (
	"context"
	"database/sql"
	"errors"
	"path/filepath"
	"testing"

	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/adapters/store/storetest"
)

// The shared suite. P4's Postgres adapter runs the same one: the invariants
// belong to the schema, so an adapter that passes a different suite proves
// nothing about what this one was protecting.
func TestConsistencySuite(t *testing.T) {
	storetest.Run(t, openFresh, func(err error) string {
		return string(sqlite.Classify(err))
	})
}

func openFresh(t *testing.T) *sql.DB {
	t.Helper()
	// A file rather than :memory: — the suite runs concurrent writers, and
	// the locking behaviour under test is the file-backed one.
	path := filepath.Join(t.TempDir(), "idev.db")
	s, err := sqlite.Open(context.Background(), path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() {
		if err := s.Close(); err != nil {
			t.Errorf("close: %v", err)
		}
	})
	return s.DB()
}

func TestMigrationsApplyAndReportAVersion(t *testing.T) {
	path := filepath.Join(t.TempDir(), "idev.db")
	s, err := sqlite.Open(context.Background(), path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	t.Cleanup(func() {
		if err := s.Close(); err != nil {
			t.Errorf("close: %v", err)
		}
	})

	v, err := s.Version(context.Background())
	if err != nil {
		t.Fatalf("version: %v", err)
	}
	if v < 1 {
		t.Fatalf("schema version = %d, want at least 1", v)
	}
}

func TestOpeningTwiceIsIdempotent(t *testing.T) {
	// Starting idevd twice against the same file must not re-run migrations
	// or fail. The second open also has to report the version: skipping the
	// migration write must not skip the dialect goose needs to read it.
	path := filepath.Join(t.TempDir(), "idev.db")
	var first int64
	for i := 0; i < 2; i++ {
		s, err := sqlite.Open(context.Background(), path)
		if err != nil {
			t.Fatalf("open %d: %v", i, err)
		}
		v, err := s.Version(context.Background())
		if err != nil {
			t.Fatalf("version %d: %v", i, err)
		}
		if i == 0 {
			first = v
		} else if v != first {
			t.Fatalf("reopen version = %d, first open = %d", v, first)
		}
		if err := s.Close(); err != nil {
			t.Fatal(err)
		}
	}
}

func TestAStaleSchemaIsStillMigrated(t *testing.T) {
	// Skipping Up is only safe when the recorded version already matches.
	// An older version has to apply what it missed.
	path := filepath.Join(t.TempDir(), "idev.db")
	s, err := sqlite.Open(context.Background(), path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if _, err := s.DB().Exec(`DROP TABLE gate_subjects`); err != nil {
		t.Fatal(err)
	}
	if _, err := s.DB().Exec(`DELETE FROM goose_db_version WHERE version_id >= 2`); err != nil {
		t.Fatal(err)
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s, err = sqlite.Open(context.Background(), path)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	t.Cleanup(func() {
		if err := s.Close(); err != nil {
			t.Errorf("close: %v", err)
		}
	})
	var n int
	if err := s.DB().QueryRow(`SELECT COUNT(*) FROM sqlite_master WHERE name = 'gate_subjects'`).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatal("gate_subjects was not recreated from the pending migration")
	}
	v, err := s.Version(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if v < 2 {
		t.Fatalf("version = %d, want at least 2", v)
	}
}

func TestForeignKeysAreOn(t *testing.T) {
	// SQLite ignores foreign keys unless asked, and the references in the
	// schema are load-bearing: a run pointing at no feature is a run nobody
	// can resolve a ticket directory for.
	db := openFresh(t)
	_, err := db.Exec(`INSERT INTO runs
		(id, workflow_id, feature_id, status, started_at, created_at)
		VALUES ('r', 'lite-change', 'no-such-feature', 'running', '2026-10-16T00:00:00Z', '2026-10-16T00:00:00Z')`)
	if err == nil {
		t.Fatal("a run referencing a missing feature was accepted; foreign keys are off")
	}
}

func TestStrictTypesAreEnforced(t *testing.T) {
	// STRICT tables turn a type mistake into an error instead of a silently
	// coerced value. `attempt: "很多"` is the kind of thing that reached the
	// Python ledgers.
	db := openFresh(t)
	_, err := db.Exec(`INSERT INTO features
		(id, workspace, feature_key, stage, risk_tier, revision, created_at, updated_at)
		VALUES ('f', 'w', 'demo', 'code', 'P1', 'many', '2026-10-16T00:00:00Z', '2026-10-16T00:00:00Z')`)
	if err == nil {
		t.Fatal("a text revision was stored in an integer column")
	}
}

func TestTxRollsBackOnError(t *testing.T) {
	path := filepath.Join(t.TempDir(), "idev.db")
	s, err := sqlite.Open(context.Background(), path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := s.Close(); err != nil {
			t.Errorf("close: %v", err)
		}
	})

	sentinel := context.Canceled
	err = s.Tx(context.Background(), func(tx *sql.Tx) error {
		if _, err := tx.Exec(`INSERT INTO features
			(id, workspace, feature_key, stage, risk_tier, revision, created_at, updated_at)
			VALUES ('f', 'w', 'demo', 'code', 'P1', 1, '2026-10-16T00:00:00Z', '2026-10-16T00:00:00Z')`); err != nil {
			return err
		}
		return sentinel
	})
	if !errors.Is(err, sentinel) {
		t.Fatalf("Tx error = %v, want the callback's error", err)
	}

	// A use case is a transaction, so a half-applied change is exactly what
	// must not survive: the state change and its audit event go together.
	var count int
	if err := s.DB().QueryRow(`SELECT COUNT(*) FROM features`).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 0 {
		t.Errorf("%d rows survived a rolled-back transaction", count)
	}
}

func TestTxCommitsOnSuccess(t *testing.T) {
	path := filepath.Join(t.TempDir(), "idev.db")
	s, err := sqlite.Open(context.Background(), path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := s.Close(); err != nil {
			t.Errorf("close: %v", err)
		}
	})

	if err := s.Tx(context.Background(), func(tx *sql.Tx) error {
		_, err := tx.Exec(`INSERT INTO features
			(id, workspace, feature_key, stage, risk_tier, revision, created_at, updated_at)
			VALUES ('f', 'w', 'demo', 'code', 'P1', 1, '2026-10-16T00:00:00Z', '2026-10-16T00:00:00Z')`)
		return err
	}); err != nil {
		t.Fatalf("Tx: %v", err)
	}
	var count int
	if err := s.DB().QueryRow(`SELECT COUNT(*) FROM features`).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Errorf("%d rows after a committed transaction, want 1", count)
	}
}

func TestClassifyDistinguishesConflicts(t *testing.T) {
	if got := sqlite.Classify(nil); got != sqlite.ConflictNone {
		t.Errorf("Classify(nil) = %q, want none", got)
	}
	if got := sqlite.Classify(context.Canceled); got != sqlite.ConflictNone {
		t.Errorf("Classify of an unrelated error = %q, want none", got)
	}
}

func TestOpenRefusesAnUnusablePath(t *testing.T) {
	// A directory that does not exist is a configuration problem worth
	// reporting at startup rather than at the first write.
	_, err := sqlite.Open(context.Background(), filepath.Join(t.TempDir(), "nope", "idev.db"))
	if err == nil {
		t.Error("Open accepted a path it cannot create")
	}
}
