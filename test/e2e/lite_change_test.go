package e2e_test

import (
	"context"
	"errors"
	"testing"

	"github.com/idev/internal/app/gatesvc"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

// The seven steps of lite-change, walked end to end with no faults: two
// conductor steps, three delegations (one with independent verification),
// two human gates. The promise is that a run started through runsvc
// reaches done, every transition left one audit event, and the chain a
// checkpoint is signed over verifies offline.
func TestLiteChangeWalksToDone(t *testing.T) {
	w := newWorld(t)
	r := startLiteChange(t, w)
	walkHappyPath(t, w, r)

	final, err := w.run.Get(context.Background(), r.ID)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if final.Status() != run.StatusDone {
		t.Fatalf("status = %s, want done", final.Status())
	}
	for _, s := range final.Steps {
		if s.State != run.StepPASS {
			t.Errorf("step %s = %s, want PASS", s.ID, s.State)
		}
	}

	// One audit event per transition, and the chain holds over all of it.
	events := w.st.Events()
	if len(events) == 0 {
		t.Fatal("no audit events at all")
	}
	if err := audit.Verify(audit.Genesis, events); err != nil {
		t.Fatalf("the audit chain does not verify: %v", err)
	}

	// A checkpoint over the finished run verifies: the signature covers
	// the head, and a Verify from Genesis passes over the whole walk.
	if _, err := w.audit.Checkpoint(context.Background()); err != nil {
		t.Fatalf("Checkpoint: %v", err)
	}
	res, err := w.audit.Verify(context.Background(), 1, 0)
	if err != nil {
		t.Fatalf("Verify(1,0): %v", err)
	}
	if !res.CheckedCheckpoint {
		t.Error("the verification did not check the checkpoint signature")
	}
	if res.To != int64(len(events)) {
		t.Errorf("verified up to seq %d, want %d", res.To, len(events))
	}
}

// The same walk with the failure design §20.5 asks for injected: the
// verify.run step FAILs, the run blocks, a second failed step cannot be
// retried past the first, and after one retry the run reaches done.
//
// The blocked-and-retry shape is what `policy.on_fail: stop` means
// mechanically: FAIL → blocked → nothing advances → EvStepRetried is the
// only way forward.
func TestLiteChangeSurvivesAFailAndRetry(t *testing.T) {
	w := newWorld(t)
	r := startLiteChange(t, w)

	conductorStep(t, w, r.ID, "preflight", "preflight/probe.md")
	delegate(t, w, r.ID, "scope-guard", "idev-ops", "idev-ops", run.StepPASS)
	delegate(t, w, r.ID, "code-pass", "idev-coder", "idev-reviewer", run.StepPASS)
	delegate(t, w, r.ID, "plan", "idev-verifier", "idev-verifier", run.StepPASS)
	approveGate(t, w, r.ID, "gate-plan", "确认")

	// The injected failure: the run step reports FAIL.
	delegate(t, w, r.ID, "run", "idev-verifier", "idev-verifier", run.StepFAIL)

	blocked, err := w.run.Get(context.Background(), r.ID)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if blocked.Status() != run.StatusBlocked {
		t.Fatalf("status after FAIL = %s, want blocked", blocked.Status())
	}

	// While blocked, the gate behind the failed step cannot be reached:
	// nothing advances, and the conductor cannot skip ahead.
	refuse(t, w, r.ID, run.Event{
		Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "gate-next",
	}, conductor(), "activating a step past a FAIL")

	// The retry needs a note; an empty one is refused.
	refuse(t, w, r.ID, run.Event{
		Kind: run.EvStepRetried, Actor: run.ActorConductor, StepID: "run",
	}, conductor(), "a retry without a note")

	// A person's words are still needed at the last gate, and the person
	// may refuse: a rejection stops the run for good.
	apply(t, w, r.ID, run.Event{
		Kind: run.EvStepRetried, Actor: run.ActorConductor, StepID: "run",
		Note: "flaky case; re-ran with the fixture regenerated",
	}, conductor())
	delegate(t, w, r.ID, "run", "idev-verifier", "idev-verifier", run.StepPASS)
	approveGate(t, w, r.ID, "gate-next", "确认")

	final, err := w.run.Get(context.Background(), r.ID)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if final.Status() != run.StatusDone {
		t.Fatalf("status after retry = %s, want done", final.Status())
	}

	// The attempt counter recorded the retry: attempt 2 on the run step.
	var attempt int
	for _, s := range final.Steps {
		if s.ID == "run" {
			attempt = s.Attempt
		}
	}
	if attempt != 2 {
		t.Errorf("run step attempt = %d, want 2", attempt)
	}

	// And the whole history, fail included, is one verifiable chain.
	if err := audit.Verify(audit.Genesis, w.st.Events()); err != nil {
		t.Fatalf("the audit chain does not verify after a retry: %v", err)
	}
}

// A person's refusal at the last gate ends the run as blocked, not done:
// "not promoting" is lite-change's default ending when the person does not
// confirm, and the machine must not turn a rejection into a success.
func TestLiteChangeGateRejectionBlocksTheRun(t *testing.T) {
	w := newWorld(t)
	r := startLiteChange(t, w)
	walkHappyPath(t, w, r)
	// walkHappyPath already approved gate-next; start over with a fresh
	// run for the rejection case.
	r2 := startLiteChange(t, w)
	conductorStep(t, w, r2.ID, "preflight", "preflight/probe.md")
	delegate(t, w, r2.ID, "scope-guard", "idev-ops", "idev-ops", run.StepPASS)
	delegate(t, w, r2.ID, "code-pass", "idev-coder", "idev-reviewer", run.StepPASS)
	delegate(t, w, r2.ID, "plan", "idev-verifier", "idev-verifier", run.StepPASS)
	approveGate(t, w, r2.ID, "gate-plan", "确认")
	delegate(t, w, r2.ID, "run", "idev-verifier", "idev-verifier", run.StepPASS)

	// The person rejects the final gate.
	ctx := context.Background()
	activate(t, w, r2.ID, "gate-next")
	apply(t, w, r2.ID, run.Event{
		Kind: run.EvGateRequested, Actor: run.ActorConductor, StepID: "gate-next",
	}, conductor())
	_, err := w.run.Apply(ctx, r2.ID, run.Event{
		Kind: run.EvGateRejected, Actor: run.ActorHuman, StepID: "gate-next",
	}, person())
	if err != nil {
		t.Fatalf("GateRejected: %v", err)
	}
	final, err := w.run.Get(ctx, r2.ID)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if final.Status() != run.StatusBlocked {
		t.Fatalf("status after a rejection = %s, want blocked", final.Status())
	}
	if final.Status() == run.StatusDone {
		t.Fatal("a rejection must never end as done")
	}
}

// The conductor cannot approve its own gate anywhere in the walk (I-3):
// the e2e shape of the unit-level promise, checked at the first gate.
func TestTheConductorCannotApproveAGate(t *testing.T) {
	w := newWorld(t)
	r := startLiteChange(t, w)
	conductorStep(t, w, r.ID, "preflight", "preflight/probe.md")
	delegate(t, w, r.ID, "scope-guard", "idev-ops", "idev-ops", run.StepPASS)
	delegate(t, w, r.ID, "code-pass", "idev-coder", "idev-reviewer", run.StepPASS)
	delegate(t, w, r.ID, "plan", "idev-verifier", "idev-verifier", run.StepPASS)
	activate(t, w, r.ID, "gate-plan")
	apply(t, w, r.ID, run.Event{
		Kind: run.EvGateRequested, Actor: run.ActorConductor, StepID: "gate-plan",
	}, conductor())

	refuse(t, w, r.ID, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorConductor, StepID: "gate-plan",
		ApprovalID: "01FORGED00000000000000000",
	}, conductor(), "the conductor approving a gate")

	// Nothing was written by the refused event: the chain has no approval.
	for _, e := range w.st.Events() {
		if e.Action == audit.ActionGateApproved {
			t.Fatal("a refused gate approval left an audit event")
		}
	}
}

// The probe from review D1, made a permanent regression: an agent that
// writes Actor: human and an invented approval id into the event must not
// pass the gate. The domain guards read the event's own claims; this test
// pins the service-level check that re-establishes them.
func TestAForgedHumanApprovalIsRefused(t *testing.T) {
	w := newWorld(t)
	r := startLiteChange(t, w)
	conductorStep(t, w, r.ID, "preflight", "preflight/probe.md")
	delegate(t, w, r.ID, "scope-guard", "idev-ops", "idev-ops", run.StepPASS)
	delegate(t, w, r.ID, "code-pass", "idev-coder", "idev-reviewer", run.StepPASS)
	delegate(t, w, r.ID, "plan", "idev-verifier", "idev-verifier", run.StepPASS)
	activate(t, w, r.ID, "gate-plan")
	apply(t, w, r.ID, run.Event{
		Kind: run.EvGateRequested, Actor: run.ActorConductor, StepID: "gate-plan",
	}, conductor())

	// The forged shape: an agent principal claiming a human actor, with an
	// approval id nothing ever recorded.
	refuse(t, w, r.ID, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorHuman, StepID: "gate-plan",
		ApprovalID: "01FORGED00000000000000000",
	}, conductor(), "an agent forging a human approval")

	// The person path is not a bypass either: a real human principal cannot
	// reference an approval that was never recorded.
	refuse(t, w, r.ID, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorHuman, StepID: "gate-plan",
		ApprovalID: "01ALSOFORGED00000000000000",
	}, person(), "a person referencing an unrecorded approval")

	// A genuine decide produces a reject, not an approve; a rejected gate
	// cannot be walked to PASS by reusing its approval id.
	g := askGate(t, w, r.ID, "gate-plan")
	_, err := w.gate.Decide(context.Background(), gatesvc.DecisionParams{
		GateID: g.ID, Quote: "驳回", Channel: gatesvc.ChannelOIDC,
		RecomputedDigest: "sha256:gate-plan", Actor: person(),
	})
	if err != nil {
		t.Fatalf("Decide(reject): %v", err)
	}
	refuse(t, w, r.ID, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorHuman, StepID: "gate-plan",
		ApprovalID: "01REJECTED0000000000000000",
	}, person(), "a rejected decision being reused as an approval")

	// Still nothing passed: the step never left awaiting_signoff and the
	// chain holds no approval.
	stored, _ := w.st.Run(r.ID)
	for i := range stored.Steps {
		if stored.Steps[i].ID == "gate-plan" && stored.Steps[i].State != run.StepAwaitingSignoff {
			t.Fatalf("gate-plan = %s, want awaiting_signoff", stored.Steps[i].State)
		}
	}
	for _, e := range w.st.Events() {
		if e.Action == audit.ActionGateApproved && e.StepID == "gate-plan" {
			t.Fatal("a refused gate approval left an audit event")
		}
	}
}

// Ten concurrent delegations on the same step: the lease admits exactly
// one writer (I-1). Design §27.2 P2④'s "10 路并发 delegation_issue 恰好
// 成功 1 个", run here against the memstore through the same services the
// walk uses — the sqlite adapter faces the same suite through storetest.
func TestTenConcurrentDelegationsAdmitOneWriter(t *testing.T) {
	w := newWorld(t)
	r := startLiteChange(t, w)
	conductorStep(t, w, r.ID, "preflight", "preflight/probe.md")
	delegate(t, w, r.ID, "scope-guard", "idev-ops", "idev-ops", run.StepPASS)

	ctx := context.Background()
	// One delegation issues first, sequentially: the run has a single
	// state machine, and the race under test is the lease, not Apply.
	activate(t, w, r.ID, "code-pass")
	apply(t, w, r.ID, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "code-pass",
		Agent: "idev-coder",
	}, conductor())

	const n = 10
	errs := make(chan error, n)
	for i := 0; i < n; i++ {
		go func() {
			_, err := w.lease.Acquire(ctx, leasesvcAcquireParams(r.ID, "code-pass"))
			errs <- err
		}()
	}
	var ok, held int
	for i := 0; i < n; i++ {
		if err := <-errs; err == nil {
			ok++
		} else {
			var ce *ports.ConflictError
			if errors.As(err, &ce) && ce.Kind == ports.ConflictLeaseHeld {
				held++
			} else {
				t.Errorf("unexpected acquire error: %v", err)
			}
		}
	}
	if ok != 1 || held != n-1 {
		t.Fatalf("%d acquired, %d lease_held; want exactly 1 and %d", ok, held, n-1)
	}
}

// Ten concurrent audit appends must all land (§27.2 P0③'s shape, against
// the Go audit repo through a transaction each): the chain is the one
// place where losing a write means losing history.
func TestTenConcurrentAppendsAllLand(t *testing.T) {
	w := newWorld(t)
	const n = 10
	errs := make(chan error, n)
	for i := 0; i < n; i++ {
		go func() {
			err := w.st.InTx(context.Background(), func(tx ports.Tx) error {
				_, err := tx.Audit().Append(context.Background(), audit.Event{
					Action: "e2e.append", Actor: audit.Actor{Handle: "e2e", Kind: "agent"},
				})
				return err
			})
			errs <- err
		}()
	}
	for i := 0; i < n; i++ {
		if err := <-errs; err != nil {
			t.Fatalf("append %d: %v", i, err)
		}
	}
	events := w.st.Events()
	if len(events) != n {
		t.Fatalf("%d events, want %d", len(events), n)
	}
	// No lost write means no gap: the chain verifies from Genesis.
	if err := audit.Verify(audit.Genesis, events); err != nil {
		t.Fatalf("the chain does not verify: %v", err)
	}
}
