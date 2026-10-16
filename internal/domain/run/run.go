// Package run holds the run and step state machines: which step is next,
// what may happen to it, and when a run is blocked, waiting on a person, or
// finished.
//
// The event table is design §5.3 (E1–E18). Each guard in it is a rule the
// Python driver either enforced in one place and not another, or could not
// enforce at all because run.yaml was just a file anyone could write.
//
// One deliberate difference from the design's §5.1, which draws run status as
// a stored state with its own transitions: here it is *derived* from the
// steps, the way scripts/workflow.py already derived it. A stored status is a
// second source of truth for something the steps already determine, and the
// two desync exactly when it matters — a step recorded FAIL while the run
// header still says running is the shape of the bug this refactor exists to
// remove. Aborted and drift are the only flags that cannot be derived, so
// they are the only ones stored.
//
// Zero IO (see .golangci.yml, domain-pure): Apply is a pure function and the
// app layer performs the returned effects inside one transaction.
package run

import (
	"fmt"
)

// StepState is where one step is in its life. The six terminal values are
// the old STEP_STATUS set, unchanged, because run.yaml still projects them.
type StepState string

// Step states. The first six are in-flight; the last six are terminal and
// are exactly the old STEP_STATUS values.
const (
	StepPending         StepState = "pending"
	StepReady           StepState = "ready"
	StepDelegated       StepState = "delegated"
	StepConductorActive StepState = "conductor_active"
	StepAwaitingSignoff StepState = "awaiting_signoff"
	StepReturned        StepState = "returned"
	StepVerifying       StepState = "verifying"

	StepPASS     StepState = "PASS"
	StepFAIL     StepState = "FAIL"
	StepUNPROVEN StepState = "UNPROVEN"
	StepSKIPPED  StepState = "SKIPPED"
	StepBLOCKED  StepState = "BLOCKED"
)

// done is the set that lets the next step activate: the step is over and did
// not stop the run. UNPROVEN counts — "no runner for this dimension" is an
// honest outcome, not a failure (verify/SKILL.md).
var done = map[StepState]bool{StepPASS: true, StepSKIPPED: true, StepUNPROVEN: true}

// stop is the set that blocks the run.
var stop = map[StepState]bool{StepFAIL: true, StepBLOCKED: true}

// terminal is done ∪ stop.
func terminal(s StepState) bool { return done[s] || stop[s] }

// IsDone reports whether a step state lets the run move on.
func IsDone(s StepState) bool { return done[s] }

// IsStop reports whether a step state blocks the run.
func IsStop(s StepState) bool { return stop[s] }

// IsTerminal reports whether a step has finished, either way.
func IsTerminal(s StepState) bool { return terminal(s) }

// Status is the run-level view, derived from the steps.
type Status string

// Run statuses. awaiting_human is new; the old run.yaml projected it as
// running, which is why "who is this waiting on" was unanswerable.
const (
	StatusPending       Status = "pending"
	StatusRunning       Status = "running"
	StatusAwaitingHuman Status = "awaiting_human"
	StatusBlocked       Status = "blocked"
	StatusDone          Status = "done"
	StatusAborted       Status = "aborted"
)

// Executor says who performs a step. It comes from registry/kinds.yaml.
type Executor string

// The two executors.
const (
	ByConductor Executor = "conductor"
	ByAgent     Executor = "agent"
)

// Step is one row of a run.
type Step struct {
	ID       string
	Kind     string
	Executor Executor
	// IsGate marks kind=human.gate. A gate is the one step a conductor may
	// never record itself.
	IsGate bool
	// NeedsVerify marks kinds whose PASS requires a second agent
	// (registry verify: independent).
	NeedsVerify bool

	State    StepState
	Attempt  int
	Note     string
	Evidence string
	// Writer and Verifier are agent handles, kept so the "verifier must not
	// be the writer" rule can be checked without a database round trip.
	Writer   string
	Verifier string
	// ApprovalID is set when a gate passed, or when a gate was skipped by
	// referencing an earlier approval.
	ApprovalID string
}

// Revision records a change to an already-finished step. Nothing is deleted:
// the note and the old value stay, which is what makes a run auditable.
type Revision struct {
	StepID string
	From   StepState
	To     StepState
	Note   string
}

// Run is the whole run.
type Run struct {
	ID         string
	WorkflowID string
	Feature    string
	Steps      []Step
	Revisions  []Revision

	// Aborted and Drift cannot be derived from the steps.
	Aborted bool
	// Drift is set when the sealed baseline no longer matches what is on
	// disk (E16). It blocks the run without touching any step, because the
	// steps are not what went wrong.
	Drift bool
}

// EventKind names one row of the §5.3 table.
type EventKind string

// The events. Names match the design so the table can be read next to it.
const (
	EvStepActivated         EventKind = "StepActivated"         // E2
	EvDelegationIssued      EventKind = "DelegationIssued"      // E3
	EvDelegationReturned    EventKind = "DelegationReturned"    // E4
	EvDelegationAccepted    EventKind = "DelegationAccepted"    // E5
	EvVerificationRecorded  EventKind = "VerificationRecorded"  // E6
	EvConductorStepStarted  EventKind = "ConductorStepStarted"  // §5.2
	EvConductorStepRecorded EventKind = "ConductorStepRecorded" // E7
	EvGateRequested         EventKind = "GateRequested"         // E8
	EvGateApproved          EventKind = "GateApproved"          // E9
	EvGateRejected          EventKind = "GateRejected"          // E10
	EvGateExpired           EventKind = "GateExpired"           // E11
	EvStepSkipped           EventKind = "StepSkipped"           // E12
	EvStepRetried           EventKind = "StepRetried"           // E13
	EvStepAmended           EventKind = "StepAmended"           // E14
	EvLeaseExpired          EventKind = "LeaseExpired"          // E15
	EvBaselineDriftDetected EventKind = "BaselineDriftDetected" // E16
	// EvBaselineRestored clears a drift block. It is not in the design's
	// §5.3 table, and leaving it out made a drifted run unrecoverable: drift
	// stops the run without putting any step into FAIL or BLOCKED, so
	// StepRetried — the usual way out of a blocked run — has nothing to
	// retry. Per §11.3 the way out is re-sealing or reopening the baseline,
	// which is a different decision from retrying a step, so it is a
	// different event.
	EvBaselineRestored EventKind = "BaselineRestored"
	EvRunAborted       EventKind = "RunAborted" // E18
)

// Actor is who raised the event. The guards that say "only a person" are the
// reason this is not advisory.
type Actor string

// The actors.
const (
	ActorConductor  Actor = "conductor"
	ActorAgent      Actor = "agent"
	ActorHuman      Actor = "human"
	ActorSystem     Actor = "system"
	ActorMaintainer Actor = "maintainer"
)

// Event is one thing that happened.
type Event struct {
	Kind   EventKind
	Actor  Actor
	StepID string

	// Outcome carries the terminal state for the record/accept events.
	Outcome  StepState
	Note     string
	Evidence string

	// Agent is the handle submitting a delegation or a verification.
	Agent string
	// ApprovalID references an approval, for a gate PASS or a gate skip.
	ApprovalID string
	// DigestMatches is the caller's assertion that the approval being
	// referenced still covers the current content (design I-4). A skip of a
	// gate with a stale digest is a skipped signature.
	DigestMatches bool
	// Command and ExitCode are required by shell.confirmed (E7).
	Command  string
	ExitCode *int
}

// Effect is a side effect for the app layer to perform in the same
// transaction. Declarative, so this package stays pure and the effects stay
// reviewable next to the guards that produced them.
type Effect string

// The effects.
const (
	EffectEmitAudit        Effect = "emit-audit"
	EffectProjectRun       Effect = "project-run-yaml"
	EffectAcquireLease     Effect = "acquire-lease"
	EffectReleaseLease     Effect = "release-lease"
	EffectIssueVerifyLease Effect = "issue-verify-lease"
	EffectRecordRevision   Effect = "record-revision"
	EffectBumpAttempt      Effect = "bump-attempt"
	EffectCloseRunSpan     Effect = "close-run-span"
	EffectStop             Effect = "stop"
)

// Error is a refused event, naming the guard that refused.
type Error struct {
	Event  EventKind
	StepID string
	From   StepState
	Reason string
}

func (e *Error) Error() string {
	if e.StepID == "" {
		return fmt.Sprintf("%s refused: %s", e.Event, e.Reason)
	}
	return fmt.Sprintf("%s on %s (%s) refused: %s", e.Event, e.StepID, e.From, e.Reason)
}

func refuse(ev Event, from StepState, reason string) error {
	return &Error{Event: ev.Kind, StepID: ev.StepID, From: from, Reason: reason}
}

// Clone deep-copies a run so Apply never mutates its input.
func (r Run) Clone() Run {
	out := r
	out.Steps = make([]Step, len(r.Steps))
	copy(out.Steps, r.Steps)
	out.Revisions = make([]Revision, len(r.Revisions))
	copy(out.Revisions, r.Revisions)
	return out
}

// Status derives the run-level state. Order matters: aborted and drift win,
// then a stopped step, then a pending signature, then completion.
func (r Run) Status() Status {
	switch {
	case r.Aborted:
		return StatusAborted
	case r.Drift:
		return StatusBlocked
	}
	for _, s := range r.Steps {
		if stop[s.State] {
			return StatusBlocked
		}
	}
	if cur := r.Current(); cur != nil {
		if cur.State == StepAwaitingSignoff {
			return StatusAwaitingHuman
		}
		if cur.State == StepPending && r.allPending() {
			return StatusPending
		}
		return StatusRunning
	}
	return StatusDone
}

func (r Run) allPending() bool {
	for _, s := range r.Steps {
		if s.State != StepPending {
			return false
		}
	}
	return true
}

// Current returns the first step that has not finished, or nil when the run
// is complete. This is what drives the NEXT/OPEN/DELEGATE view.
func (r Run) Current() *Step {
	for i := range r.Steps {
		if !done[r.Steps[i].State] {
			return &r.Steps[i]
		}
	}
	return nil
}

// Live reports whether the run can still accept events.
func (r Run) Live() bool {
	st := r.Status()
	return st != StatusAborted && st != StatusDone
}

func (r *Run) find(id string) (*Step, int) {
	for i := range r.Steps {
		if r.Steps[i].ID == id {
			return &r.Steps[i], i
		}
	}
	return nil, -1
}

// Apply runs one event. On refusal the input run comes back unchanged, so a
// caller that drops the error cannot leave a run half-advanced.
func Apply(r Run, ev Event) (Run, []Effect, error) {
	if r.Aborted {
		return r, nil, refuse(ev, "", "run is aborted")
	}
	out := r.Clone()

	// Run-level events first: they do not name a step.
	switch ev.Kind {
	case EvRunAborted:
		return applyAbort(r, out, ev)
	case EvBaselineDriftDetected:
		// E16: blocks the run without touching a step, because the steps are
		// not what changed — the sealed content under them is.
		if !r.Live() {
			return r, nil, refuse(ev, "", "run has already finished")
		}
		out.Drift = true
		return out, []Effect{EffectEmitAudit, EffectStop, EffectProjectRun}, nil

	case EvBaselineRestored:
		// The baseline matches again, either because it was re-sealed or
		// because a reopen gate passed. Only the system may say so: it is
		// the side that recomputed the manifest.
		if !out.Drift {
			return r, nil, refuse(ev, "", "no drift to clear")
		}
		if ev.Actor != ActorSystem {
			return r, nil, refuse(ev, "", "clearing drift follows a recomputed manifest")
		}
		out.Drift = false
		return out, []Effect{EffectEmitAudit, EffectProjectRun}, nil
	}

	step, idx := out.find(ev.StepID)
	if step == nil {
		return r, nil, refuse(ev, "", fmt.Sprintf("no step %q in this run", ev.StepID))
	}
	from := step.State

	// While the sealed content is in question, nothing advances. The way out
	// is EvBaselineRestored, not a step event.
	if out.Drift {
		return r, nil, refuse(ev, from, "baseline drift: re-seal or reopen before going on")
	}

	effects, err := transition(&out, step, idx, ev)
	if err != nil {
		return r, nil, err
	}

	// I-3, enforced once rather than per event: nothing but a human approval
	// puts a gate into PASS.
	//
	// Every individual guard already says so, but "every guard says so" is a
	// claim about code that will keep changing, and this is the invariant the
	// whole design exists to protect. A property test found the hole the
	// per-event guards left: a gate loaded from storage in `verifying` state
	// could be moved to PASS by VerificationRecorded. Unreachable in a real
	// run — and not somewhere to rely on that.
	if step.IsGate && step.State == StepPASS && ev.Kind != EvGateApproved {
		return r, nil, refuse(ev, from, "a gate reaches PASS only through a human approval")
	}

	effects = append(effects, EffectProjectRun)
	if out.Status() == StatusDone {
		effects = append(effects, EffectCloseRunSpan)
	}
	return out, effects, nil
}

func applyAbort(in, out Run, ev Event) (Run, []Effect, error) {
	if ev.Note == "" {
		return in, nil, refuse(ev, "", "an abort needs a note")
	}
	switch ev.Actor {
	case ActorHuman, ActorMaintainer:
	case ActorConductor:
		// E18: a conductor may only abort a run it has not already had
		// signed. Throwing away a human signature is a person's decision.
		for _, s := range in.Steps {
			if s.IsGate && s.State == StepPASS {
				return in, nil, refuse(ev, "",
					"this run has an approved gate; only a person may abort it")
			}
		}
	default:
		return in, nil, refuse(ev, "", "only a person, a maintainer or the conductor may abort")
	}
	out.Aborted = true
	out.Revisions = append(out.Revisions, Revision{Note: "aborted: " + ev.Note})
	return out, []Effect{EffectReleaseLease, EffectRecordRevision, EffectEmitAudit, EffectProjectRun}, nil
}

// transition is the §5.3 table proper.
func transition(out *Run, step *Step, idx int, ev Event) ([]Effect, error) {
	from := step.State

	switch ev.Kind {
	// E2 — the step becomes next.
	case EvStepActivated:
		if from != StepPending {
			return nil, refuse(ev, from, "only a pending step activates")
		}
		if !priorsFinished(*out, idx) {
			return nil, refuse(ev, from, "an earlier step has not finished")
		}
		step.State = StepReady
		return []Effect{EffectEmitAudit}, nil

	// E3 — hand the step to an agent.
	case EvDelegationIssued:
		if from != StepReady {
			return nil, refuse(ev, from, "a delegation is issued from ready")
		}
		if step.Executor != ByAgent {
			return nil, refuse(ev, from, "this kind stays with the conductor")
		}
		if ev.Actor != ActorConductor {
			return nil, refuse(ev, from, "only the conductor delegates")
		}
		if ev.Agent == "" {
			return nil, refuse(ev, from, "a delegation names its agent")
		}
		step.State = StepDelegated
		step.Writer = ev.Agent
		if step.Attempt == 0 {
			step.Attempt = 1
		}
		return []Effect{EffectAcquireLease, EffectEmitAudit}, nil

	// E4 — the agent reports back.
	case EvDelegationReturned:
		if from != StepDelegated {
			return nil, refuse(ev, from, "only a delegated step returns")
		}
		if ev.Agent != step.Writer {
			return nil, refuse(ev, from,
				fmt.Sprintf("%s holds this delegation, not %s", step.Writer, ev.Agent))
		}
		step.State = StepReturned
		return []Effect{EffectEmitAudit}, nil

	// E5 — the conductor accepts the report, and the machine checks decide.
	case EvDelegationAccepted:
		if from != StepReturned {
			return nil, refuse(ev, from, "accept follows a return")
		}
		if ev.Actor != ActorConductor {
			return nil, refuse(ev, from, "only the conductor accepts a report")
		}
		if !terminal(ev.Outcome) {
			return nil, refuse(ev, from, "an accepted report carries a terminal status")
		}
		if ev.Outcome == StepPASS && step.NeedsVerify {
			// I-2: this kind's PASS is not the writer's to declare.
			step.State = StepVerifying
			return []Effect{EffectReleaseLease, EffectIssueVerifyLease, EffectEmitAudit}, nil
		}
		if ev.Outcome == StepPASS && ev.Evidence == "" {
			return nil, refuse(ev, from, "a PASS without evidence does not count")
		}
		step.State = ev.Outcome
		step.Evidence = ev.Evidence
		eff := []Effect{EffectReleaseLease, EffectEmitAudit}
		if stop[ev.Outcome] {
			eff = append(eff, EffectStop)
		}
		return eff, nil

	// E6 — the second agent confirms or refuses.
	case EvVerificationRecorded:
		if step.IsGate {
			// A gate has no verifier. Reachable only from a state loaded
			// from storage, which is exactly where not to assume the path
			// was legitimate.
			return nil, refuse(ev, from, "a gate is decided by a person, not verified by an agent")
		}
		if from != StepVerifying {
			return nil, refuse(ev, from, "no verification is outstanding")
		}
		if ev.Agent == "" {
			return nil, refuse(ev, from, "a verification names its verifier")
		}
		if ev.Agent == step.Writer {
			return nil, refuse(ev, from,
				"the writer cannot verify its own work; that is what independent means")
		}
		if ev.Outcome != StepPASS && ev.Outcome != StepFAIL {
			return nil, refuse(ev, from, "a verification is PASS or FAIL")
		}
		step.State = ev.Outcome
		step.Verifier = ev.Agent
		if ev.Evidence != "" {
			step.Evidence = ev.Evidence
		}
		eff := []Effect{EffectReleaseLease, EffectEmitAudit}
		if ev.Outcome == StepFAIL {
			eff = append(eff, EffectStop)
		}
		return eff, nil

	// §5.2 — the conductor starts a step it owns.
	case EvConductorStepStarted:
		if from != StepReady {
			return nil, refuse(ev, from, "a conductor step starts from ready")
		}
		if step.Executor != ByAgent && step.IsGate {
			return nil, refuse(ev, from, "a gate is requested, not started")
		}
		if step.Executor != ByConductor {
			return nil, refuse(ev, from, "this kind is delegated")
		}
		step.State = StepConductorActive
		return []Effect{EffectEmitAudit}, nil

	// E7 — the conductor records its own step.
	case EvConductorStepRecorded:
		if from != StepConductorActive {
			return nil, refuse(ev, from, "this step is not running under the conductor")
		}
		if step.IsGate {
			return nil, refuse(ev, from, "a gate is decided by a person, not recorded")
		}
		if !terminal(ev.Outcome) {
			return nil, refuse(ev, from, "a recorded step carries a terminal status")
		}
		if step.Kind == "shell.confirmed" && (ev.Command == "" || ev.ExitCode == nil) {
			return nil, refuse(ev, from, "shell.confirmed records the command and its exit code")
		}
		if ev.Outcome == StepPASS && ev.Evidence == "" {
			return nil, refuse(ev, from, "a PASS without evidence does not count")
		}
		step.State = ev.Outcome
		step.Evidence = ev.Evidence
		eff := []Effect{EffectEmitAudit}
		if stop[ev.Outcome] {
			eff = append(eff, EffectStop)
		}
		return eff, nil

	// E8 — ask the person.
	case EvGateRequested:
		if from != StepReady {
			return nil, refuse(ev, from, "a gate is requested from ready")
		}
		if !step.IsGate {
			return nil, refuse(ev, from, "this step is not a gate")
		}
		step.State = StepAwaitingSignoff
		return []Effect{EffectEmitAudit}, nil

	// E9 — the person approved. The quote and identity were checked by
	// domain/signoff and the authn layer before this point; what is checked
	// here is that nothing else can perform this transition.
	case EvGateApproved:
		if from != StepAwaitingSignoff {
			return nil, refuse(ev, from, "no signature is outstanding")
		}
		if ev.Actor != ActorHuman {
			return nil, refuse(ev, from, "only a person approves a gate")
		}
		if ev.ApprovalID == "" {
			return nil, refuse(ev, from, "an approval must be recorded to be referenced later")
		}
		step.State = StepPASS
		step.ApprovalID = ev.ApprovalID
		return []Effect{EffectEmitAudit}, nil

	// E10 — the person refused.
	case EvGateRejected:
		if from != StepAwaitingSignoff {
			return nil, refuse(ev, from, "no signature is outstanding")
		}
		if ev.Actor != ActorHuman {
			return nil, refuse(ev, from, "only a person rejects a gate")
		}
		step.State = StepFAIL
		return []Effect{EffectEmitAudit, EffectStop}, nil

	// E11 — nobody answered in time. Back to ready, not failed: an unanswered
	// question is not a refusal.
	case EvGateExpired:
		if from != StepAwaitingSignoff {
			return nil, refuse(ev, from, "no signature is outstanding")
		}
		if ev.Actor != ActorSystem {
			return nil, refuse(ev, from, "expiry is the system's call")
		}
		step.State = StepReady
		return []Effect{EffectEmitAudit}, nil

	// E12 — skip.
	case EvStepSkipped:
		if from != StepReady {
			return nil, refuse(ev, from, "a step is skipped from ready")
		}
		if step.IsGate {
			// Skipping a gate means "a person already signed this". That
			// claim needs the earlier approval, and the content must not
			// have changed since (I-4).
			if ev.ApprovalID == "" {
				return nil, refuse(ev, from,
					"skipping a gate needs the earlier approval it relies on")
			}
			if !ev.DigestMatches {
				return nil, refuse(ev, from,
					"the content changed since that approval; ask again")
			}
			step.ApprovalID = ev.ApprovalID
		} else if ev.Note == "" {
			return nil, refuse(ev, from, "skipping a step needs a note")
		}
		step.State = StepSKIPPED
		step.Note = ev.Note
		return []Effect{EffectEmitAudit}, nil

	// E13 — try again.
	case EvStepRetried:
		if !stop[from] {
			return nil, refuse(ev, from, "only a failed or blocked step is retried")
		}
		if ev.Note == "" {
			return nil, refuse(ev, from, "a retry needs a note")
		}
		for i := range out.Steps {
			if i != idx && stop[out.Steps[i].State] {
				return nil, refuse(ev, from,
					fmt.Sprintf("%s is still %s; clear it first", out.Steps[i].ID, out.Steps[i].State))
			}
		}
		out.Revisions = append(out.Revisions, Revision{
			StepID: step.ID, From: from, To: StepReady, Note: ev.Note,
		})
		step.State = StepReady
		step.Attempt++
		return []Effect{EffectBumpAttempt, EffectRecordRevision, EffectEmitAudit}, nil

	// E14 — change a finished step.
	case EvStepAmended:
		if !terminal(from) {
			return nil, refuse(ev, from, "only a finished step is amended")
		}
		if ev.Note == "" {
			return nil, refuse(ev, from, "changing a recorded step needs a note")
		}
		if !terminal(ev.Outcome) {
			return nil, refuse(ev, from, "an amendment carries a terminal status")
		}
		if step.IsGate && ev.Outcome == StepPASS && from != StepPASS {
			// E14: a gate cannot be amended into an approval. That is a
			// signature, and signatures come from people through E9.
			return nil, refuse(ev, from,
				"a gate cannot be amended to PASS; request the gate again")
		}
		if ev.Actor != ActorConductor && ev.Actor != ActorMaintainer {
			return nil, refuse(ev, from, "only the conductor or a maintainer amends a step")
		}
		out.Revisions = append(out.Revisions, Revision{
			StepID: step.ID, From: from, To: ev.Outcome, Note: ev.Note,
		})
		step.State = ev.Outcome
		step.Note = ev.Note
		if ev.Evidence != "" {
			step.Evidence = ev.Evidence
		}
		eff := []Effect{EffectRecordRevision, EffectEmitAudit}
		if stop[ev.Outcome] {
			eff = append(eff, EffectStop)
		}
		return eff, nil

	// E15 — the agent went away. Back to ready; a late report will fail the
	// fencing check in the app layer.
	case EvLeaseExpired:
		if from != StepDelegated {
			return nil, refuse(ev, from, "no lease is outstanding on this step")
		}
		if ev.Actor != ActorSystem {
			return nil, refuse(ev, from, "lease expiry is the sweeper's call")
		}
		step.State = StepReady
		step.Writer = ""
		return []Effect{EffectReleaseLease, EffectEmitAudit}, nil
	}

	return nil, refuse(ev, from, "unknown event")
}

func priorsFinished(r Run, idx int) bool {
	for i := 0; i < idx; i++ {
		if !done[r.Steps[i].State] {
			return false
		}
	}
	return true
}
