package run_test

import (
	"errors"
	"testing"

	"pgregory.net/rapid"

	"github.com/idev/internal/domain/run"
)

// A lite-change shaped run: a conductor probe, a delegated step that needs
// independent verification, and a gate.
func newRun() run.Run {
	return run.Run{
		ID:         "01TESTRUN",
		WorkflowID: "lite-change",
		Feature:    "demo",
		Steps: []run.Step{
			{ID: "preflight", Kind: "preflight.inputs", Executor: run.ByConductor, State: run.StepPending},
			{ID: "code-pass", Kind: "deliver.code_pass", Executor: run.ByAgent, NeedsVerify: true, State: run.StepPending},
			{ID: "plan", Kind: "verify.plan", Executor: run.ByAgent, State: run.StepPending},
			{ID: "gate-plan", Kind: "human.gate", Executor: run.ByConductor, IsGate: true, State: run.StepPending},
		},
	}
}

func must(t *testing.T, r run.Run, ev run.Event) run.Run {
	t.Helper()
	out, effects, err := run.Apply(r, ev)
	if err != nil {
		t.Fatalf("%s on %s: %v", ev.Kind, ev.StepID, err)
	}
	if len(effects) == 0 {
		t.Errorf("%s produced no effects; nothing would be audited", ev.Kind)
	}
	return out
}

func mustFail(t *testing.T, r run.Run, ev run.Event, why string) {
	t.Helper()
	out, effects, err := run.Apply(r, ev)
	if err == nil {
		t.Fatalf("%s should have been refused (%s)", ev.Kind, why)
	}
	// The whole point of returning the input on refusal.
	if out.Status() != r.Status() || len(effects) != 0 {
		t.Errorf("%s was refused but changed the run (%s)", ev.Kind, why)
	}
}

func state(t *testing.T, r run.Run, id string) run.StepState {
	t.Helper()
	for _, s := range r.Steps {
		if s.ID == id {
			return s.State
		}
	}
	t.Fatalf("no step %q", id)
	return ""
}

// --- the happy path through all four step shapes ---------------------------

func TestFullRunReachesDone(t *testing.T) {
	r := newRun()
	if r.Status() != run.StatusPending {
		t.Fatalf("a fresh run is %s, want pending", r.Status())
	}

	r = must(t, r, run.Event{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "preflight"})
	if r.Status() != run.StatusRunning {
		t.Fatalf("status = %s, want running", r.Status())
	}
	r = must(t, r, run.Event{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight"})
	r = must(t, r, run.Event{
		Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
		Outcome: run.StepPASS, Evidence: "docs/probe.md",
	})

	// A delegated step that needs a second pair of eyes.
	r = must(t, r, run.Event{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "code-pass"})
	r = must(t, r, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "code-pass", Agent: "idev-coder",
	})
	r = must(t, r, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "code-pass", Agent: "idev-coder",
	})
	r = must(t, r, run.Event{
		Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "code-pass",
		Outcome: run.StepPASS, Evidence: "review.md",
	})
	if got := state(t, r, "code-pass"); got != run.StepVerifying {
		t.Fatalf("code-pass = %s, want verifying: its PASS is not the writer's to declare", got)
	}
	r = must(t, r, run.Event{
		Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: "code-pass",
		Agent: "idev-reviewer", Outcome: run.StepPASS, Evidence: "review.md",
	})

	// A plain delegated step.
	r = must(t, r, run.Event{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "plan"})
	r = must(t, r, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "plan", Agent: "idev-verifier",
	})
	r = must(t, r, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "plan", Agent: "idev-verifier",
	})
	r = must(t, r, run.Event{
		Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "plan",
		Outcome: run.StepPASS, Evidence: "verify/plan.yaml",
	})

	// The gate.
	r = must(t, r, run.Event{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "gate-plan"})
	r = must(t, r, run.Event{Kind: run.EvGateRequested, Actor: run.ActorConductor, StepID: "gate-plan"})
	if r.Status() != run.StatusAwaitingHuman {
		t.Fatalf("status = %s, want awaiting_human — the old projection could not say this", r.Status())
	}
	r = must(t, r, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorHuman, StepID: "gate-plan", ApprovalID: "ap-1",
	})

	if r.Status() != run.StatusDone {
		t.Fatalf("status = %s, want done", r.Status())
	}
	if r.Current() != nil {
		t.Errorf("a finished run still has a current step: %s", r.Current().ID)
	}
}

// --- guards, one per row ---------------------------------------------------

func TestStepsActivateInOrder(t *testing.T) {
	r := newRun()
	mustFail(t, r, run.Event{
		Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "plan",
	}, "preflight has not finished")
}

func TestOnlyTheConductorDelegates(t *testing.T) {
	r := ready(t, newRun(), "code-pass")
	mustFail(t, r, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorAgent, StepID: "code-pass", Agent: "idev-coder",
	}, "an agent cannot delegate to itself")
}

func TestConductorKindsAreNotDelegated(t *testing.T) {
	r := ready(t, newRun(), "preflight")
	mustFail(t, r, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "preflight", Agent: "idev-ops",
	}, "preflight.inputs stays with the conductor")
}

func TestOnlyTheHolderReturns(t *testing.T) {
	r := delegated(t, newRun(), "code-pass", "idev-coder")
	mustFail(t, r, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "code-pass", Agent: "idev-verifier",
	}, "a different agent submitted the report")
}

func TestPassWithoutEvidenceIsRefused(t *testing.T) {
	r := delegated(t, newRun(), "plan", "idev-verifier")
	r = must(t, r, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "plan", Agent: "idev-verifier",
	})
	mustFail(t, r, run.Event{
		Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "plan", Outcome: run.StepPASS,
	}, "a PASS with no evidence path does not count")
}

func TestNoEventSetsAUTO(t *testing.T) {
	r := delegated(t, newRun(), "plan", "idev-verifier")
	r = must(t, r, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "plan", Agent: "idev-verifier",
	})
	mustFail(t, r, run.Event{
		Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "plan",
		Outcome: run.StepAUTO, Evidence: "verify/plan-check.log",
	}, "an agent's report cannot pass a step on machine checks")

	c := ready(t, newRun(), "preflight")
	c = must(t, c, run.Event{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight"})
	mustFail(t, c, run.Event{
		Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
		Outcome: run.StepAUTO, Evidence: "docs/probe.md",
	}, "the conductor cannot record AUTO either; only the driver's gate path does")
}

func TestWriterCannotVerifyItsOwnWork(t *testing.T) {
	r := verifying(t, newRun(), "code-pass", "idev-coder")
	mustFail(t, r, run.Event{
		Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: "code-pass",
		Agent: "idev-coder", Outcome: run.StepPASS,
	}, "that is what independent verification means")

	// Someone else may.
	ok := must(t, r, run.Event{
		Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: "code-pass",
		Agent: "idev-reviewer", Outcome: run.StepPASS,
	})
	if got := state(t, ok, "code-pass"); got != run.StepPASS {
		t.Fatalf("code-pass = %s, want PASS", got)
	}
}

func TestOnlyAPersonApprovesAGate(t *testing.T) {
	r := awaitingSignoff(t, newRun(), "gate-plan")
	for _, actor := range []run.Actor{run.ActorConductor, run.ActorAgent, run.ActorSystem} {
		mustFail(t, r, run.Event{
			Kind: run.EvGateApproved, Actor: actor, StepID: "gate-plan", ApprovalID: "ap-1",
		}, "only a person approves")
	}
}

func TestApprovalMustBeRecorded(t *testing.T) {
	r := awaitingSignoff(t, newRun(), "gate-plan")
	mustFail(t, r, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorHuman, StepID: "gate-plan",
	}, "an approval with no id cannot be referenced or verified later")
}

func TestTheConductorCannotRecordAGate(t *testing.T) {
	r := ready(t, newRun(), "gate-plan")
	// It cannot even start one as a conductor step.
	mustFail(t, r, run.Event{
		Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "gate-plan",
	}, "a gate is requested, not started")
}

func TestGateExpiryReturnsToReadyNotFailed(t *testing.T) {
	r := awaitingSignoff(t, newRun(), "gate-plan")
	out := must(t, r, run.Event{Kind: run.EvGateExpired, Actor: run.ActorSystem, StepID: "gate-plan"})
	if got := state(t, out, "gate-plan"); got != run.StepReady {
		t.Fatalf("gate-plan = %s, want ready: an unanswered question is not a refusal", got)
	}
	if out.Status() == run.StatusBlocked {
		t.Error("an expired gate must not block the run")
	}
}

func TestSkippingAGateNeedsAnApprovalAndAMatchingDigest(t *testing.T) {
	r := ready(t, newRun(), "gate-plan")
	mustFail(t, r, run.Event{
		Kind: run.EvStepSkipped, Actor: run.ActorConductor, StepID: "gate-plan", Note: "already signed",
	}, "no approval referenced")
	mustFail(t, r, run.Event{
		Kind: run.EvStepSkipped, Actor: run.ActorConductor, StepID: "gate-plan",
		ApprovalID: "ap-old", DigestMatches: false,
	}, "the content changed since that approval")

	out := must(t, r, run.Event{
		Kind: run.EvStepSkipped, Actor: run.ActorConductor, StepID: "gate-plan",
		ApprovalID: "ap-old", DigestMatches: true,
	})
	if got := state(t, out, "gate-plan"); got != run.StepSKIPPED {
		t.Fatalf("gate-plan = %s, want SKIPPED", got)
	}
}

func TestShellConfirmedRecordsWhatItRan(t *testing.T) {
	r := newRun()
	r.Steps = append(r.Steps, run.Step{
		ID: "sh", Kind: "shell.confirmed", Executor: run.ByConductor, State: run.StepConductorActive,
	})
	mustFail(t, r, run.Event{
		Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "sh",
		Outcome: run.StepPASS, Evidence: "log.txt",
	}, "no command or exit code")

	zero := 0
	must(t, r, run.Event{
		Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "sh",
		Outcome: run.StepPASS, Evidence: "log.txt", Command: "make build", ExitCode: &zero,
	})
}

func TestFailBlocksTheRunAndRetryUnblocksIt(t *testing.T) {
	r := delegated(t, newRun(), "code-pass", "idev-coder")
	r = must(t, r, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "code-pass", Agent: "idev-coder",
	})
	r = must(t, r, run.Event{
		Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "code-pass",
		Outcome: run.StepFAIL, Evidence: "log.txt",
	})
	if r.Status() != run.StatusBlocked {
		t.Fatalf("status = %s, want blocked", r.Status())
	}

	mustFail(t, r, run.Event{
		Kind: run.EvStepRetried, Actor: run.ActorConductor, StepID: "code-pass",
	}, "a retry needs a note")

	before := r.Steps[1].Attempt
	out := must(t, r, run.Event{
		Kind: run.EvStepRetried, Actor: run.ActorConductor, StepID: "code-pass", Note: "fixed the import",
	})
	if out.Status() != run.StatusRunning {
		t.Fatalf("status = %s, want running after a retry", out.Status())
	}
	if out.Steps[1].Attempt != before+1 {
		t.Errorf("attempt = %d, want %d", out.Steps[1].Attempt, before+1)
	}
	if len(out.Revisions) != 1 {
		t.Error("a retry must be written into revisions")
	}
}

func TestOneBlockedStepAtATime(t *testing.T) {
	r := newRun()
	r.Steps[0].State = run.StepFAIL
	r.Steps[1].State = run.StepBLOCKED
	mustFail(t, r, run.Event{
		Kind: run.EvStepRetried, Actor: run.ActorConductor, StepID: "preflight", Note: "try again",
	}, "another step is still stopped")
}

func TestAGateCannotBeVerifiedIntoAnApproval(t *testing.T) {
	// Found by TestPropertyGatesAndStatusHoldUnderAnySequence. A gate cannot
	// reach `verifying` in a real run — it is never delegated — but a state
	// loaded from storage can say anything, and this is the one invariant
	// not to leave resting on "unreachable in practice".
	r := newRun()
	for i := range r.Steps {
		if r.Steps[i].ID == "gate-plan" {
			r.Steps[i].State = run.StepVerifying
		}
	}
	mustFail(t, r, run.Event{
		Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: "gate-plan",
		Agent: "idev-reviewer", Outcome: run.StepPASS,
	}, "an agent verified a gate into an approval")

	// And the same through every other event that can write PASS.
	for _, ev := range []run.Event{
		{
			Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "gate-plan",
			Outcome: run.StepPASS, Evidence: "x.md",
		},
		{
			Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "gate-plan",
			Outcome: run.StepPASS, Evidence: "x.md",
		},
	} {
		mustFail(t, r, ev, "a gate reached PASS via "+string(ev.Kind))
	}
}

func TestAGateCannotBeAmendedIntoAnApproval(t *testing.T) {
	r := newRun()
	r.Steps[3].State = run.StepFAIL
	mustFail(t, r, run.Event{
		Kind: run.EvStepAmended, Actor: run.ActorConductor, StepID: "gate-plan",
		Outcome: run.StepPASS, Note: "the person said yes later",
	}, "a signature comes from a person through the gate, not from an amendment")
}

func TestAmendingNeedsANoteAndRecordsTheOldValue(t *testing.T) {
	r := newRun()
	r.Steps[0].State = run.StepPASS
	mustFail(t, r, run.Event{
		Kind: run.EvStepAmended, Actor: run.ActorConductor, StepID: "preflight", Outcome: run.StepFAIL,
	}, "changing a recorded step needs a note")

	out := must(t, r, run.Event{
		Kind: run.EvStepAmended, Actor: run.ActorConductor, StepID: "preflight",
		Outcome: run.StepFAIL, Note: "the probe was wrong",
	})
	if len(out.Revisions) != 1 || out.Revisions[0].From != run.StepPASS {
		t.Errorf("the old value was not kept: %+v", out.Revisions)
	}
}

func TestLeaseExpiryFreesTheStep(t *testing.T) {
	r := delegated(t, newRun(), "code-pass", "idev-coder")
	mustFail(t, r, run.Event{
		Kind: run.EvLeaseExpired, Actor: run.ActorConductor, StepID: "code-pass",
	}, "lease expiry is the sweeper's call")

	out := must(t, r, run.Event{Kind: run.EvLeaseExpired, Actor: run.ActorSystem, StepID: "code-pass"})
	if got := state(t, out, "code-pass"); got != run.StepReady {
		t.Fatalf("code-pass = %s, want ready", got)
	}
	if out.Steps[1].Writer != "" {
		t.Error("the expired lease still names a writer")
	}
}

func TestBaselineDriftBlocksWithoutTouchingAStep(t *testing.T) {
	r := ready(t, newRun(), "code-pass")
	out := must(t, r, run.Event{Kind: run.EvBaselineDriftDetected, Actor: run.ActorSystem})
	if out.Status() != run.StatusBlocked {
		t.Fatalf("status = %s, want blocked", out.Status())
	}
	if got := state(t, out, "code-pass"); got != run.StepReady {
		t.Errorf("drift changed a step to %s; the steps are not what went wrong", got)
	}
	// Nothing proceeds while the sealed content is in question.
	mustFail(t, out, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "code-pass", Agent: "idev-coder",
	}, "the baseline drifted")
	// A step retry is not the way out: drift put no step into FAIL.
	mustFail(t, out, run.Event{
		Kind: run.EvStepRetried, Actor: run.ActorConductor, StepID: "code-pass", Note: "re-sealed",
	}, "drift is cleared by re-sealing, not by retrying a step")
	// Only the side that recomputed the manifest may say it matches again.
	mustFail(t, out, run.Event{
		Kind: run.EvBaselineRestored, Actor: run.ActorConductor,
	}, "clearing drift follows a recomputed manifest")

	cleared := must(t, out, run.Event{Kind: run.EvBaselineRestored, Actor: run.ActorSystem})
	if cleared.Status() != run.StatusRunning {
		t.Fatalf("status = %s, want running once the baseline matches again", cleared.Status())
	}
	must(t, cleared, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "code-pass", Agent: "idev-coder",
	})
	// And it cannot be cleared when there is nothing to clear.
	mustFail(t, cleared, run.Event{
		Kind: run.EvBaselineRestored, Actor: run.ActorSystem,
	}, "no drift outstanding")
}

func TestAbortNeedsANoteAndRespectsSignatures(t *testing.T) {
	r := ready(t, newRun(), "code-pass")
	mustFail(t, r, run.Event{Kind: run.EvRunAborted, Actor: run.ActorHuman}, "no note")
	mustFail(t, r, run.Event{
		Kind: run.EvRunAborted, Actor: run.ActorAgent, Note: "giving up",
	}, "an agent cannot abort a run")

	out := must(t, r, run.Event{Kind: run.EvRunAborted, Actor: run.ActorConductor, Note: "wrong ticket"})
	if out.Status() != run.StatusAborted {
		t.Fatalf("status = %s, want aborted", out.Status())
	}
	// Nothing happens after an abort.
	mustFail(t, out, run.Event{
		Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "plan",
	}, "the run is aborted")
}

func TestTheConductorCannotThrowAwayASignature(t *testing.T) {
	r := newRun()
	r.Steps[3].State = run.StepPASS
	r.Steps[3].IsGate = true
	mustFail(t, r, run.Event{
		Kind: run.EvRunAborted, Actor: run.ActorConductor, Note: "never mind",
	}, "this run has an approved gate")

	// A person still may.
	must(t, r, run.Event{Kind: run.EvRunAborted, Actor: run.ActorHuman, Note: "superseded"})
}

func TestUnknownStepAndEventAreRefused(t *testing.T) {
	r := newRun()
	mustFail(t, r, run.Event{
		Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "nope",
	}, "no such step")
	mustFail(t, r, run.Event{
		Kind: run.EventKind("Invented"), Actor: run.ActorConductor, StepID: "preflight",
	}, "unknown event")
}

func TestErrorNamesTheGuard(t *testing.T) {
	_, _, err := run.Apply(newRun(), run.Event{
		Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "plan",
	})
	var re *run.Error
	if !errors.As(err, &re) {
		t.Fatalf("error type = %T, want *run.Error", err)
	}
	if re.StepID != "plan" || re.Reason == "" {
		t.Errorf("refusal lacks context: %+v", re)
	}
}

func TestUnprovenLetsTheRunContinue(t *testing.T) {
	// "No runner for this dimension" is an honest outcome, not a failure.
	r := delegated(t, newRun(), "plan", "idev-verifier")
	r = must(t, r, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "plan", Agent: "idev-verifier",
	})
	out := must(t, r, run.Event{
		Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "plan",
		Outcome: run.StepUNPROVEN, Evidence: "report.md",
	})
	if out.Status() == run.StatusBlocked {
		t.Error("UNPROVEN must not block the run")
	}
	if !run.IsDone(run.StepUNPROVEN) || run.IsStop(run.StepUNPROVEN) {
		t.Error("UNPROVEN belongs to the done set")
	}
}

// --- every remaining guard, one row each -----------------------------------

// The refusals above are the ones worth a named test. These are the rest of
// the table: each row is a guard, and a row that stops failing means a guard
// was dropped.
func TestEveryGuardRefuses(t *testing.T) {
	zero := 0
	cases := []struct {
		name  string
		setup func(run.Run) run.Run
		event run.Event
	}{
		{
			name:  "activating a step that is already ready",
			setup: func(r run.Run) run.Run { return ready(t, r, "preflight") },
			event: run.Event{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "preflight"},
		},
		{
			name:  "delegating without naming an agent",
			setup: func(r run.Run) run.Run { return ready(t, r, "code-pass") },
			event: run.Event{Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "code-pass"},
		},
		{
			name:  "an agent accepting its own report",
			setup: func(r run.Run) run.Run { return returned(t, r, "plan", "idev-verifier") },
			event: run.Event{
				Kind: run.EvDelegationAccepted, Actor: run.ActorAgent, StepID: "plan",
				Outcome: run.StepPASS, Evidence: "x.md",
			},
		},
		{
			name:  "accepting with a non-terminal outcome",
			setup: func(r run.Run) run.Run { return returned(t, r, "plan", "idev-verifier") },
			event: run.Event{
				Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: "plan",
				Outcome: run.StepReady,
			},
		},
		{
			name:  "a verification with no verifier named",
			setup: func(r run.Run) run.Run { return verifying(t, r, "code-pass", "idev-coder") },
			event: run.Event{
				Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: "code-pass",
				Outcome: run.StepPASS,
			},
		},
		{
			name:  "a verification that is neither PASS nor FAIL",
			setup: func(r run.Run) run.Run { return verifying(t, r, "code-pass", "idev-coder") },
			event: run.Event{
				Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: "code-pass",
				Agent: "idev-reviewer", Outcome: run.StepUNPROVEN,
			},
		},
		{
			name:  "the conductor starting a delegated kind",
			setup: func(r run.Run) run.Run { return ready(t, r, "code-pass") },
			event: run.Event{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "code-pass"},
		},
		{
			name: "recording a conductor step with a non-terminal outcome",
			setup: func(r run.Run) run.Run {
				out := ready(t, r, "preflight")
				return must(t, out, run.Event{
					Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight",
				})
			},
			event: run.Event{
				Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
				Outcome: run.StepReady,
			},
		},
		{
			name: "a conductor PASS with no evidence",
			setup: func(r run.Run) run.Run {
				out := ready(t, r, "preflight")
				return must(t, out, run.Event{
					Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight",
				})
			},
			event: run.Event{
				Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
				Outcome: run.StepPASS,
			},
		},
		{
			name:  "requesting a gate on a step that is not one",
			setup: func(r run.Run) run.Run { return ready(t, r, "plan") },
			event: run.Event{Kind: run.EvGateRequested, Actor: run.ActorConductor, StepID: "plan"},
		},
		{
			name:  "a non-person rejecting a gate",
			setup: func(r run.Run) run.Run { return awaitingSignoff(t, r, "gate-plan") },
			event: run.Event{Kind: run.EvGateRejected, Actor: run.ActorConductor, StepID: "gate-plan"},
		},
		{
			name:  "the conductor expiring its own gate",
			setup: func(r run.Run) run.Run { return awaitingSignoff(t, r, "gate-plan") },
			event: run.Event{Kind: run.EvGateExpired, Actor: run.ActorConductor, StepID: "gate-plan"},
		},
		{
			name:  "skipping a plain step with no note",
			setup: func(r run.Run) run.Run { return ready(t, r, "plan") },
			event: run.Event{Kind: run.EvStepSkipped, Actor: run.ActorConductor, StepID: "plan"},
		},
		{
			name: "amending to a non-terminal outcome",
			setup: func(r run.Run) run.Run {
				out := r.Clone()
				out.Steps[0].State = run.StepPASS
				return out
			},
			event: run.Event{
				Kind: run.EvStepAmended, Actor: run.ActorConductor, StepID: "preflight",
				Outcome: run.StepReady, Note: "n",
			},
		},
		{
			name: "an agent amending a step",
			setup: func(r run.Run) run.Run {
				out := r.Clone()
				out.Steps[0].State = run.StepPASS
				return out
			},
			event: run.Event{
				Kind: run.EvStepAmended, Actor: run.ActorAgent, StepID: "preflight",
				Outcome: run.StepFAIL, Note: "n",
			},
		},
		{
			name:  "returning a step that was never delegated",
			setup: func(r run.Run) run.Run { return ready(t, r, "plan") },
			event: run.Event{
				Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "plan", Agent: "idev-verifier",
			},
		},
		{
			name: "drift on a finished run",
			setup: func(r run.Run) run.Run {
				out := r.Clone()
				for i := range out.Steps {
					out.Steps[i].State = run.StepPASS
				}
				return out
			},
			event: run.Event{Kind: run.EvBaselineDriftDetected, Actor: run.ActorSystem},
		},
		{
			name: "recording shell.confirmed with a command but no exit code",
			setup: func(r run.Run) run.Run {
				out := r.Clone()
				out.Steps = append(out.Steps, run.Step{
					ID: "sh", Kind: "shell.confirmed", Executor: run.ByConductor,
					State: run.StepConductorActive,
				})
				return out
			},
			event: run.Event{
				Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "sh",
				Outcome: run.StepPASS, Evidence: "log", Command: "make",
			},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			mustFail(t, tc.setup(newRun()), tc.event, tc.name)
		})
	}

	// And the counterpart that must succeed, so the rows above are not
	// passing for some unrelated reason.
	r := newRun()
	r.Steps = append(r.Steps, run.Step{
		ID: "sh", Kind: "shell.confirmed", Executor: run.ByConductor, State: run.StepConductorActive,
	})
	must(t, r, run.Event{
		Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "sh",
		Outcome: run.StepPASS, Evidence: "log", Command: "make", ExitCode: &zero,
	})
}

func TestBlockedConductorStepStopsTheRun(t *testing.T) {
	out := ready(t, newRun(), "preflight")
	out = must(t, out, run.Event{
		Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight",
	})
	out = must(t, out, run.Event{
		Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
		Outcome: run.StepBLOCKED, Evidence: "missing.md",
	})
	if out.Status() != run.StatusBlocked {
		t.Fatalf("status = %s, want blocked", out.Status())
	}
}

func TestFailedVerificationStopsTheRun(t *testing.T) {
	out := verifying(t, newRun(), "code-pass", "idev-coder")
	out = must(t, out, run.Event{
		Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: "code-pass",
		Agent: "idev-reviewer", Outcome: run.StepFAIL,
	})
	if out.Status() != run.StatusBlocked {
		t.Fatalf("status = %s, want blocked when the verifier refuses", out.Status())
	}
}

func TestAmendmentCanCarryNewEvidence(t *testing.T) {
	r := newRun()
	r.Steps[0].State = run.StepPASS
	out := must(t, r, run.Event{
		Kind: run.EvStepAmended, Actor: run.ActorMaintainer, StepID: "preflight",
		Outcome: run.StepPASS, Note: "better evidence", Evidence: "docs/new.md",
	})
	if out.Steps[0].Evidence != "docs/new.md" {
		t.Errorf("evidence = %q, want the amended path", out.Steps[0].Evidence)
	}
}

func TestStateSetHelpers(t *testing.T) {
	for _, s := range []run.StepState{run.StepPASS, run.StepSKIPPED, run.StepUNPROVEN} {
		if !run.IsDone(s) || !run.IsTerminal(s) || run.IsStop(s) {
			t.Errorf("%s should be done and terminal", s)
		}
	}
	for _, s := range []run.StepState{run.StepFAIL, run.StepBLOCKED} {
		if !run.IsStop(s) || !run.IsTerminal(s) || run.IsDone(s) {
			t.Errorf("%s should be a stop and terminal", s)
		}
	}
	for _, s := range []run.StepState{run.StepPending, run.StepReady, run.StepDelegated} {
		if run.IsTerminal(s) {
			t.Errorf("%s is not terminal", s)
		}
	}
}

func TestRunLevelRefusalHasNoStep(t *testing.T) {
	_, _, err := run.Apply(newRun(), run.Event{Kind: run.EvRunAborted, Actor: run.ActorHuman})
	if err == nil {
		t.Fatal("expected a refusal")
	}
	var re *run.Error
	if !errors.As(err, &re) {
		t.Fatalf("error type = %T", err)
	}
	if re.StepID != "" {
		t.Errorf("a run-level refusal named step %q", re.StepID)
	}
	if got := err.Error(); got == "" {
		t.Error("Error() is empty")
	}
}

func returned(t *testing.T, r run.Run, id, agent string) run.Run {
	t.Helper()
	out := delegated(t, r, id, agent)
	return must(t, out, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: id, Agent: agent,
	})
}

// --- properties ------------------------------------------------------------

// Whatever sequence of events arrives, a gate only ever reaches PASS through
// a human approval, and a run never reports done while a step is stopped.
//
// The run is seeded with an arbitrary per-step state rather than started from
// scratch. Walking from the beginning with random events almost never reaches
// a requested gate — the path to it is long and specific — so the earlier
// version of this test asserted things about states it never visited. Two
// mutations (letting the conductor approve a gate, letting an amendment
// become an approval) were caught only by the named tests above, which is how
// that was noticed.
func TestPropertyGatesAndStatusHoldUnderAnySequence(t *testing.T) {
	kinds := []run.EventKind{
		run.EvStepActivated, run.EvDelegationIssued, run.EvDelegationReturned,
		run.EvDelegationAccepted, run.EvVerificationRecorded, run.EvConductorStepStarted,
		run.EvConductorStepRecorded, run.EvGateRequested, run.EvGateApproved,
		run.EvGateRejected, run.EvGateExpired, run.EvStepSkipped, run.EvStepRetried,
		run.EvStepAmended, run.EvLeaseExpired, run.EvBaselineDriftDetected,
		run.EvBaselineRestored, run.EvRunAborted,
	}
	actors := []run.Actor{
		run.ActorConductor, run.ActorAgent, run.ActorHuman, run.ActorSystem, run.ActorMaintainer,
	}
	outcomes := []run.StepState{
		run.StepPASS, run.StepFAIL, run.StepUNPROVEN, run.StepSKIPPED, run.StepBLOCKED, run.StepReady,
	}
	anyState := []run.StepState{
		run.StepPending, run.StepReady, run.StepDelegated, run.StepConductorActive,
		run.StepAwaitingSignoff, run.StepReturned, run.StepVerifying,
		run.StepPASS, run.StepFAIL, run.StepUNPROVEN, run.StepSKIPPED, run.StepBLOCKED,
	}
	agents := []string{"idev-coder", "idev-reviewer", "idev-verifier", ""}
	ids := []string{"preflight", "code-pass", "plan", "gate-plan", "nope"}

	rapid.Check(t, func(t *rapid.T) {
		r := newRun()
		for i := range r.Steps {
			r.Steps[i].State = rapid.SampledFrom(anyState).Draw(t, "seed")
			if rapid.Bool().Draw(t, "hasWriter") {
				r.Steps[i].Writer = rapid.SampledFrom(agents).Draw(t, "writer")
			}
		}
		// A gate that starts PASS counts as already approved: this test
		// reasons about transitions, not about how the seed came to be.
		approved := map[string]bool{}
		for _, s := range r.Steps {
			if s.IsGate && s.State == run.StepPASS {
				approved[s.ID] = true
				// Keep the seed self-consistent with the invariant.
				for i := range r.Steps {
					if r.Steps[i].ID == s.ID {
						r.Steps[i].ApprovalID = "seed"
					}
				}
			}
		}

		for i := 0; i < rapid.IntRange(1, 40).Draw(t, "events"); i++ {
			ev := run.Event{
				Kind:          rapid.SampledFrom(kinds).Draw(t, "kind"),
				Actor:         rapid.SampledFrom(actors).Draw(t, "actor"),
				StepID:        rapid.SampledFrom(ids).Draw(t, "step"),
				Outcome:       rapid.SampledFrom(outcomes).Draw(t, "outcome"),
				Agent:         rapid.SampledFrom(agents).Draw(t, "agent"),
				Note:          rapid.SampledFrom([]string{"", "note"}).Draw(t, "note"),
				Evidence:      rapid.SampledFrom([]string{"", "ev.md"}).Draw(t, "evidence"),
				ApprovalID:    rapid.SampledFrom([]string{"", "ap-1"}).Draw(t, "approval"),
				DigestMatches: rapid.Bool().Draw(t, "digest"),
			}
			before := r
			next, _, err := run.Apply(r, ev)
			if err != nil {
				if next.Status() != before.Status() {
					t.Fatalf("a refused %s changed the run status", ev.Kind)
				}
				continue
			}

			for _, s := range next.Steps {
				if !s.IsGate || s.State != run.StepPASS {
					continue
				}
				// A gate is PASS: it must carry an approval, and the only
				// event that can have put it there is a human approval.
				if s.ApprovalID == "" {
					t.Fatalf("gate %s is PASS with no approval id (via %s)", s.ID, ev.Kind)
				}
				if !approved[s.ID] {
					if ev.Kind != run.EvGateApproved || ev.Actor != run.ActorHuman {
						t.Fatalf("gate %s reached PASS via %s by %s", s.ID, ev.Kind, ev.Actor)
					}
					approved[s.ID] = true
				}
			}

			// A writer never ends up as its own verifier.
			for _, s := range next.Steps {
				if s.Verifier != "" && s.Verifier == s.Writer {
					t.Fatalf("step %s was verified by its own writer %q", s.ID, s.Writer)
				}
			}

			// done and blocked are mutually exclusive, and done means every
			// step finished.
			switch next.Status() {
			case run.StatusDone:
				for _, s := range next.Steps {
					if !run.IsDone(s.State) {
						t.Fatalf("run is done while %s is %s", s.ID, s.State)
					}
				}
			case run.StatusBlocked:
				stopped := next.Drift
				for _, s := range next.Steps {
					if run.IsStop(s.State) {
						stopped = true
					}
				}
				if !stopped {
					t.Fatal("run is blocked with nothing stopped and no drift")
				}
			}

			// Current is always the first unfinished step.
			if cur := next.Current(); cur != nil {
				for _, s := range next.Steps {
					if s.ID == cur.ID {
						break
					}
					if !run.IsDone(s.State) {
						t.Fatalf("Current() = %s but %s is still %s", cur.ID, s.ID, s.State)
					}
				}
			}
			r = next
		}
	})
}

// --- helpers ---------------------------------------------------------------

func ready(t *testing.T, r run.Run, id string) run.Run {
	t.Helper()
	out := r.Clone()
	for i := range out.Steps {
		if out.Steps[i].ID == id {
			out.Steps[i].State = run.StepReady
			return out
		}
		out.Steps[i].State = run.StepPASS
	}
	t.Fatalf("no step %q", id)
	return r
}

func delegated(t *testing.T, r run.Run, id, agent string) run.Run {
	t.Helper()
	out := ready(t, r, id)
	return must(t, out, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: id, Agent: agent,
	})
}

func verifying(t *testing.T, r run.Run, id, agent string) run.Run {
	t.Helper()
	out := delegated(t, r, id, agent)
	out = must(t, out, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: id, Agent: agent,
	})
	return must(t, out, run.Event{
		Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: id,
		Outcome: run.StepPASS, Evidence: "review.md",
	})
}

func awaitingSignoff(t *testing.T, r run.Run, id string) run.Run {
	t.Helper()
	out := ready(t, r, id)
	return must(t, out, run.Event{Kind: run.EvGateRequested, Actor: run.ActorConductor, StepID: id})
}
