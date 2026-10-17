// Package memstore is an in-memory implementation of the ports, for testing
// the application layer without a database.
//
// It exists so a use-case test fails for reasons about the use case. Driving
// the services through SQLite would work, but then every service test also
// tests the schema, the driver and the migration — and when one breaks, the
// failure does not say which. The store adapters have their own consistency
// suite (internal/adapters/store/storetest) for exactly that.
//
// What it does not do is emulate the database's constraints loosely. The
// partial unique indexes are the invariants (I-1, I-5, threat T6), so they
// are enforced here too, with the same conflict kinds — a service that
// passes against this fake and fails against SQLite would make the fake
// worse than useless.
package memstore

import (
	"context"
	"fmt"
	"sort"
	"sync"
	"time"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/baseline"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/canonical"
)

// Store holds everything in memory.
type Store struct {
	mu sync.Mutex

	runs     map[string]*runRow
	leases   map[string]*leaseRow
	delegs   map[string]*ports.Delegation
	verifs   map[string]bool
	gates    map[string]*gateRow
	approvs  map[string]*ports.Approval
	baseline map[string]*baselineRow
	events   []audit.Event
	checkpts []audit.Checkpoint
	idemp    map[string][]byte
	fencing  map[string]uint64

	// FailOn makes the next call to a named operation return an error, so a
	// test can check that a use case leaves no partial state behind.
	FailOn map[string]error
}

type runRow struct {
	r         run.Run
	featureID string
	version   int64
}

type leaseRow struct {
	l         lease.Lease
	featureID string
	tokenHash string
	status    string
}

type gateRow struct {
	g         gate.Gate
	featureID string
}

type baselineRow struct {
	id       string
	feature  string
	manifest baseline.Manifest
	status   string
	sealedAt time.Time
}

// New returns an empty store.
func New() *Store {
	return &Store{
		runs:     map[string]*runRow{},
		leases:   map[string]*leaseRow{},
		delegs:   map[string]*ports.Delegation{},
		verifs:   map[string]bool{},
		gates:    map[string]*gateRow{},
		approvs:  map[string]*ports.Approval{},
		baseline: map[string]*baselineRow{},
		idemp:    map[string][]byte{},
		fencing:  map[string]uint64{},
		FailOn:   map[string]error{},
	}
}

// InTx runs fn against a snapshot, committing only when it returns nil.
//
// The snapshot is the point: a use case that fails halfway must leave
// nothing behind, and a fake that mutates in place would let a bug like
// that pass here and show up only against a real transaction.
func (s *Store) InTx(ctx context.Context, fn func(ports.Tx) error) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	snap := s.clone()
	tx := &txn{s: snap, ctx: ctx}
	if err := fn(tx); err != nil {
		return err
	}
	s.restore(snap)
	return nil
}

// Close is a no-op.
func (s *Store) Close() error { return nil }

func (s *Store) clone() *Store {
	out := New()
	out.FailOn = s.FailOn
	for k, v := range s.runs {
		cp := *v
		cp.r = v.r.Clone()
		out.runs[k] = &cp
	}
	for k, v := range s.leases {
		cp := *v
		out.leases[k] = &cp
	}
	for k, v := range s.delegs {
		cp := *v
		out.delegs[k] = &cp
	}
	for k, v := range s.verifs {
		out.verifs[k] = v
	}
	for k, v := range s.gates {
		cp := *v
		out.gates[k] = &cp
	}
	for k, v := range s.approvs {
		cp := *v
		out.approvs[k] = &cp
	}
	for k, v := range s.baseline {
		cp := *v
		out.baseline[k] = &cp
	}
	out.events = append([]audit.Event{}, s.events...)
	out.checkpts = append([]audit.Checkpoint{}, s.checkpts...)
	for k, v := range s.idemp {
		out.idemp[k] = v
	}
	for k, v := range s.fencing {
		out.fencing[k] = v
	}
	return out
}

func (s *Store) restore(from *Store) {
	s.runs, s.leases, s.delegs, s.verifs = from.runs, from.leases, from.delegs, from.verifs
	s.gates, s.approvs, s.baseline = from.gates, from.approvs, from.baseline
	s.events, s.idemp, s.fencing = from.events, from.idemp, from.fencing
	s.checkpts = from.checkpts
}

// Events returns the audit chain, for assertions.
func (s *Store) Events() []audit.Event {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]audit.Event{}, s.events...)
}

// Checkpoints returns every saved checkpoint, oldest first, for assertions.
func (s *Store) Checkpoints() []audit.Checkpoint {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]audit.Checkpoint{}, s.checkpts...)
}

// TamperEvent rewrites one stored event in place — not through Append, not
// through a use case. It exists because the audit chain's entire job is to
// survive an attacker with write access to the store (threat T7), and the
// use cases that defend against it must be tested against a tampered chain.
// The mutate function receives a copy of the stored event and returns the
// replacement; resealing inside it (audit.Seal) is the tamperer's own move.
func (s *Store) TamperEvent(seq int64, mutate func(e audit.Event) audit.Event) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for i := range s.events {
		if s.events[i].Seq == seq {
			s.events[i] = mutate(s.events[i])
			return
		}
	}
}

// Run returns a stored run, for assertions.
func (s *Store) Run(id string) (run.Run, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	row, ok := s.runs[id]
	if !ok {
		return run.Run{}, false
	}
	return row.r.Clone(), true
}

// SeedRun puts a run in place without going through a use case.
func (s *Store) SeedRun(r run.Run, featureID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.runs[r.ID] = &runRow{r: r.Clone(), featureID: featureID, version: 1}
}

// SeedBaseline puts a sealed baseline in place.
func (s *Store) SeedBaseline(featureID, id string, m baseline.Manifest) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.baseline[id] = &baselineRow{id: id, feature: featureID, manifest: m, status: "sealed"}
}

// SeedGateApproval puts a gate and its recorded approval in place, the way
// gatesvc.Decide leaves them, for tests that walk the run side of the loop.
func (s *Store) SeedGateApproval(g gate.Gate, featureID string, a ports.Approval) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.gates[g.ID] = &gateRow{g: g, featureID: featureID}
	cp := a
	s.approvs[a.ID] = &cp
}

func conflict(kind, detail string) error {
	return &ports.ConflictError{Kind: kind, Detail: detail}
}

// txn is one transaction's view.
type txn struct {
	s   *Store
	ctx context.Context
}

func (t *txn) Runs() ports.RunRepo               { return runRepo{t.s} }
func (t *txn) Leases() ports.LeaseRepo           { return leaseRepo{t.s} }
func (t *txn) Delegations() ports.DelegationRepo { return delegRepo{t.s} }
func (t *txn) Gates() ports.GateRepo             { return gateRepo{t.s} }
func (t *txn) Baselines() ports.BaselineRepo     { return baselineRepo{t.s} }
func (t *txn) Audit() ports.AuditRepo            { return auditRepo{t.s} }
func (t *txn) Idempotency() ports.IdempotencyRepo {
	return idempRepo{t.s}
}

func (s *Store) fail(op string) error {
	if err, ok := s.FailOn[op]; ok {
		return err
	}
	return nil
}

// --- runs ------------------------------------------------------------------

type runRepo struct{ s *Store }

func (r runRepo) Create(_ context.Context, rn run.Run, featureID string) error {
	if err := r.s.fail("runs.Create"); err != nil {
		return err
	}
	// The live-run index: one live run per (feature, workflow).
	for _, row := range r.s.runs {
		if row.featureID == featureID && row.r.WorkflowID == rn.WorkflowID && row.r.Live() {
			return conflict(ports.ConflictLiveRun,
				fmt.Sprintf("%s already has a live %s run", featureID, rn.WorkflowID))
		}
	}
	r.s.runs[rn.ID] = &runRow{r: rn.Clone(), featureID: featureID, version: 1}
	return nil
}

func (r runRepo) Get(_ context.Context, id string) (run.Run, int64, error) {
	row, ok := r.s.runs[id]
	if !ok {
		return run.Run{}, 0, conflict(ports.ConflictNotFound, "run "+id)
	}
	return row.r.Clone(), row.version, nil
}

func (r runRepo) FindLive(_ context.Context, featureID, workflowID string) (run.Run, int64, error) {
	for _, row := range r.s.runs {
		if row.featureID == featureID && row.r.WorkflowID == workflowID && row.r.Live() {
			return row.r.Clone(), row.version, nil
		}
	}
	return run.Run{}, 0, conflict(ports.ConflictNotFound, "no live run")
}

func (r runRepo) Save(_ context.Context, rn run.Run, version int64) error {
	if err := r.s.fail("runs.Save"); err != nil {
		return err
	}
	row, ok := r.s.runs[rn.ID]
	if !ok {
		return conflict(ports.ConflictNotFound, "run "+rn.ID)
	}
	// Compare-and-swap. A writer that read version N may only write N+1, so
	// two conductors cannot both apply a decision to the same run.
	if row.version != version {
		return conflict(ports.ConflictStaleVersion,
			fmt.Sprintf("run %s is at version %d, not %d", rn.ID, row.version, version))
	}
	row.r = rn.Clone()
	row.version++
	return nil
}

// --- leases ----------------------------------------------------------------

type leaseRepo struct{ s *Store }

func (l leaseRepo) Issue(_ context.Context, ls lease.Lease, tokenHash string) error {
	if err := l.s.fail("leases.Issue"); err != nil {
		return err
	}
	if ls.Purpose == lease.PurposeWrite {
		// Invariant I-1, both halves of the index: per feature when one is
		// set, and per run otherwise.
		for _, row := range l.s.leases {
			if row.status != "active" || row.l.Purpose != lease.PurposeWrite {
				continue
			}
			if ls.Feature != "" && row.featureID == ls.Feature {
				return conflict(ports.ConflictLeaseHeld,
					fmt.Sprintf("%s holds the write lease on %s", row.l.Agent, ls.Feature))
			}
			if ls.Feature == "" && row.l.RunID == ls.RunID {
				return conflict(ports.ConflictLeaseHeld,
					fmt.Sprintf("%s holds the write lease on run %s", row.l.Agent, ls.RunID))
			}
		}
	}
	l.s.leases[ls.ID] = &leaseRow{l: ls, featureID: ls.Feature, tokenHash: tokenHash, status: "active"}
	return nil
}

func (l leaseRepo) Get(_ context.Context, id string) (lease.Lease, error) {
	row, ok := l.s.leases[id]
	if !ok {
		return lease.Lease{}, conflict(ports.ConflictNotFound, "lease "+id)
	}
	return row.l, nil
}

func (l leaseRepo) ActiveFor(_ context.Context, runID, stepID string) (lease.Lease, error) {
	for _, row := range l.s.leases {
		if row.status == "active" && row.l.RunID == runID && row.l.StepID == stepID {
			return row.l, nil
		}
	}
	return lease.Lease{}, conflict(ports.ConflictNotFound, "no active lease")
}

func (l leaseRepo) Extend(
	_ context.Context, id, tokenHash string, now, until time.Time,
) (lease.Lease, error) {
	if err := l.s.fail("leases.Extend"); err != nil {
		return lease.Lease{}, err
	}
	row, ok := l.s.leases[id]
	if !ok {
		return lease.Lease{}, conflict(ports.ConflictNotFound, "lease "+id)
	}
	if row.tokenHash != tokenHash {
		// Only the holder can keep the lease; anyone else extending it
		// would hand the write to a caller that never won it.
		return lease.Lease{}, conflict(ports.ConflictLeaseHeld, "token does not match lease "+id)
	}
	if row.status != "active" {
		return lease.Lease{}, conflict(ports.ConflictLeaseHeld,
			fmt.Sprintf("lease %s is %s, not active", id, row.status))
	}
	if row.l.Expired(now) {
		// The sweeper may not have marked it yet, but the deadline is the
		// truth. Letting a late renewal through would resurrect a lease
		// after another one may have claimed the feature.
		return lease.Lease{}, conflict(ports.ConflictLeaseHeld,
			fmt.Sprintf("lease %s ran out at %s; a late renewal cannot resurrect it",
				id, row.l.ExpiresAt.Format(time.RFC3339)))
	}
	row.l.ExpiresAt = until
	return row.l, nil
}

func (l leaseRepo) Release(_ context.Context, id string) error {
	row, ok := l.s.leases[id]
	if !ok {
		return conflict(ports.ConflictNotFound, "lease "+id)
	}
	// Released, not deleted: who held it is part of the audit trail.
	row.status = "released"
	return nil
}

func (l leaseRepo) NextFencing(_ context.Context, featureID string) (uint64, error) {
	l.s.fencing[featureID]++
	return l.s.fencing[featureID], nil
}

func (l leaseRepo) Expire(_ context.Context, now time.Time, limit int) ([]lease.Lease, error) {
	var out []lease.Lease
	ids := make([]string, 0, len(l.s.leases))
	for id := range l.s.leases {
		ids = append(ids, id)
	}
	sort.Strings(ids) // deterministic order, so a sweeper test is repeatable
	for _, id := range ids {
		row := l.s.leases[id]
		if row.status != "active" || !row.l.Expired(now) {
			continue
		}
		row.status = "expired"
		out = append(out, row.l)
		if limit > 0 && len(out) >= limit {
			break
		}
	}
	return out, nil
}

// --- delegations -----------------------------------------------------------

type delegRepo struct{ s *Store }

func (d delegRepo) Insert(_ context.Context, rec ports.Delegation) error {
	if err := d.s.fail("delegations.Insert"); err != nil {
		return err
	}
	// Invariant I-5: a record is never replaced.
	for _, existing := range d.s.delegs {
		if existing.RunID == rec.RunID && existing.StepID == rec.StepID &&
			existing.Attempt == rec.Attempt {
			return conflict(ports.ConflictAttemptExists,
				fmt.Sprintf("%s attempt %d is already recorded", rec.StepID, rec.Attempt))
		}
	}
	cp := rec
	d.s.delegs[rec.ID] = &cp
	return nil
}

func (d delegRepo) Get(_ context.Context, id string) (ports.Delegation, error) {
	rec, ok := d.s.delegs[id]
	if !ok {
		return ports.Delegation{}, conflict(ports.ConflictNotFound, "delegation "+id)
	}
	return *rec, nil
}

func (d delegRepo) Latest(_ context.Context, runID, stepID string) (ports.Delegation, error) {
	var best *ports.Delegation
	for _, rec := range d.s.delegs {
		if rec.RunID != runID || rec.StepID != stepID {
			continue
		}
		if best == nil || rec.Attempt > best.Attempt {
			best = rec
		}
	}
	if best == nil {
		return ports.Delegation{}, conflict(ports.ConflictNotFound, "no delegation for "+stepID)
	}
	return *best, nil
}

func (d delegRepo) Update(_ context.Context, rec ports.Delegation) error {
	if _, ok := d.s.delegs[rec.ID]; !ok {
		return conflict(ports.ConflictNotFound, "delegation "+rec.ID)
	}
	cp := rec
	d.s.delegs[rec.ID] = &cp
	return nil
}

func (d delegRepo) RecordVerification(
	_ context.Context, delegationID, verifier, verdict string, evidence []string, at time.Time,
) error {
	if _, ok := d.s.delegs[delegationID]; !ok {
		return conflict(ports.ConflictNotFound, "delegation "+delegationID)
	}
	// One verdict per delegation: two would let a caller pick the one it
	// prefers, which is the same failure as asking a gate twice.
	if d.s.verifs[delegationID] {
		return conflict(ports.ConflictVerification, delegationID+" is already verified")
	}
	d.s.verifs[delegationID] = true
	return nil
}

// --- gates -----------------------------------------------------------------

type gateRepo struct{ s *Store }

func (g gateRepo) Open(_ context.Context, gt gate.Gate, featureID string) error {
	if err := g.s.fail("gates.Open"); err != nil {
		return err
	}
	// One open question per step.
	for _, row := range g.s.gates {
		if row.g.Status == gate.StatusPending && row.g.RunID == gt.RunID &&
			row.g.StepID == gt.StepID && gt.RunID != "" && gt.StepID != "" {
			return conflict(ports.ConflictGatePending,
				fmt.Sprintf("%s already has a pending gate", gt.StepID))
		}
	}
	g.s.gates[gt.ID] = &gateRow{g: gt, featureID: featureID}
	return nil
}

func (g gateRepo) Get(_ context.Context, id string) (gate.Gate, error) {
	row, ok := g.s.gates[id]
	if !ok {
		return gate.Gate{}, conflict(ports.ConflictNotFound, "gate "+id)
	}
	return row.g, nil
}

func (g gateRepo) Save(_ context.Context, gt gate.Gate) error {
	row, ok := g.s.gates[gt.ID]
	if !ok {
		return conflict(ports.ConflictNotFound, "gate "+gt.ID)
	}
	row.g = gt
	return nil
}

func (g gateRepo) RecordApproval(_ context.Context, a ports.Approval) error {
	if err := g.s.fail("gates.RecordApproval"); err != nil {
		return err
	}
	// Threat T6: replaying an approval against the same gate.
	for _, existing := range g.s.approvs {
		if existing.GateID == a.GateID {
			return conflict(ports.ConflictApprovalExists, "gate "+a.GateID+" is already decided")
		}
	}
	// Invariant I-3 at the storage layer, mirroring the CHECK constraint.
	if a.Kind != "human" {
		return fmt.Errorf("memstore: approver_kind must be human, got %q", a.Kind)
	}
	cp := a
	g.s.approvs[a.ID] = &cp
	return nil
}

func (g gateRepo) Approval(_ context.Context, id string) (ports.Approval, error) {
	a, ok := g.s.approvs[id]
	if !ok {
		return ports.Approval{}, conflict(ports.ConflictNotFound, "approval "+id)
	}
	return *a, nil
}

// --- baselines -------------------------------------------------------------

type baselineRepo struct{ s *Store }

func (b baselineRepo) Put(
	_ context.Context, featureID string, m baseline.Manifest, status string,
) (string, error) {
	if err := b.s.fail("baselines.Put"); err != nil {
		return "", err
	}
	if status == "sealed" {
		if err := b.checkOneSealed(featureID, ""); err != nil {
			return "", err
		}
	}
	id := fmt.Sprintf("bl-%s-%d", featureID, m.Revision)
	b.s.baseline[id] = &baselineRow{id: id, feature: featureID, manifest: m, status: status}
	return id, nil
}

func (b baselineRepo) checkOneSealed(featureID, except string) error {
	for _, row := range b.s.baseline {
		if row.feature == featureID && row.status == "sealed" && row.id != except {
			return conflict(ports.ConflictSealedBaseline,
				fmt.Sprintf("%s already has a sealed baseline at revision %d",
					featureID, row.manifest.Revision))
		}
	}
	return nil
}

func (b baselineRepo) Sealed(_ context.Context, featureID string) (baseline.Manifest, error) {
	for _, row := range b.s.baseline {
		if row.feature == featureID && row.status == "sealed" {
			return row.manifest, nil
		}
	}
	return baseline.Manifest{}, conflict(ports.ConflictNotFound, "no sealed baseline")
}

func (b baselineRepo) Get(_ context.Context, id string) (baseline.Manifest, error) {
	row, ok := b.s.baseline[id]
	if !ok {
		return baseline.Manifest{}, conflict(ports.ConflictNotFound, "baseline "+id)
	}
	return row.manifest, nil
}

func (b baselineRepo) Seal(_ context.Context, id string, at time.Time) error {
	row, ok := b.s.baseline[id]
	if !ok {
		return conflict(ports.ConflictNotFound, "baseline "+id)
	}
	if err := b.checkOneSealed(row.feature, id); err != nil {
		return err
	}
	row.status = "sealed"
	row.sealedAt = at
	return nil
}

func (b baselineRepo) Reopen(_ context.Context, featureID string) error {
	for _, row := range b.s.baseline {
		if row.feature == featureID && row.status == "sealed" {
			row.status = "reopened"
		}
	}
	return nil
}

// --- audit -----------------------------------------------------------------

type auditRepo struct{ s *Store }

func (a auditRepo) Append(_ context.Context, e audit.Event) (audit.Event, error) {
	if err := a.s.fail("audit.Append"); err != nil {
		return audit.Event{}, err
	}
	// The repo owns the sequence and the head, so two writers cannot
	// produce two events claiming the same predecessor.
	prev := audit.Genesis
	if n := len(a.s.events); n > 0 {
		prev = a.s.events[n-1].Hash
	}
	e.Seq = int64(len(a.s.events) + 1)
	sealed, err := audit.Seal(e, prev)
	if err != nil {
		return audit.Event{}, err
	}
	a.s.events = append(a.s.events, sealed)
	return sealed, nil
}

func (a auditRepo) Head(_ context.Context) (canonical.Digest, int64, error) {
	if n := len(a.s.events); n > 0 {
		return a.s.events[n-1].Hash, a.s.events[n-1].Seq, nil
	}
	return audit.Genesis, 0, nil
}

func (a auditRepo) Range(_ context.Context, fromSeq int64, limit int) ([]audit.Event, error) {
	var out []audit.Event
	for _, e := range a.s.events {
		if e.Seq < fromSeq {
			continue
		}
		out = append(out, e)
		if limit > 0 && len(out) >= limit {
			break
		}
	}
	return out, nil
}

func (a auditRepo) SaveCheckpoint(_ context.Context, cp audit.Checkpoint) error {
	if err := a.s.fail("audit.SaveCheckpoint"); err != nil {
		return err
	}
	a.s.checkpts = append(a.s.checkpts, cp)
	return nil
}

func (a auditRepo) Checkpoint(_ context.Context) (audit.Checkpoint, error) {
	if n := len(a.s.checkpts); n > 0 {
		return a.s.checkpts[n-1], nil
	}
	return audit.Checkpoint{}, conflict(ports.ConflictNotFound, "no checkpoint yet")
}

// --- idempotency -----------------------------------------------------------

type idempRepo struct{ s *Store }

func (i idempRepo) Claim(_ context.Context, key, scope string) ([]byte, bool, error) {
	if key == "" {
		return nil, false, nil
	}
	if result, ok := i.s.idemp[key]; ok {
		return result, true, nil
	}
	i.s.idemp[key] = nil
	return nil, false, nil
}

func (i idempRepo) Complete(_ context.Context, key string, result []byte) error {
	if key == "" {
		return nil
	}
	i.s.idemp[key] = result
	return nil
}
