// Package runsvc drives runs: one use case, one transaction.
//
// The services here are thin on purpose. The decisions live in
// internal/domain, which is pure and exhaustively tested; what this layer
// adds is the part that cannot be a pure function — reading the current
// state, applying the domain's answer, writing the audit event, and doing
// all of it atomically so a state change and its record cannot be
// separated (invariant I-6).
//
// That last point is the reason for the shape. The Python driver did
// "read, decide, write" with no transaction, so a crash or a concurrent
// writer left state nobody had audited and audits of state that was rolled
// back. Here the audit append is in the same transaction as the save, and
// the save is a compare-and-swap, so two conductors cannot both apply a
// decision to the same run.
package runsvc

import (
	"context"
	"errors"
	"fmt"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

// Service applies events to runs.
type Service struct {
	Store    ports.Store
	Clock    ports.Clock
	IDs      ports.IDGen
	Registry ports.KindRegistry
}

// StartParams describes a new run.
type StartParams struct {
	WorkflowID string
	FeatureID  string
	Feature    string
	Steps      []run.Step
	Params     map[string]string
	Actor      ports.Principal
	// IdempotencyKey makes a retried start safe. A conductor whose request
	// timed out must not create a second run by retrying.
	IdempotencyKey string
}

// Start creates a run and activates its first step.
func (s Service) Start(ctx context.Context, p StartParams) (run.Run, error) {
	if p.WorkflowID == "" || p.FeatureID == "" {
		return run.Run{}, fmt.Errorf("runsvc: a run needs a workflow and a feature")
	}
	if len(p.Steps) == 0 {
		return run.Run{}, fmt.Errorf("runsvc: %s has no steps", p.WorkflowID)
	}
	for _, st := range p.Steps {
		if s.Registry != nil && s.Registry.Forbidden(st.Kind) {
			// The forbidden kinds are the shapes of skipping the human.
			return run.Run{}, fmt.Errorf(
				"runsvc: step %s uses forbidden kind %s", st.ID, st.Kind)
		}
	}

	var out run.Run
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		if p.IdempotencyKey != "" {
			_, replayed, err := tx.Idempotency().Claim(ctx, p.IdempotencyKey, "run.start")
			if err != nil {
				return err
			}
			if replayed {
				// The first attempt already created it; return that rather
				// than a second run.
				existing, _, err := tx.Runs().FindLive(ctx, p.FeatureID, p.WorkflowID)
				if err != nil {
					return err
				}
				out = existing
				return nil
			}
		}

		r := run.Run{
			ID:         s.IDs.New(),
			WorkflowID: p.WorkflowID,
			Feature:    p.Feature,
			Steps:      withExecutors(p.Steps, s.Registry),
		}
		if err := tx.Runs().Create(ctx, r, p.FeatureID); err != nil {
			return err
		}

		// Activate the first step inside the same transaction: a run whose
		// first step is still pending has no next step to show, and the
		// conductor would have to ask twice.
		activated, _, err := run.Apply(r, run.Event{
			Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: r.Steps[0].ID,
		})
		if err != nil {
			return err
		}
		if err := tx.Runs().Save(ctx, activated, 1); err != nil {
			return err
		}
		if err := appendAudit(ctx, tx, audit.Event{
			Action:  audit.ActionRunStarted,
			Actor:   actorOf(p.Actor),
			RunID:   r.ID,
			Feature: p.Feature,
			Detail:  map[string]any{"workflow_id": p.WorkflowID},
		}, s.Clock); err != nil {
			return err
		}
		if p.IdempotencyKey != "" {
			if err := tx.Idempotency().Complete(ctx, p.IdempotencyKey, []byte(r.ID)); err != nil {
				return err
			}
		}
		out = activated
		return nil
	})
	return out, err
}

// withExecutors fills in each step's executor and verification needs from
// the registry, so the domain machine does not have to consult it.
func withExecutors(steps []run.Step, reg ports.KindRegistry) []run.Step {
	out := make([]run.Step, len(steps))
	copy(out, steps)
	for i := range out {
		if out[i].State == "" {
			out[i].State = run.StepPending
		}
		if reg == nil {
			continue
		}
		if reg.AgentFor(out[i].Kind) == "-" {
			out[i].Executor = run.ByConductor
		} else {
			out[i].Executor = run.ByAgent
		}
		out[i].IsGate = reg.IsGate(out[i].Kind)
		if _, ok := reg.NeedsIndependentVerification(out[i].Kind); ok {
			out[i].NeedsVerify = true
		}
	}
	return out
}

// Apply runs one domain event against a stored run.
//
// Every caller goes through this rather than touching the repo, so there is
// one place where "the domain said yes" and "the audit recorded it" are
// tied together.
//
// The event's Actor field is a claim, and the guards that matter read it
// (only a person approves a gate). Since the caller constructs the event,
// checkEvent re-establishes the claim against the authenticated principal
// and — for the events that carry one — the recorded approval, inside the
// same transaction. Without this, an agent that writes Actor: human and an
// invented approval id passes every domain guard (review D1).
func (s Service) Apply(ctx context.Context, runID string, ev run.Event, actor ports.Principal) (run.Run, error) {
	var out run.Run
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		current, version, err := tx.Runs().Get(ctx, runID)
		if err != nil {
			return err
		}
		if err := checkEvent(ctx, tx, current, ev, actor); err != nil {
			return err
		}
		next, effects, err := run.Apply(current, ev)
		if err != nil {
			return err
		}
		if err := tx.Runs().Save(ctx, next, version); err != nil {
			return err
		}
		if err := appendAudit(ctx, tx, auditFor(ev, next, actor), s.Clock); err != nil {
			return err
		}
		if err := s.performEffects(ctx, tx, next, ev, effects); err != nil {
			return err
		}
		out = next
		return nil
	})
	return out, err
}

// checkEvent re-verifies, in the transaction Apply runs in, the claims an
// event makes about identity and approvals. The domain guards read those
// claims as facts; this is where they become facts.
//
// A refusal here writes nothing: not the run, not an audit event.
func checkEvent(ctx context.Context, tx ports.Tx, current run.Run, ev run.Event, actor ports.Principal) error {
	// Only an authenticated human principal can claim a human actor. The
	// claim is one-way: a human principal may still raise conductor or
	// system-shaped events, which the domain guards check by themselves.
	if ev.Actor == run.ActorHuman && actor.Kind != "human" {
		return fmt.Errorf(
			"runsvc: %s claims a person raised it, but %s (%s) is not one",
			ev.Kind, actor.Handle, actor.Kind)
	}

	switch ev.Kind {
	case run.EvDelegationReturned, run.EvVerificationRecorded:
		// A report must arrive on the lease that is live now. One that
		// references a lease already swept or superseded — or presents a
		// stale fencing counter — is a late report from a holder who lost
		// the step, and applying it would write over the new holder's work
		// (E15, review D2: the fencing tokens existed but were never
		// checked).
		l, err := tx.Leases().ActiveFor(ctx, current.ID, ev.StepID)
		if err != nil {
			return fmt.Errorf(
				"runsvc: %s on %s: no live lease holds this step: %w",
				ev.Kind, ev.StepID, err)
		}
		if err := l.CheckFencing(ev.Fencing); err != nil {
			return fmt.Errorf("runsvc: %s on %s: %w", ev.Kind, ev.StepID, err)
		}
		if err := l.CheckHolder(ev.Agent); err != nil {
			return fmt.Errorf("runsvc: %s on %s: %w", ev.Kind, ev.StepID, err)
		}
	case run.EvGateApproved, run.EvStepSkipped:
		// A gate PASS — directly or by skip — must reference a recorded
		// approval that belongs to this run and step, decided as an approve
		// by the same person whose principal is submitting the event.
		if ev.Kind == run.EvStepSkipped && !gateStep(current, ev.StepID) {
			// Skipping an ordinary step needs a note, which the domain
			// checks; there is no approval to verify.
			return nil
		}
		a, err := tx.Gates().Approval(ctx, ev.ApprovalID)
		if err != nil {
			return fmt.Errorf(
				"runsvc: %s references approval %q, which is not recorded: %w",
				ev.Kind, ev.ApprovalID, err)
		}
		g, err := tx.Gates().Get(ctx, a.GateID)
		if err != nil {
			return fmt.Errorf("runsvc: loading gate %s: %w", a.GateID, err)
		}
		if g.RunID != current.ID || g.StepID != ev.StepID {
			return fmt.Errorf(
				"runsvc: approval %s belongs to %s/%s, not %s/%s",
				a.ID, g.RunID, g.StepID, current.ID, ev.StepID)
		}
		if a.Decision != string(gate.DecisionApprove) {
			return fmt.Errorf(
				"runsvc: approval %s is a %s; only an approve passes a gate",
				a.ID, a.Decision)
		}
		if a.Handle != actor.Handle || a.Kind != "human" {
			return fmt.Errorf(
				"runsvc: approval %s was given by %s (%s), not by the submitting principal",
				a.ID, a.Handle, a.Kind)
		}
	}
	return nil
}

// gateStep reports whether the named step of the run is a gate.
func gateStep(r run.Run, stepID string) bool {
	for i := range r.Steps {
		if r.Steps[i].ID == stepID {
			return r.Steps[i].IsGate
		}
	}
	return false
}

// performEffects executes the declarative effects the domain asked for.
//
// Only the ones with a storage consequence are handled here; projection to
// the old YAML files is a separate port, applied after the transaction
// commits, because a file write cannot be rolled back with the database.
func (s Service) performEffects(
	ctx context.Context, tx ports.Tx, r run.Run, ev run.Event, effects []run.Effect,
) error {
	for _, e := range effects {
		switch e {
		case run.EffectReleaseLease:
			l, err := tx.Leases().ActiveFor(ctx, r.ID, ev.StepID)
			if err != nil {
				// No lease to release is not an error: conductor steps take
				// none, and a lease already swept is already released.
				if isNotFound(err) {
					continue
				}
				return err
			}
			if err := tx.Leases().Release(ctx, l.ID); err != nil {
				return err
			}
			// The domain's own release path needs no token — the state
			// machine said the step is done with the lease — but it still
			// owes the chain its record, which leasesvc.Release would have
			// written for a token-holding caller.
			if err := appendAudit(ctx, tx, audit.Event{
				Action:  audit.ActionLeaseReleased,
				Actor:   audit.Actor{Handle: "run", Kind: "system"},
				RunID:   r.ID,
				StepID:  ev.StepID,
				Feature: r.Feature,
				Subject: l.ID,
				Detail:  map[string]any{"agent": l.Agent, "via": "run-state-machine"},
			}, s.Clock); err != nil {
				return err
			}
		case run.EffectStop, run.EffectEmitAudit, run.EffectProjectRun,
			run.EffectCloseRunSpan, run.EffectRecordRevision, run.EffectBumpAttempt,
			run.EffectAcquireLease, run.EffectIssueVerifyLease:
			// EmitAudit is already done; ProjectRun and CloseRunSpan happen
			// outside the transaction; the lease effects are performed by
			// the services that own them, which need the token and the
			// paths this layer does not have.
		}
	}
	return nil
}

// Get reads a run.
func (s Service) Get(ctx context.Context, runID string) (run.Run, error) {
	var out run.Run
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		r, _, err := tx.Runs().Get(ctx, runID)
		out = r
		return err
	})
	return out, err
}

// Next describes what the conductor should do now.
//
// The shape mirrors `workflow.py next`, because the conductor's prompt and
// the golden files both depend on it: NEXT, OPEN, DELEGATE, LABEL.
type Next struct {
	// Action is delegate, conductor, gate, done or blocked.
	Action string
	Step   *run.Step
	// Steps is the open wave. Step is its first member. A group lists every
	// member that is still unfinished; a step with no group is the only entry.
	Steps  []run.Step
	Agent  string
	Status run.Status
}

// Action values.
const (
	ActionDelegate  = "delegate"
	ActionConductor = "conductor"
	ActionGate      = "gate"
	ActionDone      = "done"
	ActionBlocked   = "blocked"
)

// Next computes the next action without changing anything.
func (s Service) Next(ctx context.Context, runID string) (Next, error) {
	r, err := s.Get(ctx, runID)
	if err != nil {
		return Next{}, err
	}
	return s.NextFor(r), nil
}

// NextFor is Next on an already-loaded run.
func (s Service) NextFor(r run.Run) Next {
	status := r.Status()
	opened := r.Open()
	cur := r.Current()
	switch status {
	case run.StatusDone, run.StatusAborted:
		return Next{Action: ActionDone, Status: status}
	case run.StatusBlocked:
		return Next{Action: ActionBlocked, Step: cur, Steps: opened, Status: status}
	}
	if cur == nil {
		return Next{Action: ActionDone, Status: run.StatusDone}
	}
	switch {
	case cur.IsGate:
		return Next{Action: ActionGate, Step: cur, Steps: opened, Status: status}
	case cur.Executor == run.ByAgent:
		agent := ""
		if s.Registry != nil {
			agent = s.Registry.AgentFor(cur.Kind)
		}
		return Next{Action: ActionDelegate, Step: cur, Steps: opened, Agent: agent, Status: status}
	default:
		return Next{Action: ActionConductor, Step: cur, Steps: opened, Status: status}
	}
}

// --- helpers ---------------------------------------------------------------

func appendAudit(ctx context.Context, tx ports.Tx, e audit.Event, clock ports.Clock) error {
	if e.At.IsZero() && clock != nil {
		e.At = clock.Now()
	}
	_, err := tx.Audit().Append(ctx, e)
	return err
}

func actorOf(p ports.Principal) audit.Actor {
	return audit.Actor{
		Handle:     p.Handle,
		Kind:       p.Kind,
		OnBehalfOf: p.OwnerHandle,
	}
}

// auditFor maps a domain event to an audit action. The mapping is explicit
// rather than derived from the event name, so renaming an event does not
// silently change what the audit trail says happened.
func auditFor(ev run.Event, r run.Run, actor ports.Principal) audit.Event {
	action := audit.ActionStepRecorded
	switch ev.Kind {
	case run.EvStepActivated:
		action = audit.ActionStepActivated
	case run.EvDelegationIssued:
		action = audit.ActionDelegationIssued
	case run.EvDelegationReturned:
		action = audit.ActionDelegationReturned
	case run.EvDelegationAccepted:
		action = audit.ActionDelegationAccepted
	case run.EvVerificationRecorded:
		action = audit.ActionVerification
	case run.EvGateRequested:
		action = audit.ActionGateRequested
	case run.EvGateApproved:
		action = audit.ActionGateApproved
	case run.EvGateRejected:
		action = audit.ActionGateRejected
	case run.EvGateExpired:
		action = audit.ActionGateExpired
	case run.EvStepSkipped:
		action = audit.ActionStepSkipped
	case run.EvStepRetried:
		action = audit.ActionStepRetried
	case run.EvStepAmended:
		action = audit.ActionStepAmended
	case run.EvLeaseExpired:
		action = audit.ActionLeaseExpired
	case run.EvBaselineDriftDetected:
		action = audit.ActionBaselineDrift
	case run.EvRunAborted:
		action = audit.ActionRunAborted
	}
	detail := map[string]any{}
	if ev.Note != "" {
		detail["note"] = ev.Note
	}
	if ev.Outcome != "" {
		detail["outcome"] = string(ev.Outcome)
	}
	if ev.Agent != "" {
		detail["agent"] = ev.Agent
	}
	if len(detail) == 0 {
		detail = nil
	}
	return audit.Event{
		Action:  action,
		Actor:   actorOf(actor),
		RunID:   r.ID,
		StepID:  ev.StepID,
		Feature: r.Feature,
		Subject: ev.ApprovalID,
		Detail:  detail,
	}
}

func isNotFound(err error) bool {
	var ce *ports.ConflictError
	return errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound
}
