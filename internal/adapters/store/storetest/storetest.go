// Package storetest is the consistency suite every store adapter must pass.
//
// One suite, two adapters: SQLite now, PostgreSQL in P4. The point is that
// the invariants are properties of the *schema*, not of whichever engine is
// underneath, so the same assertions have to hold for both. A Postgres
// adapter that passes a different test suite proves nothing about the thing
// the SQLite one was protecting.
//
// What it tests is deliberately narrow: constraints and concurrency. Every
// case here corresponds to a review finding where two writers raced and the
// second won silently, or to an invariant the design states (I-1, I-3, I-5,
// I-6). Business logic is tested in internal/domain, against no database at
// all.
package storetest

import (
	"context"
	"database/sql"
	"fmt"
	"sync"
	"testing"
	"time"
)

// Opener hands the suite a migrated, empty database.
type Opener func(t *testing.T) *sql.DB

// Classifier maps a driver error to a stable name, so the suite can assert
// which constraint fired rather than matching engine-specific strings.
type Classifier func(error) string

// Run executes the whole suite.
func Run(t *testing.T, open Opener, classify Classifier) {
	t.Helper()
	cases := []struct {
		name string
		fn   func(*testing.T, Opener, Classifier)
	}{
		{"one live run per feature and workflow", testOneLiveRun},
		{"one write lease per feature", testSingleWriter},
		{"one write lease across two runs of a feature", testSingleWriterAcrossRuns},
		{"one write lease per run when no feature is set", testSingleWriterUnboundRun},
		{"one verification per delegation", testOneVerification},
		{"a delegation attempt cannot be rewritten", testAttemptIsUnique},
		{"one pending gate per step", testOnePendingGate},
		{"one approval per gate", testOneApprovalPerGate},
		{"only a human can be an approver", testApproverMustBeHuman},
		{"approvals are immutable", testApprovalsImmutable},
		{"audit events are append-only", testAuditAppendOnly},
		{"one sealed baseline per feature", testOneSealedBaseline},
		{"a run advances by compare-and-swap", testVersionCAS},
		{"ten concurrent delegations yield one winner", testConcurrentDelegations},
		{"ten concurrent write leases yield one holder", testConcurrentLeases},
		{"a released lease frees the slot", testLeaseReleaseFreesSlot},
		{"an aborted run frees the slot", testAbortedRunFreesSlot},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) { tc.fn(t, open, classify) })
	}
}

// --- fixtures --------------------------------------------------------------

const (
	featureID = "01FEATURE0000000000000000A"
	runID     = "01RUN000000000000000000000"
	altRunID  = "01RUN000000000000000000001"
	gateID    = "01GATE00000000000000000000"
	baseA     = "01BASE00000000000000000000"
	baseB     = "01BASE00000000000000000001"
)

func now() string { return time.Now().UTC().Format(time.RFC3339Nano) }

func exec(t *testing.T, db *sql.DB, q string, args ...any) {
	t.Helper()
	if _, err := db.ExecContext(context.Background(), q, args...); err != nil {
		t.Fatalf("exec: %v\n%s", err, q)
	}
}

func tryExec(db *sql.DB, q string, args ...any) error {
	_, err := db.ExecContext(context.Background(), q, args...)
	return err
}

func seedFeature(t *testing.T, db *sql.DB) {
	t.Helper()
	exec(t, db, `INSERT INTO features
		(id, workspace, feature_key, stage, risk_tier, revision, created_at, updated_at)
		VALUES (?, 'w', 'demo', 'code', 'P1', 1, ?, ?)`, featureID, now(), now())
}

func seedRun(t *testing.T, db *sql.DB, id, workflow, status string) {
	t.Helper()
	exec(t, db, `INSERT INTO runs
		(id, workflow_id, feature_id, status, started_at, created_at)
		VALUES (?, ?, ?, ?, ?, ?)`, id, workflow, featureID, status, now(), now())
}

func insertRun(db *sql.DB, id, workflow, status string) error {
	return tryExec(db, `INSERT INTO runs
		(id, workflow_id, feature_id, status, started_at, created_at)
		VALUES (?, ?, ?, ?, ?, ?)`, id, workflow, featureID, status, now(), now())
}

func insertWriteLease(db *sql.DB, id, agent, status string) error {
	return tryExec(db, `INSERT INTO leases
		(id, purpose, feature_id, run_id, step_id, agent, token_sha256,
		 fencing_token, status, issued_at, expires_at)
		VALUES (?, 'write', ?, ?, 'code-pass', ?, 'h', 1, ?, ?, ?)`,
		id, featureID, runID, agent, status, now(),
		time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano))
}

// insertWriteLeaseFor is insertWriteLease with the run named, so a test can
// put two leases on one feature through two different runs.
func insertWriteLeaseFor(db *sql.DB, id, run, agent string) error {
	return tryExec(db, `INSERT INTO leases
		(id, purpose, feature_id, run_id, step_id, agent, token_sha256,
		 fencing_token, status, issued_at, expires_at)
		VALUES (?, 'write', ?, ?, 'code-pass', ?, 'h', 1, 'active', ?, ?)`,
		id, featureID, run, agent, now(),
		time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano))
}

func insertDelegation(db *sql.DB, id, step string, attempt int) error {
	return tryExec(db, `INSERT INTO delegations
		(id, run_id, step_id, attempt, agent, packet_json, state, issued_at)
		VALUES (?, ?, ?, ?, 'idev-coder', '{}', 'issued', ?)`,
		id, runID, step, attempt, now())
}

func insertGate(db *sql.DB, id, step, status string) error {
	return tryExec(db, `INSERT INTO gates
		(id, gate_type, run_id, step_id, feature_id, risk_tier, subject_kind,
		 subject_digest, required_assurance, status, created_at, expires_at)
		VALUES (?, 'sealed', ?, ?, ?, 'P1', 'baseline', 'sha256:a', 'high', ?, ?, ?)`,
		id, runID, step, featureID, status, now(),
		time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano))
}

func insertApproval(db *sql.DB, id, gate, kind string) error {
	return tryExec(db, `INSERT INTO approvals
		(id, gate_id, gate_type, decision, subject_digest, approver_handle,
		 approver_kind, assurance, quote, signature_json, decided_at)
		VALUES (?, ?, 'sealed', 'approve', 'sha256:a', 'wangwei794', ?, 'high', '确认', '{}', ?)`,
		id, gate, kind, now())
}

func insertBaseline(db *sql.DB, id string, revision int, status string) error {
	return tryExec(db, `INSERT INTO baselines
		(id, feature_id, revision, status, manifest_json, manifest_root, raw_root, created_at)
		VALUES (?, ?, ?, ?, '{}', 'sha256:a', 'sha256:b', ?)`,
		id, featureID, revision, status, now())
}

func insertAudit(t *testing.T, db *sql.DB, seq int, prev, hash string) {
	t.Helper()
	exec(t, db, `INSERT INTO audit_events
		(seq, at, action, actor_handle, actor_kind, prev_hash, hash)
		VALUES (?, ?, 'run.started', 'wangwei794', 'human', ?, ?)`,
		seq, now(), prev, hash)
}

func mustConflict(t *testing.T, classify Classifier, err error, want string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected %s, the write succeeded", want)
	}
	if got := classify(err); got != want {
		t.Fatalf("conflict = %q, want %q (error: %v)", got, want, err)
	}
}

// --- constraints -----------------------------------------------------------

func testOneLiveRun(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")

	// `workflow.py` read the file, saw a live run and refused — with nothing
	// preventing a second start between the read and the write.
	mustConflict(t, classify, insertRun(db, altRunID, "lite-change", "running"), "live_run")

	// A different workflow on the same feature is fine.
	if err := insertRun(db, altRunID, "dev-selftest", "running"); err != nil {
		t.Errorf("a second workflow on the same feature must be allowed: %v", err)
	}
}

func testSingleWriter(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")

	if err := insertWriteLease(db, "l-1", "idev-coder", "active"); err != nil {
		t.Fatalf("the first write lease must be granted: %v", err)
	}
	// Invariant I-1.
	mustConflict(t, classify, insertWriteLease(db, "l-2", "idev-verifier", "active"), "lease_held")

	// A verify lease alongside it is the normal case.
	err := tryExec(db, `INSERT INTO leases
		(id, purpose, feature_id, run_id, step_id, agent, token_sha256,
		 fencing_token, status, issued_at, expires_at)
		VALUES ('l-3', 'verify', ?, ?, 'plan', 'idev-verifier', 'h', 2, 'active', ?, ?)`,
		featureID, runID, now(), time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano))
	if err != nil {
		t.Errorf("a verify lease must coexist with a write lease: %v", err)
	}
}

func testSingleWriterAcrossRuns(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	// A feature may legitimately have two live runs, as long as they are
	// different workflows (runs_live_uq allows it). Both wanting to write
	// the same product code is exactly what I-1 forbids.
	seedRun(t, db, runID, "lite-change", "running")
	seedRun(t, db, altRunID, "dev-selftest", "running")

	if err := insertWriteLeaseFor(db, "l-1", runID, "idev-coder"); err != nil {
		t.Fatalf("the first write lease must be granted: %v", err)
	}
	// This is the case the run-scoped index cannot see: different run, same
	// feature. Removing leases_single_writer_feature makes only this test
	// fail, which is how the gap in the suite was found.
	mustConflict(t, classify,
		insertWriteLeaseFor(db, "l-2", altRunID, "idev-verifier"), "lease_held")
}

func testSingleWriterUnboundRun(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")

	// The feature-scoped index is conditional on feature_id being set, so a
	// lease with no feature falls through it. The run-scoped index is the
	// only thing left, and without this case removing it changed nothing in
	// the suite — which is how this gap was found.
	insert := func(id string) error {
		return tryExec(db, `INSERT INTO leases
			(id, purpose, feature_id, run_id, step_id, agent, token_sha256,
			 fencing_token, status, issued_at, expires_at)
			VALUES (?, 'write', NULL, ?, 'code-pass', 'idev-coder', 'h', 1, 'active', ?, ?)`,
			id, runID, now(), time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano))
	}
	if err := insert("l-1"); err != nil {
		t.Fatalf("a write lease with no feature must still be grantable: %v", err)
	}
	mustConflict(t, classify, insert("l-2"), "lease_held")
}

func testOneVerification(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")
	if err := insertDelegation(db, "d-1", "code-pass", 1); err != nil {
		t.Fatal(err)
	}

	insert := func(id, verifier, verdict string) error {
		return tryExec(db, `INSERT INTO verifications
			(id, delegation_id, verifier, verdict, at)
			VALUES (?, 'd-1', ?, ?, ?)`, id, verifier, verdict, now())
	}
	if err := insert("v-1", "idev-reviewer", "PASS"); err != nil {
		t.Fatalf("the first verification must be recorded: %v", err)
	}
	// Two verdicts on one delegation would let a caller pick the one it
	// prefers — which is the same failure as asking a gate twice.
	mustConflict(t, classify, insert("v-2", "idev-verifier", "FAIL"), "verification_exists")
}

func testAttemptIsUnique(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")

	if err := insertDelegation(db, "d-1", "code-pass", 1); err != nil {
		t.Fatalf("the first delegation must be recorded: %v", err)
	}
	// Invariant I-5: the old code replaced the record and reported OK.
	mustConflict(t, classify, insertDelegation(db, "d-2", "code-pass", 1), "attempt_exists")

	// A retry is a new attempt, not a rewrite.
	if err := insertDelegation(db, "d-3", "code-pass", 2); err != nil {
		t.Errorf("attempt 2 must be recordable: %v", err)
	}
}

func testOnePendingGate(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "awaiting_human")

	if err := insertGate(db, gateID, "gate-plan", "pending"); err != nil {
		t.Fatalf("the first gate must be opened: %v", err)
	}
	// Asking twice would let the conductor apply whichever answer it likes.
	mustConflict(t, classify, insertGate(db, "01GATE00000000000000000001", "gate-plan", "pending"),
		"gate_pending")

	// Once withdrawn, the question can be asked again.
	exec(t, db, `UPDATE gates SET status = 'withdrawn' WHERE id = ?`, gateID)
	if err := insertGate(db, "01GATE00000000000000000002", "gate-plan", "pending"); err != nil {
		t.Errorf("a withdrawn gate must free the slot: %v", err)
	}
}

func testOneApprovalPerGate(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "awaiting_human")
	if err := insertGate(db, gateID, "gate-plan", "pending"); err != nil {
		t.Fatal(err)
	}

	if err := insertApproval(db, "01APPROVAL000000000000000", gateID, "human"); err != nil {
		t.Fatalf("the first approval must be recorded: %v", err)
	}
	// Threat T6: replaying an approval against the same gate.
	mustConflict(t, classify,
		insertApproval(db, "01APPROVAL000000000000001", gateID, "human"), "approval_exists")
}

func testApproverMustBeHuman(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "awaiting_human")
	if err := insertGate(db, gateID, "gate-plan", "pending"); err != nil {
		t.Fatal(err)
	}

	// Invariant I-3 at the storage layer. The domain refuses this, RBAC
	// refuses this, and so does the table — three independent layers,
	// because a single layer is one mistake away from not refusing.
	for _, kind := range []string{"agent", "service"} {
		err := insertApproval(db, "01APPROVAL00000000000000"+kind[:1], gateID, kind)
		if err == nil {
			t.Fatalf("an approval by a %s was stored", kind)
		}
	}
}

func testApprovalsImmutable(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "awaiting_human")
	if err := insertGate(db, gateID, "gate-plan", "pending"); err != nil {
		t.Fatal(err)
	}
	id := "01APPROVAL000000000000000"
	if err := insertApproval(db, id, gateID, "human"); err != nil {
		t.Fatal(err)
	}

	// Editing a record of what a person said is not a correction.
	mustConflict(t, classify,
		tryExec(db, `UPDATE approvals SET quote = '驳回' WHERE id = ?`, id), "append_only")
	mustConflict(t, classify,
		tryExec(db, `DELETE FROM approvals WHERE id = ?`, id), "append_only")

	var quote string
	if err := db.QueryRow(`SELECT quote FROM approvals WHERE id = ?`, id).Scan(&quote); err != nil {
		t.Fatal(err)
	}
	if quote != "确认" {
		t.Errorf("quote = %q; the refused update changed it anyway", quote)
	}
}

func testAuditAppendOnly(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	insertAudit(t, db, 1, "sha256:0", "sha256:a")

	// Invariant I-6's second defence. The hash chain detects tampering
	// afterwards; this refuses the easy case outright.
	mustConflict(t, classify,
		tryExec(db, `UPDATE audit_events SET actor_handle = 'someone' WHERE seq = 1`), "append_only")
	mustConflict(t, classify,
		tryExec(db, `DELETE FROM audit_events WHERE seq = 1`), "append_only")

	var handle string
	if err := db.QueryRow(`SELECT actor_handle FROM audit_events WHERE seq = 1`).Scan(&handle); err != nil {
		t.Fatal(err)
	}
	if handle != "wangwei794" {
		t.Errorf("actor = %q; the refused update changed it anyway", handle)
	}
}

func testOneSealedBaseline(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)

	if err := insertBaseline(db, baseA, 1, "sealed"); err != nil {
		t.Fatalf("the first sealed baseline must be stored: %v", err)
	}
	// Two sealed baselines would make "what was agreed" ambiguous.
	mustConflict(t, classify, insertBaseline(db, baseB, 2, "sealed"), "sealed_baseline")

	// A draft alongside a sealed one is the reopen path.
	if err := insertBaseline(db, baseB, 2, "draft"); err != nil {
		t.Errorf("a draft revision must be allowed: %v", err)
	}
}

func testVersionCAS(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")

	// A writer that read version 1 may write version 2.
	res, err := db.Exec(
		`UPDATE runs SET status = 'blocked', version = version + 1 WHERE id = ? AND version = 1`, runID)
	if err != nil {
		t.Fatal(err)
	}
	if n, _ := res.RowsAffected(); n != 1 {
		t.Fatalf("the first writer updated %d rows, want 1", n)
	}

	// A second writer that also read version 1 updates nothing, rather than
	// overwriting the first one's decision.
	res, err = db.Exec(
		`UPDATE runs SET status = 'done', version = version + 1 WHERE id = ? AND version = 1`, runID)
	if err != nil {
		t.Fatal(err)
	}
	if n, _ := res.RowsAffected(); n != 0 {
		t.Fatalf("a stale writer updated %d rows; it should have lost the race", n)
	}

	var status string
	if err := db.QueryRow(`SELECT status FROM runs WHERE id = ?`, runID).Scan(&status); err != nil {
		t.Fatal(err)
	}
	if status != "blocked" {
		t.Errorf("status = %q, want blocked: the stale writer won", status)
	}
}

// --- concurrency -----------------------------------------------------------

func testConcurrentDelegations(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")

	// The design's acceptance criterion: ten goroutines issuing the same
	// step's delegation produce exactly one winner.
	const n = 10
	var wg sync.WaitGroup
	results := make([]error, n)
	start := make(chan struct{})
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			<-start
			results[i] = insertDelegation(db, fmt.Sprintf("d-%02d", i), "code-pass", 1)
		}(i)
	}
	close(start)
	wg.Wait()

	won, lost := 0, 0
	for _, err := range results {
		switch {
		case err == nil:
			won++
		case classify(err) == "attempt_exists":
			lost++
		default:
			t.Errorf("unexpected failure: %v", err)
		}
	}
	if won != 1 || lost != n-1 {
		t.Fatalf("%d won and %d were refused, want 1 and %d", won, lost, n-1)
	}

	var count int
	if err := db.QueryRow(
		`SELECT COUNT(*) FROM delegations WHERE run_id = ? AND step_id = 'code-pass'`,
		runID).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Errorf("%d records on disk, want 1", count)
	}
}

func testConcurrentLeases(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")

	const n = 10
	var wg sync.WaitGroup
	results := make([]error, n)
	start := make(chan struct{})
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			<-start
			results[i] = insertWriteLease(db, fmt.Sprintf("l-%02d", i), "idev-coder", "active")
		}(i)
	}
	close(start)
	wg.Wait()

	won := 0
	for _, err := range results {
		if err == nil {
			won++
			continue
		}
		if got := classify(err); got != "lease_held" {
			t.Errorf("unexpected failure: %q %v", got, err)
		}
	}
	if won != 1 {
		t.Fatalf("%d goroutines got the write lease, want 1", won)
	}
}

func testLeaseReleaseFreesSlot(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")

	if err := insertWriteLease(db, "l-1", "idev-coder", "active"); err != nil {
		t.Fatal(err)
	}
	exec(t, db, `UPDATE leases SET status = 'released' WHERE id = 'l-1'`)

	// The next writer can take it, and the released record is still there:
	// the history of who held it is part of the audit trail.
	if err := insertWriteLease(db, "l-2", "idev-verifier", "active"); err != nil {
		t.Errorf("a released lease must free the slot: %v", err)
	}
	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM leases`).Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 2 {
		t.Errorf("%d lease rows, want 2: releasing must not delete the record", count)
	}
}

func testAbortedRunFreesSlot(t *testing.T, open Opener, classify Classifier) {
	db := open(t)
	seedFeature(t, db)
	seedRun(t, db, runID, "lite-change", "running")
	exec(t, db, `UPDATE runs SET status = 'aborted' WHERE id = ?`, runID)

	// A finished or abandoned run must not block the next one, which is
	// what `cmd_start`'s rotate-the-old-file behaviour was approximating.
	if err := insertRun(db, altRunID, "lite-change", "running"); err != nil {
		t.Errorf("an aborted run must free the slot: %v", err)
	}
}
