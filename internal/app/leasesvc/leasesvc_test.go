package leasesvc_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/memstore"
	"github.com/idev/internal/app/leasesvc"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

// The tests pin the lease service's promises: one writer per feature (I-1),
// the verifier fenced into the ticket directory (I-2), and every state
// change leaving with its audit event in the same transaction (I-6).

var at = time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

type seqIDs struct{ n int }

func (g *seqIDs) New() string {
	g.n++
	return fmt.Sprintf("01LSE0000000000000000000%02d", g.n)
}

func newSvc(t *testing.T) (leasesvc.Service, *memstore.Store) {
	t.Helper()
	st := memstore.New()
	// The run a lease is bound to: a delegated step for the writer, a
	// verifying step for the verifier (review D2's binding).
	st.SeedRun(delegatedRun(), "f-1")
	return leasesvc.Service{Store: st, Clock: fixedClock{t: at}, IDs: &seqIDs{}}, st
}

// delegatedRun is the run the acquire params point at: code-pass delegated
// to the coder, verify-plan accepted and awaiting its verifier.
func delegatedRun() run.Run {
	return run.Run{
		ID: "r-1", WorkflowID: "lite-change", Feature: "demo",
		Steps: []run.Step{
			{ID: "code-pass", Kind: "deliver.code_pass", State: run.StepDelegated, Writer: "coder@claude"},
			{ID: "verify-plan", Kind: "verify.plan", State: run.StepVerifying, Writer: "verifier@claude"},
		},
	}
}

func conductor() ports.Principal {
	return ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "wangwei794"}
}

// writeParams asks for the lease a coder needs to change product code.
func writeParams() leasesvc.AcquireParams {
	return leasesvc.AcquireParams{
		Purpose:    lease.PurposeWrite,
		Feature:    "f-1",
		RunID:      "r-1",
		StepID:     "code-pass",
		Agent:      "coder@claude",
		WritePaths: []string{"**"},
		Actor:      conductor(),
	}
}

// verifyParams asks for the verifier's slice of one ticket.
func verifyParams() leasesvc.AcquireParams {
	return leasesvc.AcquireParams{
		Purpose:    lease.PurposeVerify,
		Feature:    "f-1",
		RunID:      "r-1",
		StepID:     "verify-plan",
		Agent:      "verifier@claude",
		TicketDir:  "tickets/F-1",
		WritePaths: []string{"tickets/F-1/**"},
		Actor:      conductor(),
	}
}

func acquire(t *testing.T, s leasesvc.Service, p leasesvc.AcquireParams) leasesvc.Held {
	t.Helper()
	h, err := s.Acquire(context.Background(), p)
	if err != nil {
		t.Fatalf("Acquire: %v", err)
	}
	return h
}

// activeLease and getLease read through a transaction, the way a conductor
// would, so the assertions are about the store and not a return value.
func activeLease(t *testing.T, st *memstore.Store, runID, stepID string) (lease.Lease, bool) {
	t.Helper()
	var (
		l     lease.Lease
		found bool
	)
	err := st.InTx(context.Background(), func(tx ports.Tx) error {
		got, err := tx.Leases().ActiveFor(context.Background(), runID, stepID)
		if err != nil {
			var ce *ports.ConflictError
			if errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound {
				return nil
			}
			return err
		}
		l, found = got, true
		return nil
	})
	if err != nil {
		t.Fatalf("ActiveFor: %v", err)
	}
	return l, found
}

func getLease(t *testing.T, st *memstore.Store, id string) lease.Lease {
	t.Helper()
	var l lease.Lease
	if err := st.InTx(context.Background(), func(tx ports.Tx) error {
		got, err := tx.Leases().Get(context.Background(), id)
		if err != nil {
			return err
		}
		l = got
		return nil
	}); err != nil {
		t.Fatalf("Get(%s): %v", id, err)
	}
	return l
}

func wantConflict(t *testing.T, err error, kind, what string) {
	t.Helper()
	var ce *ports.ConflictError
	if !errors.As(err, &ce) || ce.Kind != kind {
		t.Fatalf("%s: err = %v, want a %s conflict", what, err, kind)
	}
}

func TestAcquireIssuesALeaseAndRecordsIt(t *testing.T) {
	s, st := newSvc(t)
	h := acquire(t, s, writeParams())

	if len(h.Token) != 43 { // 32 random bytes, base64 without padding
		t.Errorf("token = %q, want 43 base64 characters", h.Token)
	}
	if h.Lease.ID == "" || h.Lease.Fencing != 1 {
		t.Errorf("lease = %+v, want an id and fencing 1 on the feature's first lease", h.Lease)
	}
	if want := at.Add(30 * time.Minute); !h.Lease.ExpiresAt.Equal(want) {
		t.Errorf("deadline = %v, want %v (the default TTL)", h.Lease.ExpiresAt, want)
	}
	if _, ok := activeLease(t, st, "r-1", "code-pass"); !ok {
		t.Error("the step has no active lease after acquire")
	}

	events := st.Events()
	if len(events) != 1 || events[0].Action != audit.ActionLeaseAcquired {
		t.Fatalf("audit = %v, want one lease.acquired", events)
	}
	e := events[0]
	if e.Subject != h.Lease.ID || e.RunID != "r-1" || e.StepID != "code-pass" || e.Feature != "f-1" {
		t.Errorf("event scope = %s/%s/%s for %s", e.RunID, e.StepID, e.Feature, e.Subject)
	}
	if !e.At.Equal(at) {
		t.Errorf("At = %v, want the clock's %v", e.At, at)
	}
	if e.Actor.Handle != "conductor@claude" || e.Actor.OnBehalfOf != "wangwei794" {
		t.Errorf("actor = %+v, want the conductor acting for a person", e.Actor)
	}
	if e.Detail["fencing"] != uint64(1) || e.Detail["agent"] != "coder@claude" {
		t.Errorf("detail = %v", e.Detail)
	}
	if want := at.Add(30 * time.Minute).Format(time.RFC3339); e.Detail["expires_at"] != want {
		t.Errorf("expires_at = %v, want %s", e.Detail["expires_at"], want)
	}
	// The token lives exactly once: in the Held the caller got. The audit
	// log must never see it — only the hash is stored anywhere.
	if blob, err := json.Marshal(e.Detail); err != nil || strings.Contains(string(blob), h.Token) {
		t.Error("the bearer token leaked into the audit log")
	}
}

// seedDelegated extends the seeded run with another delegated step, for
// tests that race a second writer onto the same feature.
func seedDelegated(st *memstore.Store, runID, stepID, agent string) {
	r, ok := st.Run(runID)
	if !ok {
		return
	}
	r.Steps = append(r.Steps, run.Step{
		ID: stepID, Kind: "deliver.code_pass", State: run.StepDelegated, Writer: agent,
	})
	st.SeedRun(r, "f-1")
}

// seedDelegatedRun seeds a whole run (ID runID, feature featureID) whose
// single step stepID is delegated to agent.
func seedDelegatedRun(st *memstore.Store, runID, featureID, stepID, agent string) {
	st.SeedRun(run.Run{
		ID: runID, WorkflowID: "lite-change", Feature: "demo",
		Steps: []run.Step{
			{ID: stepID, Kind: "deliver.code_pass", State: run.StepDelegated, Writer: agent},
		},
	}, featureID)
}

func TestAcquireRefusesASecondWriteLeaseOnTheFeature(t *testing.T) {
	s, st := newSvc(t)
	acquire(t, s, writeParams())

	p := writeParams() // same feature, another step and agent
	p.StepID, p.Agent = "code-pass-2", "other-coder@claude"
	seedDelegated(st, "r-1", "code-pass-2", "other-coder@claude")
	_, err := s.Acquire(context.Background(), p)
	wantConflict(t, err, ports.ConflictLeaseHeld, "a second write lease on the feature")
	if len(st.Events()) != 1 {
		t.Errorf("%d events; a refused acquire must not be recorded", len(st.Events()))
	}

	// A verify lease runs alongside the writer: I-1 is about who may change
	// product code, and the verifier is fenced elsewhere (I-2).
	if _, err := s.Acquire(context.Background(), verifyParams()); err != nil {
		t.Fatalf("a verify lease beside the write lease: %v", err)
	}
}

func TestAcquireKeepsAVerifyLeaseInsideTheTicketDirectory(t *testing.T) {
	s, _ := newSvc(t)

	p := verifyParams()
	p.WritePaths = []string{"tickets/F-1/report.md", "internal/domain/foo.go"}
	if _, err := s.Acquire(context.Background(), p); err == nil {
		t.Fatal("a verify lease reaching product code was issued (I-2)")
	}

	p.WritePaths = []string{"tickets/F-1/report.md", "tickets/F-1/**"}
	h := acquire(t, s, p)
	if h.Lease.Purpose != lease.PurposeVerify {
		t.Errorf("purpose = %s, want verify", h.Lease.Purpose)
	}

	p.TicketDir = "" // nowhere left to fence the writes into
	if _, err := s.Acquire(context.Background(), p); err == nil {
		t.Fatal("a verify lease without a ticket directory was issued")
	}
}

func TestAcquireRefusesIncompleteParameters(t *testing.T) {
	s, st := newSvc(t)

	mut := func(f func(*leasesvc.AcquireParams)) leasesvc.AcquireParams {
		p := writeParams()
		f(&p)
		return p
	}
	for _, tc := range []struct {
		what string
		p    leasesvc.AcquireParams
	}{
		{"a none step", mut(func(p *leasesvc.AcquireParams) { p.Purpose = lease.PurposeNone })},
		{"no agent", mut(func(p *leasesvc.AcquireParams) { p.Agent = "" })},
		{"no run", mut(func(p *leasesvc.AcquireParams) { p.RunID = "" })},
		{"no step", mut(func(p *leasesvc.AcquireParams) { p.StepID = "" })},
		{"no feature", mut(func(p *leasesvc.AcquireParams) { p.Feature = "" })},
	} {
		if _, err := s.Acquire(context.Background(), tc.p); err == nil {
			t.Errorf("%s: a lease was issued", tc.what)
		}
	}
	if len(st.Events()) != 0 {
		t.Error("a refused acquire wrote an audit event")
	}
}

func TestRenewPushesTheDeadlineWithoutAnAuditEvent(t *testing.T) {
	s, st := newSvc(t)
	h := acquire(t, s, writeParams())

	// Ten minutes in, only the clock moved.
	s.Clock = fixedClock{t: at.Add(10 * time.Minute)}
	got, err := s.Renew(context.Background(), h.Lease.ID, h.Token)
	if err != nil {
		t.Fatalf("Renew: %v", err)
	}
	if want := at.Add(40 * time.Minute); !got.ExpiresAt.Equal(want) {
		t.Errorf("deadline = %v, want %v", got.ExpiresAt, want)
	}
	if got.ID != h.Lease.ID || got.Agent != h.Lease.Agent || got.Fencing != h.Lease.Fencing {
		t.Error("the renewal changed the lease's facts; only the deadline moves")
	}
	if len(st.Events()) != 1 {
		t.Errorf("%d events; a keepalive is not worth a record", len(st.Events()))
	}
	if l := getLease(t, st, h.Lease.ID); !l.ExpiresAt.Equal(at.Add(40 * time.Minute)) {
		t.Errorf("the stored deadline = %v; the return value is not the store", l.ExpiresAt)
	}
}

func TestRenewIsRefusedForAnyoneButTheLiveHolder(t *testing.T) {
	s, _ := newSvc(t)
	h := acquire(t, s, writeParams())

	_, err := s.Renew(context.Background(), h.Lease.ID, "a-forged-token")
	wantConflict(t, err, ports.ConflictLeaseHeld, "a forged token")

	_, err = s.Renew(context.Background(), "no-such-lease", h.Token)
	wantConflict(t, err, ports.ConflictNotFound, "an unknown lease")

	// A released lease stays down.
	if err := s.Release(context.Background(), h.Lease.ID, h.Token, conductor()); err != nil {
		t.Fatalf("Release: %v", err)
	}
	_, err = s.Renew(context.Background(), h.Lease.ID, h.Token)
	wantConflict(t, err, ports.ConflictLeaseHeld, "a released lease")

	// So does one past its deadline, even before the sweeper has marked it.
	s2, _ := newSvc(t)
	h2 := acquire(t, s2, writeParams())
	s2.Clock = fixedClock{t: at.Add(31 * time.Minute)}
	_, err = s2.Renew(context.Background(), h2.Lease.ID, h2.Token)
	wantConflict(t, err, ports.ConflictLeaseHeld, "an expired lease")
}

func TestAFailedRenewLeavesTheLeaseAlone(t *testing.T) {
	s, st := newSvc(t)
	h := acquire(t, s, writeParams())

	st.FailOn["leases.Extend"] = errors.New("disk full")
	s.Clock = fixedClock{t: at.Add(10 * time.Minute)}
	if _, err := s.Renew(context.Background(), h.Lease.ID, h.Token); err == nil {
		t.Fatal("the store failure was swallowed")
	}
	// The deadline and the audit trail must look as if nothing happened.
	if want := at.Add(30 * time.Minute); !getLease(t, st, h.Lease.ID).ExpiresAt.Equal(want) {
		t.Errorf("a failed renewal moved the deadline")
	}
	if len(st.Events()) != 1 {
		t.Errorf("%d events after a failed renewal", len(st.Events()))
	}

	delete(st.FailOn, "leases.Extend")
	if _, err := s.Renew(context.Background(), h.Lease.ID, h.Token); err != nil {
		t.Fatalf("Renew after the failure cleared: %v", err)
	}
}

func TestReleaseRetiresTheLeaseAndAudits(t *testing.T) {
	s, st := newSvc(t)
	h := acquire(t, s, writeParams())

	// Not the holder: releasing a lease needs its token (review D2).
	err := s.Release(context.Background(), h.Lease.ID, "a-forged-token", conductor())
	wantConflict(t, err, ports.ConflictLeaseHeld, "a forged release token")
	if _, ok := activeLease(t, st, "r-1", "code-pass"); !ok {
		t.Error("a forged token retired the lease")
	}

	if err := s.Release(context.Background(), h.Lease.ID, h.Token, conductor()); err != nil {
		t.Fatalf("Release: %v", err)
	}
	if _, ok := activeLease(t, st, "r-1", "code-pass"); ok {
		t.Error("the step still has an active lease")
	}
	events := st.Events()
	if len(events) != 2 || events[1].Action != audit.ActionLeaseReleased {
		t.Fatalf("audit = %v, want lease.acquired then lease.released", events)
	}
	if events[1].Subject != h.Lease.ID || events[1].Detail["agent"] != "coder@claude" {
		t.Errorf("release event = %+v", events[1])
	}

	// A retry is not a second release.
	if err := s.Release(context.Background(), h.Lease.ID, h.Token, conductor()); err != nil {
		t.Fatalf("second Release: %v", err)
	}
	if len(st.Events()) != 2 {
		t.Error("a double release wrote a second event")
	}

	// A fresh lease may take the step; retiring the old one again is still
	// not an event.
	h2 := acquire(t, s, writeParams())
	if h2.Lease.Fencing != 2 {
		t.Errorf("fencing = %d, want 2 for the feature's second lease", h2.Lease.Fencing)
	}
	if err := s.Release(context.Background(), h.Lease.ID, h.Token, conductor()); err != nil {
		t.Fatalf("Release of the superseded lease: %v", err)
	}
	if len(st.Events()) != 3 {
		t.Error("releasing a superseded lease wrote an event")
	}
	if _, ok := activeLease(t, st, "r-1", "code-pass"); !ok {
		t.Error("the successor lease was disturbed")
	}
}

func TestReleaseOfAnExpiredLeaseLeavesItToTheSweeper(t *testing.T) {
	s, st := newSvc(t)
	h := acquire(t, s, writeParams())

	s.Clock = fixedClock{t: at.Add(31 * time.Minute)}
	if err := s.Release(context.Background(), h.Lease.ID, h.Token, conductor()); err != nil {
		t.Fatalf("Release: %v", err)
	}
	if len(st.Events()) != 1 {
		t.Fatalf("%d events; expiry is the sweeper's fact to record", len(st.Events()))
	}

	n, err := s.Sweep(context.Background())
	if err != nil || n != 1 {
		t.Fatalf("Sweep = %d, %v; want 1, nil", n, err)
	}
	events := st.Events()
	if len(events) != 2 || events[1].Action != audit.ActionLeaseExpired {
		t.Fatalf("audit = %v, want lease.expired", events)
	}
	if events[1].Actor.Handle != "sweeper" || events[1].Actor.Kind != "system" || events[1].Actor.OnBehalfOf != "" {
		t.Errorf("expiry actor = %+v, want the system sweeper on nobody's behalf", events[1].Actor)
	}
	if want := at.Add(31 * time.Minute).Format(time.RFC3339); events[1].Detail["expired_at"] != want {
		t.Errorf("expired_at = %v, want %s", events[1].Detail["expired_at"], want)
	}
}

func TestSweepExpiresOnlyWhatRanOut(t *testing.T) {
	s, st := newSvc(t)
	h1 := acquire(t, s, writeParams()) // f-1, runs out at 12:30
	p2 := writeParams()
	p2.Feature, p2.RunID, p2.StepID = "f-2", "r-2", "code-pass"
	seedDelegatedRun(st, "r-2", "f-2", "code-pass", "coder@claude") // its own delegated run
	h2 := acquire(t, s, p2)                                         // f-2, runs out at 12:30 too

	// Taken twenty minutes later, this one outlives the sweep.
	s.Clock = fixedClock{t: at.Add(20 * time.Minute)}
	acquire(t, s, verifyParams()) // runs out at 12:50
	s.Clock = fixedClock{t: at.Add(31 * time.Minute)}

	n, err := s.Sweep(context.Background())
	if err != nil || n != 2 {
		t.Fatalf("Sweep = %d, %v; want the two leases that ran out", n, err)
	}
	events := st.Events()
	if len(events) != 5 {
		t.Fatalf("%d events; want three issued and two expired", len(events))
	}
	if events[3].Action != audit.ActionLeaseExpired || events[4].Action != audit.ActionLeaseExpired {
		t.Fatalf("audit tail = %s, %s", events[3].Action, events[4].Action)
	}
	if events[3].Subject != h1.Lease.ID || events[4].Subject != h2.Lease.ID {
		t.Errorf("expired %s then %s; a stable order wants %s then %s",
			events[3].Subject, events[4].Subject, h1.Lease.ID, h2.Lease.ID)
	}
	if _, ok := activeLease(t, st, "r-1", "verify-plan"); !ok {
		t.Error("the sweep retired a lease that had not run out")
	}

	// And it does not repeat itself.
	if n, err = s.Sweep(context.Background()); err != nil || n != 0 {
		t.Fatalf("second Sweep = %d, %v; want nothing left", n, err)
	}
	if len(st.Events()) != 5 {
		t.Error("the second sweep wrote events")
	}
}

func TestSweepBatchesAtAHundred(t *testing.T) {
	s, st := newSvc(t)
	for i := 0; i < 101; i++ {
		p := writeParams()
		p.Feature = fmt.Sprintf("f-%03d", i)
		p.RunID = fmt.Sprintf("r-%03d", i)
		seedDelegatedRun(st, p.RunID, p.Feature, "code-pass", "coder@claude")
		acquire(t, s, p)
	}

	s.Clock = fixedClock{t: at.Add(31 * time.Minute)}
	n, err := s.Sweep(context.Background())
	if err != nil || n != 100 {
		t.Fatalf("Sweep = %d, %v; want one batch of 100", n, err)
	}
	if got, want := len(st.Events()), 101+100; got != want {
		t.Fatalf("%d events, want %d", got, want)
	}
	if n, err = s.Sweep(context.Background()); err != nil || n != 1 {
		t.Fatalf("second Sweep = %d, %v; want the one left over", n, err)
	}
}

func TestAFailedAcquireLeavesNothingBehind(t *testing.T) {
	s, st := newSvc(t)
	st.FailOn["leases.Issue"] = errors.New("disk full")

	p := writeParams()
	if _, err := s.Acquire(context.Background(), p); err == nil {
		t.Fatal("the store failure was swallowed")
	}
	if len(st.Events()) != 0 {
		t.Error("a failed acquire left an audit event behind (I-6)")
	}
	if _, ok := activeLease(t, st, p.RunID, p.StepID); ok {
		t.Error("a failed acquire left a lease behind")
	}

	// The fencing increment rolled back with the lease: a refused acquire
	// burns nothing.
	delete(st.FailOn, "leases.Issue")
	if h := acquire(t, s, p); h.Lease.Fencing != 1 {
		t.Errorf("fencing = %d, want 1; the failed attempt burned a token", h.Lease.Fencing)
	}
}

func TestAnUnsweptExpiredLeaseStillHoldsTheFeature(t *testing.T) {
	s, st := newSvc(t)
	acquire(t, s, writeParams())

	// Past its deadline but not yet swept, the lease still owns the
	// feature: Issue does not check expiry, so the single-writer rule
	// (I-1) holds across the gap between a lease running out and the
	// sweep that records it. The DB fallback layer never widens the
	// writer set on its own.
	s.Clock = fixedClock{t: at.Add(31 * time.Minute)}
	p := writeParams() // same feature, a new step and holder
	p.StepID, p.Agent = "code-pass-2", "other-coder@claude"
	seedDelegated(st, "r-1", "code-pass-2", "other-coder@claude")
	_, err := s.Acquire(context.Background(), p)
	wantConflict(t, err, ports.ConflictLeaseHeld, "an expired but unswept lease")
	if len(st.Events()) != 1 {
		t.Errorf("%d events; the refused acquire must not be recorded", len(st.Events()))
	}
}

func TestTheLeaseAfterASweepFencesAboveTheOneItReplaced(t *testing.T) {
	s, st := newSvc(t)
	h1 := acquire(t, s, writeParams())

	s.Clock = fixedClock{t: at.Add(31 * time.Minute)}
	if n, err := s.Sweep(context.Background()); err != nil || n != 1 {
		t.Fatalf("Sweep = %d, %v; want the one lease that ran out", n, err)
	}

	// With the dead lease retired, the feature is acquirable again, and
	// the successor starts above its predecessor: fencing tokens only
	// climb, so a write the dead holder still has in flight presents a
	// stale token and is refused downstream.
	h2 := acquire(t, s, writeParams())
	if h2.Lease.Fencing <= h1.Lease.Fencing {
		t.Errorf("fencing = %d, want above %d once the lease is swept", h2.Lease.Fencing, h1.Lease.Fencing)
	}
	if want := at.Add(61 * time.Minute); !h2.Lease.ExpiresAt.Equal(want) {
		t.Errorf("deadline = %v, want %v (a fresh TTL from the swept time)", h2.Lease.ExpiresAt, want)
	}
	if _, ok := activeLease(t, st, "r-1", "code-pass"); !ok {
		t.Error("the successor lease is not the step's active lease")
	}
	events := st.Events()
	if len(events) != 3 || events[2].Action != audit.ActionLeaseAcquired {
		t.Fatalf("audit = %v, want acquired, expired, acquired", events)
	}
	if events[2].Detail["fencing"] != uint64(2) {
		t.Errorf("fencing detail = %v, want 2", events[2].Detail["fencing"])
	}
}
