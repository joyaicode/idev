// Package gate holds the human-gate record: what is being asked, what
// strength of authentication the answer needs, and what makes an approval
// valid.
//
// The design calls this the one thing an agent must not be able to do
// (invariant I-3). Three separate properties have to hold for that to be
// true, and all three live here:
//
//   - the approver is a person, not an agent or the conductor;
//   - the authentication was strong enough for what is being signed, which
//     is why `assurance` exists and why a policy can only ever tighten it;
//   - the approval is bound to a digest of the exact content that was shown,
//     so signing and then changing the content is detectable (I-4).
//
// Zero IO: the signature checking, the digest computing and the clock all
// arrive as values. The app layer supplies them inside one transaction.
package gate

import (
	"fmt"
	"time"
)

// Type is what a person is being asked to decide.
type Type string

// The gate types. The first six advance or close delivery; the last two are
// destructive and carry keyword requirements (domain/signoff enforces those).
const (
	TypeSealed         Type = "sealed"
	TypeAcceptedReq    Type = "accepted_req"
	TypeAcceptedArch   Type = "accepted_arch"
	TypeAcceptedPlan   Type = "accepted_plan"
	TypeAligned        Type = "aligned"
	TypeResolved       Type = "resolved"
	TypeStepConfirm    Type = "step_confirm"
	TypeDefectOrigin   Type = "defect_origin"
	TypeReopenBaseline Type = "reopen_baseline"
)

// Status is where a gate record is in its life.
type Status string

// Gate statuses.
const (
	StatusPending   Status = "pending"
	StatusApproved  Status = "approved"
	StatusRejected  Status = "rejected"
	StatusExpired   Status = "expired"
	StatusWithdrawn Status = "withdrawn"
)

// Assurance is how strongly the approver was authenticated.
//
// Only two levels, because the distinction that matters is whether a process
// running on the person's machine could have produced the approval. `low` is
// a local token plus a TTY: it stops a mistake and a hallucinated signature,
// not a determined forgery (design §10.4, threat T4). `high` requires a
// user-verifying authenticator — Touch ID or a PIN — which an agent cannot
// satisfy.
type Assurance string

// The assurance levels. Ordered: High satisfies a requirement for Low.
const (
	AssuranceLow  Assurance = "low"
	AssuranceHigh Assurance = "high"
)

func rank(a Assurance) int {
	if a == AssuranceHigh {
		return 2
	}
	return 1
}

// Satisfies reports whether an achieved assurance meets a requirement.
func (a Assurance) Satisfies(required Assurance) bool { return rank(a) >= rank(required) }

// RiskTier is the recipe's declared risk. P0 is the most dangerous.
type RiskTier string

// The risk tiers, from workflow_spec.RISK_TIERS.
const (
	RiskP0 RiskTier = "P0"
	RiskP1 RiskTier = "P1"
	RiskP2 RiskTier = "P2"
)

// SubjectKind says what the digest covers.
type SubjectKind string

// The subject kinds.
const (
	SubjectBaseline    SubjectKind = "baseline"
	SubjectArtifactSet SubjectKind = "artifact_set"
	SubjectRunStep     SubjectKind = "run_step"
)

// Subject is what the person is signing, identified by content rather than
// by name. The digest is the whole point: "I approve the baseline" is not
// checkable later, "I approve this manifest_root" is.
type Subject struct {
	Kind             SubjectKind
	Digest           string
	BaselineRevision int
}

// Gate is one pending question and its answer.
type Gate struct {
	ID      string
	Type    Type
	RunID   string
	StepID  string
	Feature string
	Risk    RiskTier

	Subject Subject
	// WillWrite is the list of fields the approval authorises writing. The
	// person sees it before answering; an approval that writes something
	// outside it is not the approval they gave.
	WillWrite []string
	// Proof is the evidence shown alongside the question — gate results,
	// case counts. chat-confirm-signoff.md forbids asking for a signature
	// on an agent summary alone.
	Proof string

	RequiredAssurance Assurance
	RequiredKeywords  []string

	Status    Status
	CreatedAt time.Time
	ExpiresAt time.Time
}

// Policy is the per-deployment assurance matrix. It may tighten the defaults
// and may not loosen them below the default, which is what keeps a
// configuration change from becoming a way around I-3.
type Policy struct {
	// Overrides is keyed by gate type. A value weaker than the default is
	// ignored (and reported by Validate).
	Overrides map[Type]Assurance
	// AllowLowForHigh is the documented P2-era transition switch: passkeys
	// land in P3, so until then a `high` requirement completes at `low` and
	// the audit records assurance_downgraded. Default false.
	AllowLowForHigh bool
}

// defaultAssurance is design §10.4's matrix: the row is the gate type, the
// column is the recipe's risk tier.
var defaultAssurance = map[Type]map[RiskTier]Assurance{
	TypeSealed:         {RiskP0: AssuranceHigh, RiskP1: AssuranceHigh, RiskP2: AssuranceLow},
	TypeReopenBaseline: {RiskP0: AssuranceHigh, RiskP1: AssuranceHigh, RiskP2: AssuranceLow},
	TypeAligned:        {RiskP0: AssuranceHigh, RiskP1: AssuranceHigh, RiskP2: AssuranceLow},
	TypeDefectOrigin:   {RiskP0: AssuranceHigh, RiskP1: AssuranceHigh, RiskP2: AssuranceLow},

	TypeAcceptedReq:  {RiskP0: AssuranceHigh, RiskP1: AssuranceLow, RiskP2: AssuranceLow},
	TypeAcceptedArch: {RiskP0: AssuranceHigh, RiskP1: AssuranceLow, RiskP2: AssuranceLow},
	TypeAcceptedPlan: {RiskP0: AssuranceHigh, RiskP1: AssuranceLow, RiskP2: AssuranceLow},
	TypeResolved:     {RiskP0: AssuranceHigh, RiskP1: AssuranceLow, RiskP2: AssuranceLow},

	TypeStepConfirm: {RiskP0: AssuranceLow, RiskP1: AssuranceLow, RiskP2: AssuranceLow},
}

// DefaultAssurance returns the matrix value for one cell.
func DefaultAssurance(t Type, risk RiskTier) (Assurance, error) {
	row, ok := defaultAssurance[t]
	if !ok {
		return "", fmt.Errorf("gate: unknown gate type %q", t)
	}
	a, ok := row[risk]
	if !ok {
		return "", fmt.Errorf("gate: unknown risk tier %q", risk)
	}
	return a, nil
}

// RequiredAssurance applies the policy on top of the matrix.
func (p Policy) RequiredAssurance(t Type, risk RiskTier) (Assurance, error) {
	base, err := DefaultAssurance(t, risk)
	if err != nil {
		return "", err
	}
	if over, ok := p.Overrides[t]; ok && rank(over) > rank(base) {
		return over, nil
	}
	return base, nil
}

// Validate reports policy entries that try to loosen the matrix. They are
// ignored rather than honoured, and saying so beats silently dropping them.
func (p Policy) Validate() []error {
	var out []error
	for t, want := range p.Overrides {
		for _, risk := range []RiskTier{RiskP0, RiskP1, RiskP2} {
			base, err := DefaultAssurance(t, risk)
			if err != nil {
				out = append(out, err)
				break
			}
			if rank(want) < rank(base) {
				out = append(out, fmt.Errorf(
					"gate: policy for %s at risk %s asks for %s but the floor is %s; ignored",
					t, risk, want, base))
			}
		}
	}
	return out
}

// RequiredKeywords is the keyword the quote must carry for a destructive
// gate. domain/signoff does the parsing; this says which to demand.
func RequiredKeywords(t Type, origin string) []string {
	switch t {
	case TypeDefectOrigin:
		return []string{"origin=" + origin}
	case TypeReopenBaseline:
		return []string{"解除密封", "reopen"}
	}
	return nil
}

// DefaultTTL is how long a question stays open. An unanswered gate expires
// back to ready rather than failing: nobody answering is not a refusal.
const DefaultTTL = 72 * time.Hour

// Request is the input to Open.
type Request struct {
	ID      string
	Type    Type
	RunID   string
	StepID  string
	Feature string
	Risk    RiskTier
	Subject Subject
	// Origin is required for defect_origin.
	Origin    string
	WillWrite []string
	Proof     string
	Now       time.Time
	TTL       time.Duration
}

// Open creates a pending gate.
//
// The guards here are the ones chat-confirm-signoff.md states as rules for
// asking: name the fields that will be written, show the proof, and identify
// the content by digest.
func Open(p Policy, r Request) (Gate, error) {
	if r.ID == "" {
		return Gate{}, fmt.Errorf("gate: a gate needs an id")
	}
	assurance, err := p.RequiredAssurance(r.Type, r.Risk)
	if err != nil {
		return Gate{}, err
	}
	if r.Subject.Digest == "" {
		return Gate{}, fmt.Errorf(
			"gate: %s has no subject digest; an approval must bind to content, not to a name", r.Type)
	}
	if r.Type == TypeSealed || r.Type == TypeReopenBaseline {
		if r.Subject.Kind != SubjectBaseline {
			return Gate{}, fmt.Errorf("gate: %s signs a baseline, not %s", r.Type, r.Subject.Kind)
		}
		if r.Subject.BaselineRevision <= 0 {
			return Gate{}, fmt.Errorf("gate: %s needs the baseline revision it refers to", r.Type)
		}
	}
	if r.Type == TypeDefectOrigin && r.Origin == "" {
		return Gate{}, fmt.Errorf("gate: defect_origin must name the origin it is asking about")
	}
	// A writing gate has to say what it writes. step_confirm is the
	// exception: it confirms an action, not a field.
	if len(r.WillWrite) == 0 && r.Type != TypeStepConfirm {
		return Gate{}, fmt.Errorf(
			"gate: %s must list the fields it will write, so the person can see what they are signing", r.Type)
	}
	if r.Proof == "" && r.Type != TypeStepConfirm {
		return Gate{}, fmt.Errorf(
			"gate: %s must show its proof; asking for a signature on a summary alone is forbidden", r.Type)
	}

	ttl := r.TTL
	if ttl <= 0 {
		ttl = DefaultTTL
	}
	return Gate{
		ID: r.ID, Type: r.Type, RunID: r.RunID, StepID: r.StepID,
		Feature: r.Feature, Risk: r.Risk, Subject: r.Subject,
		WillWrite: r.WillWrite, Proof: r.Proof,
		RequiredAssurance: assurance,
		RequiredKeywords:  RequiredKeywords(r.Type, r.Origin),
		Status:            StatusPending,
		CreatedAt:         r.Now,
		ExpiresAt:         r.Now.Add(ttl),
	}, nil
}

// PrincipalKind distinguishes a person from the things that are not one.
type PrincipalKind string

// The principal kinds.
const (
	PrincipalHuman   PrincipalKind = "human"
	PrincipalAgent   PrincipalKind = "agent"
	PrincipalService PrincipalKind = "service"
)

// Approver is the authenticated identity submitting a decision. `By` is
// never supplied by the caller: it is the handle of the authenticated
// principal (design §10.2, threat T1).
type Approver struct {
	Handle string
	Kind   PrincipalKind
	// HasApproverRole and ScopeCoversFeature come from the authz layer.
	HasApproverRole    bool
	ScopeCoversFeature bool
	Assurance          Assurance
}

// Decision is approve or reject.
type Decision string

// The decisions.
const (
	DecisionApprove Decision = "approve"
	DecisionReject  Decision = "reject"
)

// Submission is one answer to a gate.
type Submission struct {
	Decision Decision
	Approver Approver
	// QuoteOK and QuoteKeywords come from domain/signoff: this package does
	// not re-parse the sentence, it only insists the parse happened and
	// succeeded.
	QuoteOK       bool
	QuoteKeywords []string
	// RecomputedDigest is the digest of the content *now*. Compared against
	// what the person was shown, so signing and then editing is caught.
	RecomputedDigest string
	ApprovalID       string
	Now              time.Time
}

// Outcome is what Decide produced.
type Outcome struct {
	Gate Gate
	// Downgraded is true when a `high` requirement was met at `low` under
	// the transition switch. The audit record must say so.
	Downgraded bool
}

// RejectReason names why a submission was refused, for audit and for telling
// the person what to do.
type RejectReason string

// The refusal reasons.
const (
	ReasonNotPending     RejectReason = "not-pending"
	ReasonExpired        RejectReason = "expired"
	ReasonNotHuman       RejectReason = "not-human"
	ReasonNotApprover    RejectReason = "not-approver"
	ReasonOutOfScope     RejectReason = "out-of-scope"
	ReasonWeakAssurance  RejectReason = "weak-assurance"
	ReasonQuoteRejected  RejectReason = "quote-rejected"
	ReasonKeywordMissing RejectReason = "keyword-missing"
	ReasonDigestMismatch RejectReason = "digest-mismatch"
	ReasonNoApprovalID   RejectReason = "no-approval-id"
)

// Error is a refused submission.
type Error struct {
	GateID string
	Reason RejectReason
	Detail string
}

func (e *Error) Error() string {
	return fmt.Sprintf("gate %s: %s: %s", e.GateID, e.Reason, e.Detail)
}

func deny(g Gate, reason RejectReason, detail string) error {
	return &Error{GateID: g.ID, Reason: reason, Detail: detail}
}

// Decide applies a submission to a gate.
//
// The order of the checks is deliberate: identity before authentication
// strength before content, so the audit record names the first thing that
// was wrong rather than the last.
func Decide(g Gate, p Policy, s Submission) (Outcome, error) {
	if g.Status != StatusPending {
		return Outcome{}, deny(g, ReasonNotPending, "this gate was already "+string(g.Status))
	}
	if !g.ExpiresAt.IsZero() && s.Now.After(g.ExpiresAt) {
		return Outcome{}, deny(g, ReasonExpired, "the question expired; ask again")
	}
	// I-3. An agent token cannot reach this, and if one did, this is where
	// it stops.
	if s.Approver.Kind != PrincipalHuman {
		return Outcome{}, deny(g, ReasonNotHuman,
			fmt.Sprintf("%q is a %s; only a person signs", s.Approver.Handle, s.Approver.Kind))
	}
	if !s.Approver.HasApproverRole {
		return Outcome{}, deny(g, ReasonNotApprover, s.Approver.Handle+" has no approver role")
	}
	if !s.Approver.ScopeCoversFeature {
		return Outcome{}, deny(g, ReasonOutOfScope,
			s.Approver.Handle+"'s scope does not cover "+g.Feature)
	}

	downgraded := false
	if !s.Approver.Assurance.Satisfies(g.RequiredAssurance) {
		transitionAllows := p.AllowLowForHigh && g.RequiredAssurance == AssuranceHigh
		if !transitionAllows {
			return Outcome{}, deny(g, ReasonWeakAssurance,
				fmt.Sprintf("this gate needs %s authentication, got %s",
					g.RequiredAssurance, s.Approver.Assurance))
		}
		downgraded = true
	}

	if s.Decision == DecisionReject {
		out := g
		out.Status = StatusRejected
		return Outcome{Gate: out, Downgraded: downgraded}, nil
	}

	if !s.QuoteOK {
		return Outcome{}, deny(g, ReasonQuoteRejected, "the quote is not a confirmation")
	}
	if missing := missingKeyword(g.RequiredKeywords, s.QuoteKeywords); missing != "" {
		return Outcome{}, deny(g, ReasonKeywordMissing, "the quote must contain "+missing)
	}
	// I-4: signing and then editing is the failure this catches.
	if s.RecomputedDigest != g.Subject.Digest {
		return Outcome{}, deny(g, ReasonDigestMismatch,
			"the content changed after the question was asked; ask again")
	}
	if s.ApprovalID == "" {
		return Outcome{}, deny(g, ReasonNoApprovalID,
			"an approval that is not recorded cannot be verified later")
	}

	out := g
	out.Status = StatusApproved
	return Outcome{Gate: out, Downgraded: downgraded}, nil
}

// missingKeyword returns "" when the quote satisfies the requirement.
// RequiredKeywords is a disjunction: reopen_baseline accepts either word.
func missingKeyword(required, got []string) string {
	if len(required) == 0 {
		return ""
	}
	have := make(map[string]bool, len(got))
	for _, k := range got {
		have[k] = true
	}
	for _, want := range required {
		if have[want] {
			return ""
		}
	}
	if len(required) == 1 {
		return required[0]
	}
	return "one of " + fmt.Sprint(required)
}

// Withdraw cancels a pending question, for when the conductor realises it
// asked the wrong thing.
func Withdraw(g Gate, note string) (Gate, error) {
	if g.Status != StatusPending {
		return g, deny(g, ReasonNotPending, "this gate was already "+string(g.Status))
	}
	if note == "" {
		return g, &Error{GateID: g.ID, Reason: ReasonNotPending, Detail: "withdrawing needs a note"}
	}
	out := g
	out.Status = StatusWithdrawn
	return out, nil
}

// Expire marks a question nobody answered.
func Expire(g Gate, now time.Time) (Gate, error) {
	if g.Status != StatusPending {
		return g, deny(g, ReasonNotPending, "this gate was already "+string(g.Status))
	}
	if !now.After(g.ExpiresAt) {
		return g, deny(g, ReasonNotPending, "this gate has not expired yet")
	}
	out := g
	out.Status = StatusExpired
	return out, nil
}

// Types lists every gate type, for callers that render the matrix.
func Types() []Type {
	return []Type{
		TypeSealed, TypeAcceptedReq, TypeAcceptedArch, TypeAcceptedPlan,
		TypeAligned, TypeResolved, TypeStepConfirm, TypeDefectOrigin, TypeReopenBaseline,
	}
}
