// Package feature holds the delivery stage machine: the rule that a ticket
// moves req-review → req → arch → code → test → done one step at a time, and
// goes backwards only to a defect origin a person has named.
//
// The rules are deliver/references/deliver-schema.md §阶段 verbatim; this is
// the executable copy. They are worth encoding because every one of them is a
// way the process can be quietly skipped: jumping a stage, rolling back
// without agreement, or treating a rollback as a chance to rewrite a sealed
// baseline. The old implementation enforced none of it — stage was a string
// in a YAML file and anything could write it.
//
// Zero IO by design (see .golangci.yml, rule domain-pure): everything here is
// a pure function of state and event, so the whole table can be tested
// without a database, and the app layer owns the transaction.
package feature

import (
	"fmt"
	"sort"
)

// Stage is where a ticket is in its delivery life.
type Stage string

// The six stages, in order, plus ops.
//
// ops is deliberately not in the ordering: it is a side-track for a live
// phenomenon, entered from done or mid-delivery, and it is never a defect
// origin (deliver-schema.md: "ops 不是缺陷 origin").
const (
	StageReqReview Stage = "req-review"
	StageReq       Stage = "req"
	StageArch      Stage = "arch"
	StageCode      Stage = "code"
	StageTest      Stage = "test"
	StageDone      Stage = "done"
	StageOps       Stage = "ops"
)

// order is the single source for "one step forward" and "is X before Y".
var order = []Stage{StageReqReview, StageReq, StageArch, StageCode, StageTest, StageDone}

func index(s Stage) int {
	for i, v := range order {
		if v == s {
			return i
		}
	}
	return -1
}

// Known reports whether s is a stage this machine understands.
func Known(s Stage) bool { return index(s) >= 0 || s == StageOps }

// GateType is the human decision that drives a transition.
type GateType string

// The gates. Each one is a sentence a person said, verified by
// domain/signoff before it reaches this package.
const (
	GateSealed         GateType = "sealed"
	GateAcceptedReq    GateType = "accepted_req"
	GateAcceptedArch   GateType = "accepted_arch"
	GateSelftest       GateType = "selftest"
	GateAligned        GateType = "aligned"
	GateResolved       GateType = "resolved"
	GateReopenBaseline GateType = "reopen_baseline"
	GateDefectOrigin   GateType = "defect_origin"
)

// Effect is a side effect the app layer must perform in the same transaction.
// Declarative so the machine stays pure and the effects stay reviewable.
type Effect string

// The effects this machine can ask for.
const (
	EffectBumpRevision    Effect = "bump-revision"
	EffectVoidItemIDs     Effect = "void-item-ids"
	EffectExpireApprovals Effect = "expire-approvals-after-origin"
	EffectRecordRevision  Effect = "record-revision"
	EffectUnsealBaseline  Effect = "unseal-baseline"
	EffectProjectSignoff  Effect = "project-signoff"
	EffectEmitAudit       Effect = "emit-audit"
)

// State is everything the machine needs. Approvals maps a stage to whether
// its exit gate has been signed; a rollback expires the ones after the origin
// rather than deleting them, so the evidence survives.
type State struct {
	Stage          Stage
	Revision       int
	BaselineSealed bool
	Approvals      map[Stage]bool
	// SelftestPassed gates code → test. It is not a human signature: the
	// verify run either went green or it did not.
	SelftestPassed bool
}

// Event is one decision applied to the state.
type Event struct {
	Gate GateType
	// Origin is the stage a defect_origin gate names.
	Origin Stage
	// Quote is carried for the audit record; signoff.ParseConfirm has
	// already validated it and checked the keyword rules.
	Quote string
	// By is the authenticated human principal.
	By string
}

// Clone copies the state so Apply can stay free of aliasing surprises.
func (s State) Clone() State {
	out := s
	out.Approvals = make(map[Stage]bool, len(s.Approvals))
	for k, v := range s.Approvals {
		out.Approvals[k] = v
	}
	return out
}

// TransitionError says which rule refused, in the words the rule is written
// in, so the conductor can repeat it to the person.
type TransitionError struct {
	From   Stage
	Gate   GateType
	Reason string
}

func (e *TransitionError) Error() string {
	return fmt.Sprintf("stage %s: gate %s refused: %s", e.From, e.Gate, e.Reason)
}

func refuse(from Stage, gate GateType, reason string) error {
	return &TransitionError{From: from, Gate: gate, Reason: reason}
}

// Apply runs one event against the state.
//
// It never mutates the input. On refusal the returned state is the input
// unchanged, so a caller that ignores the error cannot half-advance a ticket.
func Apply(s State, e Event) (State, []Effect, error) {
	if !Known(s.Stage) {
		return s, nil, refuse(s.Stage, e.Gate, "unknown stage")
	}
	out := s.Clone()
	if out.Approvals == nil {
		out.Approvals = map[Stage]bool{}
	}

	switch e.Gate {
	case GateSealed:
		if s.Stage != StageReqReview {
			return s, nil, refuse(s.Stage, e.Gate, "a baseline is sealed in req-review only")
		}
		out.Stage = StageReq
		out.BaselineSealed = true
		out.Approvals[StageReqReview] = true
		return out, []Effect{EffectProjectSignoff, EffectEmitAudit}, nil

	case GateAcceptedReq:
		return forward(s, out, e, StageReq, StageArch)

	case GateAcceptedArch:
		return forward(s, out, e, StageArch, StageCode)

	case GateSelftest:
		// Not a signature. The self-test gate is the verify run going green.
		if s.Stage != StageCode {
			return s, nil, refuse(s.Stage, e.Gate, "the self-test gate belongs to code")
		}
		if !s.SelftestPassed {
			return s, nil, refuse(s.Stage, e.Gate, "verify selftest has not passed")
		}
		out.Stage = StageTest
		out.Approvals[StageCode] = true
		return out, []Effect{EffectEmitAudit}, nil

	case GateAligned:
		return forward(s, out, e, StageTest, StageDone)

	case GateResolved:
		if s.Stage != StageOps {
			return s, nil, refuse(s.Stage, e.Gate, "resolved closes an ops track")
		}
		out.Stage = StageDone
		return out, []Effect{EffectProjectSignoff, EffectEmitAudit}, nil

	case GateReopenBaseline:
		// The only way back into req-review, and the only way a sealed
		// baseline becomes writable again. signoff.ParseConfirm has already
		// required the words 解除密封 or reopen in the quote.
		if s.Stage == StageReqReview {
			return s, nil, refuse(s.Stage, e.Gate, "the baseline is already open")
		}
		out.Stage = StageReqReview
		out.Revision = s.Revision + 1
		out.BaselineSealed = false
		out.Approvals = map[Stage]bool{}
		out.SelftestPassed = false
		return out, []Effect{
			EffectBumpRevision,
			EffectUnsealBaseline,
			EffectVoidItemIDs,
			EffectExpireApprovals,
			EffectRecordRevision,
			EffectEmitAudit,
		}, nil

	case GateDefectOrigin:
		return rollback(s, out, e)
	}
	return s, nil, refuse(s.Stage, e.Gate, "unknown gate")
}

// forward advances exactly one stage, and only from the stage that owns the
// gate. "只能前进一格" is the rule; this is where it lives.
func forward(in, out State, e Event, from, to Stage) (State, []Effect, error) {
	if in.Stage != from {
		return in, nil, refuse(in.Stage, e.Gate, fmt.Sprintf("this gate exits %s", from))
	}
	if !in.BaselineSealed {
		return in, nil, refuse(in.Stage, e.Gate, "the baseline is not sealed")
	}
	out.Stage = to
	out.Approvals[from] = true
	return out, []Effect{EffectProjectSignoff, EffectEmitAudit}, nil
}

// rollback returns to a named defect origin.
//
// Three refusals matter here, and each one is a way the process was skipped
// in practice: naming a stage that is not behind you (that is not a defect,
// that is a jump), naming req-review without first reopening the baseline,
// and naming ops at all.
func rollback(in, out State, e Event) (State, []Effect, error) {
	origin := e.Origin
	if !Known(origin) {
		return in, nil, refuse(in.Stage, e.Gate, "defect origin names no stage")
	}
	if origin == StageOps {
		return in, nil, refuse(in.Stage, e.Gate, "ops is not a defect origin")
	}
	if origin == StageReqReview {
		return in, nil, refuse(in.Stage, e.Gate,
			"req-review is reachable only through reopen_baseline")
	}
	here, there := index(in.Stage), index(origin)
	if here < 0 {
		return in, nil, refuse(in.Stage, e.Gate, "cannot roll back from here")
	}
	if there >= here {
		return in, nil, refuse(in.Stage, e.Gate,
			fmt.Sprintf("%s is not behind %s; a rollback goes backwards", origin, in.Stage))
	}
	out.Stage = origin
	// Everything signed after the origin stops counting. The records are
	// kept — deliver-schema.md: "写入 revisions,不删除证据".
	for _, st := range order[there:] {
		delete(out.Approvals, st)
	}
	out.SelftestPassed = false
	return out, []Effect{EffectExpireApprovals, EffectRecordRevision, EffectEmitAudit}, nil
}

// EnterOps moves a ticket onto the ops side-track without changing how far
// delivery got. deliver-schema.md allows it from done or mid-delivery, which
// is why it is not part of the ordered machine.
func EnterOps(s State) (State, []Effect, error) {
	if s.Stage == StageOps {
		return s, nil, refuse(s.Stage, "", "already on the ops track")
	}
	out := s.Clone()
	out.Stage = StageOps
	return out, []Effect{EffectEmitAudit}, nil
}

// Stages lists the ordered stages, for callers that render the machine.
func Stages() []Stage {
	out := make([]Stage, len(order))
	copy(out, order)
	return out
}

// SignedStages lists the stages whose exit gate has been approved, in order.
func (s State) SignedStages() []Stage {
	out := []Stage{}
	for st, ok := range s.Approvals {
		if ok {
			out = append(out, st)
		}
	}
	sort.Slice(out, func(i, j int) bool { return index(out[i]) < index(out[j]) })
	return out
}
