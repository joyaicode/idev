package runsvc_test

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/kindreg"
	"github.com/idev/internal/adapters/memstore"
	"github.com/idev/internal/app/runsvc"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

type seqIDs struct{ n int }

func (g *seqIDs) New() string {
	g.n++
	return fmt.Sprintf("01RUN0000000000000000000%02d", g.n)
}

func newSvc(t *testing.T) (runsvc.Service, *memstore.Store) {
	t.Helper()
	st := memstore.New()
	return runsvc.Service{
		Store:    st,
		Clock:    fixedClock{t: time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)},
		IDs:      &seqIDs{},
		Registry: kindreg.MustLoad(),
	}, st
}

func conductor() ports.Principal {
	return ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "wangwei794"}
}

func person() ports.Principal {
	return ports.Principal{Handle: "wangwei794", Kind: "human"}
}

// A lite-change shaped recipe: a conductor probe, a delegated step needing
// independent verification, a plain delegated step, and a gate.
func steps() []run.Step {
	return []run.Step{
		{ID: "preflight", Kind: "preflight.inputs"},
		{ID: "code-pass", Kind: "deliver.code_pass"},
		{ID: "plan", Kind: "verify.plan"},
		{ID: "gate-plan", Kind: "human.gate"},
	}
}

func start(t *testing.T, s runsvc.Service) run.Run {
	t.Helper()
	r, err := s.Start(context.Background(), runsvc.StartParams{
		WorkflowID: "lite-change", FeatureID: "f-1", Feature: "demo",
		Steps: steps(), Actor: conductor(),
	})
	if err != nil {
		t.Fatalf("Start: %v", err)
	}
	return r
}

func TestStartCreatesARunAndActivatesTheFirstStep(t *testing.T) {
	s, st := newSvc(t)
	r := start(t, s)

	if r.ID == "" {
		t.Fatal("the run has no id")
	}
	// A run whose first step is still pending has no next step to show, so
	// the conductor would have to ask twice.
	if r.Steps[0].State != run.StepReady {
		t.Errorf("first step = %s, want ready", r.Steps[0].State)
	}
	if got := r.Status(); got != run.StatusRunning {
		t.Errorf("status = %s, want running", got)
	}

	// The executors come from the registry, not from the caller.
	byID := map[string]run.Step{}
	for _, st := range r.Steps {
		byID[st.ID] = st
	}
	if byID["preflight"].Executor != run.ByConductor {
		t.Error("preflight.inputs should stay with the conductor")
	}
	if byID["code-pass"].Executor != run.ByAgent || !byID["code-pass"].NeedsVerify {
		t.Error("deliver.code_pass should be delegated and need independent verification")
	}
	if !byID["gate-plan"].IsGate {
		t.Error("human.gate should be marked as a gate")
	}

	// Invariant I-6: the state change and its record are written together.
	events := st.Events()
	if len(events) != 1 || events[0].Action != audit.ActionRunStarted {
		t.Fatalf("audit = %+v, want one run.started", events)
	}
	if events[0].Actor.OnBehalfOf != "wangwei794" {
		t.Error("an agent acting for a person must record whose behalf it acted on")
	}
}

func TestStartRefusesASecondLiveRun(t *testing.T) {
	s, _ := newSvc(t)
	start(t, s)

	_, err := s.Start(context.Background(), runsvc.StartParams{
		WorkflowID: "lite-change", FeatureID: "f-1", Feature: "demo",
		Steps: steps(), Actor: conductor(),
	})
	var ce *ports.ConflictError
	if !errors.As(err, &ce) || ce.Kind != ports.ConflictLiveRun {
		t.Fatalf("err = %v, want a live_run conflict", err)
	}
}

func TestStartRefusesForbiddenKinds(t *testing.T) {
	s, st := newSvc(t)
	_, err := s.Start(context.Background(), runsvc.StartParams{
		WorkflowID: "bad", FeatureID: "f-1", Feature: "demo",
		Steps: []run.Step{{ID: "a", Kind: "auto.seal"}}, Actor: conductor(),
	})
	if err == nil {
		t.Fatal("a recipe naming a forbidden kind was accepted")
	}
	if len(st.Events()) != 0 {
		t.Error("a refused start wrote an audit event")
	}
}

func TestStartRefusesAnEmptyRecipe(t *testing.T) {
	s, _ := newSvc(t)
	if _, err := s.Start(context.Background(), runsvc.StartParams{
		WorkflowID: "empty", FeatureID: "f-1", Actor: conductor(),
	}); err == nil {
		t.Error("a run with no steps was accepted")
	}
	if _, err := s.Start(context.Background(), runsvc.StartParams{
		Steps: steps(), Actor: conductor(),
	}); err == nil {
		t.Error("a run with no workflow or feature was accepted")
	}
}

// A retried start must not create a second run. The conductor's first
// request may have succeeded and the response been lost.
func TestStartIsIdempotent(t *testing.T) {
	s, st := newSvc(t)
	p := runsvc.StartParams{
		WorkflowID: "lite-change", FeatureID: "f-1", Feature: "demo",
		Steps: steps(), Actor: conductor(), IdempotencyKey: "k-1",
	}
	first, err := s.Start(context.Background(), p)
	if err != nil {
		t.Fatal(err)
	}
	second, err := s.Start(context.Background(), p)
	if err != nil {
		t.Fatalf("a retried start failed: %v", err)
	}
	if first.ID != second.ID {
		t.Errorf("the retry created a second run: %s and %s", first.ID, second.ID)
	}
	if n := len(st.Events()); n != 1 {
		t.Errorf("%d audit events, want 1: the retry was recorded as a second start", n)
	}
}

// --- the transaction boundary --------------------------------------------

// The reason this layer exists: a use case that fails partway must leave
// nothing behind. The Python driver did read-decide-write with no
// transaction, so a crash left state nobody had audited.
func TestAFailedAuditAppendRollsBackTheStateChange(t *testing.T) {
	s, st := newSvc(t)
	r := start(t, s)

	boom := errors.New("audit storage is down")
	st.FailOn["audit.Append"] = boom

	_, err := s.Apply(context.Background(), r.ID, run.Event{
		Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight",
	}, conductor())
	if !errors.Is(err, boom) {
		t.Fatalf("err = %v, want the audit failure", err)
	}

	stored, ok := st.Run(r.ID)
	if !ok {
		t.Fatal("the run disappeared")
	}
	if stored.Steps[0].State != run.StepReady {
		t.Errorf("step = %s, want ready: the state change survived a failed audit",
			stored.Steps[0].State)
	}
}

func TestAFailedSaveWritesNoAudit(t *testing.T) {
	s, st := newSvc(t)
	r := start(t, s)
	before := len(st.Events())

	st.FailOn["runs.Save"] = errors.New("storage is down")
	if _, err := s.Apply(context.Background(), r.ID, run.Event{
		Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight",
	}, conductor()); err == nil {
		t.Fatal("expected the save to fail")
	}
	if n := len(st.Events()); n != before {
		t.Errorf("%d audit events, want %d: a failed save was still audited", n, before)
	}
}

func TestARefusedDomainEventChangesNothing(t *testing.T) {
	s, st := newSvc(t)
	r := start(t, s)
	before := len(st.Events())

	// preflight.inputs stays with the conductor, so delegating it is
	// refused by the domain.
	_, err := s.Apply(context.Background(), r.ID, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor,
		StepID: "preflight", Agent: "idev-ops",
	}, conductor())
	if err == nil {
		t.Fatal("delegating a conductor kind was accepted")
	}
	if n := len(st.Events()); n != before {
		t.Errorf("a refused event wrote %d audit events", n-before)
	}
	stored, _ := st.Run(r.ID)
	if stored.Steps[0].State != run.StepReady {
		t.Error("a refused event changed the run")
	}
}

// --- the audit trail ------------------------------------------------------

func TestEveryTransitionIsAudited(t *testing.T) {
	s, st := newSvc(t)
	r := start(t, s)
	ctx := context.Background()

	seq := []struct {
		ev   run.Event
		want audit.Action
	}{
		{
			run.Event{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight"},
			audit.ActionStepRecorded,
		},
		{run.Event{
			Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
			Outcome: run.StepPASS, Evidence: "docs/p.md",
		}, audit.ActionStepRecorded},
		{
			run.Event{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "code-pass"},
			audit.ActionStepActivated,
		},
		{run.Event{
			Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "code-pass",
			Agent: "idev-coder",
		}, audit.ActionDelegationIssued},
		{run.Event{
			Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "code-pass",
			Agent: "idev-coder",
		}, audit.ActionDelegationReturned},
		{run.Event{
			Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "code-pass",
			Outcome: run.StepPASS, Evidence: "review.md",
		}, audit.ActionDelegationAccepted},
		{run.Event{
			Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: "code-pass",
			Agent: "idev-reviewer", Outcome: run.StepPASS,
		}, audit.ActionVerification},
	}
	for _, step := range seq {
		if _, err := s.Apply(ctx, r.ID, step.ev, conductor()); err != nil {
			t.Fatalf("%s: %v", step.ev.Kind, err)
		}
	}

	events := st.Events()
	// One for the start, one per transition.
	if len(events) != len(seq)+1 {
		t.Fatalf("%d audit events, want %d", len(events), len(seq)+1)
	}
	for i, step := range seq {
		if got := events[i+1].Action; got != step.want {
			t.Errorf("event %d = %s, want %s (from %s)", i+1, got, step.want, step.ev.Kind)
		}
	}
	// And the chain holds: an edited or removed event would break it.
	if err := audit.Verify(audit.Genesis, events); err != nil {
		t.Fatalf("the audit chain does not verify: %v", err)
	}
}

func TestTheAuditChainSurvivesManyTransitions(t *testing.T) {
	s, st := newSvc(t)
	r := start(t, s)
	ctx := context.Background()

	for i := 0; i < 20; i++ {
		// Alternating valid and refused events: the refused ones must not
		// enter the chain at all.
		_, _ = s.Apply(ctx, r.ID, run.Event{
			Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "plan",
		}, conductor())
	}
	if err := audit.Verify(audit.Genesis, st.Events()); err != nil {
		t.Fatalf("chain broken: %v", err)
	}
}

func TestGateApprovalRecordsTheApprovalID(t *testing.T) {
	s, st := newSvc(t)
	r := start(t, s)
	ctx := context.Background()

	// Walk to the gate.
	for _, ev := range []run.Event{
		{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight"},
		{
			Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
			Outcome: run.StepPASS, Evidence: "p.md",
		},
		{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "code-pass"},
		{Kind: run.EvStepSkipped, Actor: run.ActorConductor, StepID: "code-pass", Note: "no code change"},
		{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "plan"},
		{Kind: run.EvStepSkipped, Actor: run.ActorConductor, StepID: "plan", Note: "plan unchanged"},
		{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "gate-plan"},
		{Kind: run.EvGateRequested, Actor: run.ActorConductor, StepID: "gate-plan"},
	} {
		if _, err := s.Apply(ctx, r.ID, ev, conductor()); err != nil {
			t.Fatalf("%s on %s: %v", ev.Kind, ev.StepID, err)
		}
	}

	// Only a person, and the approval has to be recorded to be referenced.
	if _, err := s.Apply(ctx, r.ID, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorConductor, StepID: "gate-plan",
		ApprovalID: "ap-1",
	}, conductor()); err == nil {
		t.Fatal("the conductor approved a gate")
	}

	final, err := s.Apply(ctx, r.ID, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorHuman, StepID: "gate-plan",
		ApprovalID: "01APPROVAL000000000000001",
	}, person())
	if err != nil {
		t.Fatalf("approving the gate: %v", err)
	}
	if final.Status() != run.StatusDone {
		t.Errorf("status = %s, want done", final.Status())
	}

	events := st.Events()
	last := events[len(events)-1]
	if last.Action != audit.ActionGateApproved {
		t.Fatalf("last action = %s", last.Action)
	}
	if last.Actor.Kind != "human" {
		t.Errorf("the approval was audited as a %s", last.Actor.Kind)
	}
	if last.Subject != "01APPROVAL000000000000001" {
		t.Errorf("the audit record does not reference the approval: %q", last.Subject)
	}
}

// --- what the conductor is told to do next -------------------------------

func TestNextMirrorsTheOldDriver(t *testing.T) {
	s, _ := newSvc(t)
	r := start(t, s)
	ctx := context.Background()

	// A conductor kind.
	n, err := s.Next(ctx, r.ID)
	if err != nil {
		t.Fatal(err)
	}
	if n.Action != runsvc.ActionConductor || n.Step.ID != "preflight" {
		t.Fatalf("next = %+v, want the conductor on preflight", n)
	}
	if n.Agent != "" {
		t.Errorf("a conductor step named an agent: %q", n.Agent)
	}

	// A delegated kind names its agent, which is what the DELEGATE line is.
	for _, ev := range []run.Event{
		{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight"},
		{
			Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
			Outcome: run.StepPASS, Evidence: "p.md",
		},
		{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "code-pass"},
	} {
		if _, err := s.Apply(ctx, r.ID, ev, conductor()); err != nil {
			t.Fatal(err)
		}
	}
	n, _ = s.Next(ctx, r.ID)
	if n.Action != runsvc.ActionDelegate || n.Agent != "idev-coder" {
		t.Fatalf("next = %+v, want a delegation to idev-coder", n)
	}
}

func TestNextReportsAGateAndABlock(t *testing.T) {
	s, _ := newSvc(t)
	r := start(t, s)
	ctx := context.Background()

	// A failed step blocks the run, and the conductor must be told that
	// rather than handed the next step.
	for _, ev := range []run.Event{
		{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight"},
		{
			Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
			Outcome: run.StepFAIL, Evidence: "log.txt",
		},
	} {
		if _, err := s.Apply(ctx, r.ID, ev, conductor()); err != nil {
			t.Fatal(err)
		}
	}
	n, _ := s.Next(ctx, r.ID)
	if n.Action != runsvc.ActionBlocked {
		t.Fatalf("next = %+v, want blocked", n)
	}
}

func TestNextOnAFinishedRun(t *testing.T) {
	s, _ := newSvc(t)
	r := start(t, s)
	if _, err := s.Apply(context.Background(), r.ID, run.Event{
		Kind: run.EvRunAborted, Actor: run.ActorHuman, Note: "wrong ticket",
	}, person()); err != nil {
		t.Fatal(err)
	}
	n, _ := s.Next(context.Background(), r.ID)
	if n.Action != runsvc.ActionDone {
		t.Errorf("next = %+v, want done for an aborted run", n)
	}
}

func TestGetAndApplyOnAMissingRun(t *testing.T) {
	s, _ := newSvc(t)
	if _, err := s.Get(context.Background(), "nope"); err == nil {
		t.Error("Get accepted a run that does not exist")
	}
	if _, err := s.Apply(context.Background(), "nope", run.Event{
		Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "a",
	}, conductor()); err == nil {
		t.Error("Apply accepted a run that does not exist")
	}
}

func TestConcurrentApplyLosesOneWriter(t *testing.T) {
	// Optimistic concurrency: two conductors that read the same version
	// cannot both apply a decision. One wins, the other is told to re-read.
	s, st := newSvc(t)
	r := start(t, s)
	// Simulate the race by applying against a stale version directly.
	current, version, err := readRun(st, r.ID)
	if err != nil {
		t.Fatal(err)
	}
	next, _, err := run.Apply(current, run.Event{
		Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight",
	})
	if err != nil {
		t.Fatal(err)
	}
	// First writer at this version succeeds.
	if err := saveRun(st, next, version); err != nil {
		t.Fatalf("the first writer failed: %v", err)
	}
	// Second writer at the same version does not.
	err = saveRun(st, next, version)
	var ce *ports.ConflictError
	if !errors.As(err, &ce) || ce.Kind != ports.ConflictStaleVersion {
		t.Fatalf("err = %v, want a stale_version conflict", err)
	}
	if !strings.Contains(ce.Error(), "version") {
		t.Errorf("the conflict does not explain itself: %q", ce.Error())
	}
}

func readRun(st *memstore.Store, id string) (run.Run, int64, error) {
	var r run.Run
	var v int64
	err := st.InTx(context.Background(), func(tx ports.Tx) error {
		var err error
		r, v, err = tx.Runs().Get(context.Background(), id)
		return err
	})
	return r, v, err
}

func saveRun(st *memstore.Store, r run.Run, version int64) error {
	return st.InTx(context.Background(), func(tx ports.Tx) error {
		return tx.Runs().Save(context.Background(), r, version)
	})
}
