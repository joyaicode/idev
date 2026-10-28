package gatesvc_test

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/memstore"
	"github.com/idev/internal/app/gatesvc"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/canonical"
)

// The tests pin the gate service's promises: a decision is bound to what
// the approver actually said and to the content they were shown (I-4),
// the destructive gate types demand their keywords (I-5), a decision and
// its audit event land in one transaction or not at all (I-6), and a
// gate is answered at most once (T6). Running through all of it is I-3:
// the one thing an agent must not be able to produce is a human
// signature, so every path to a recorded approval crosses the authz
// questions and a real key.

var at = time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)

// baseDigest is the digest of the content the approver was shown. The
// service never sees the content itself; it only compares digests.
const baseDigest = "sha256:6f4a0c0de5e2a2a8a3d1f0b19c8e7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f"

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

type seqIDs struct{ n int }

func (g *seqIDs) New() string {
	g.n++
	return fmt.Sprintf("01LGT0000000000000000000%02d", g.n)
}

// edSigner is a real ed25519 key pair. Approvals are signed with real
// cryptography so the tampering tests exercise the exact bytes an
// offline verifier will rebuild; a fake that signs everything with a
// constant would pass while binding nothing.
type edSigner struct {
	pub  ed25519.PublicKey
	priv ed25519.PrivateKey
}

func newSigner(t *testing.T) *edSigner {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("ed25519.GenerateKey: %v", err)
	}
	return &edSigner{pub: pub, priv: priv}
}

// keyID is the shape a stored signature names its key by: ed25519:
// followed by 16 hex characters.
func (s *edSigner) keyID() string {
	return "ed25519:" + hex.EncodeToString(s.pub[:8])
}

func (s *edSigner) Sign(ctx context.Context, payload []byte) ([]byte, string, error) {
	return ed25519.Sign(s.priv, payload), s.keyID(), nil
}

func (s *edSigner) Verify(ctx context.Context, payload, sig []byte, keyID string) error {
	if keyID != s.keyID() {
		return fmt.Errorf("unknown key %s", keyID)
	}
	if !ed25519.Verify(s.pub, payload, sig) {
		return errors.New("the signature does not verify")
	}
	return nil
}

func (s *edSigner) KeyID(ctx context.Context) (string, error) { return s.keyID(), nil }

// askz answers the authorizer's two questions and records every one, so
// the tests can pin exactly what the service asked: the wildcard
// question — does the principal hold gate.approve at all — and then the
// feature question — is this feature theirs to approve.
type askz struct {
	asked  []string
	role   bool
	scopes map[string]bool
}

func (a *askz) Can(ctx context.Context, p ports.Principal, action, scope string) bool {
	a.asked = append(a.asked, action+" "+scope)
	if scope == "*" {
		return a.role
	}
	return a.scopes[scope]
}

func newSvc(t *testing.T) (gatesvc.Service, *memstore.Store, *askz) {
	t.Helper()
	st := memstore.New()
	az := &askz{role: true, scopes: map[string]bool{"f-1": true}}
	s := gatesvc.Service{
		Store:      st,
		Clock:      fixedClock{t: at},
		IDs:        &seqIDs{},
		Signer:     newSigner(t),
		Authorizer: az,
	}
	return s, st, az
}

func conductor() ports.Principal {
	return ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "wangwei794"}
}

// human is the approver. Only a person's answer is worth a signature.
func human() ports.Principal {
	return ports.Principal{Handle: "wangwei794", Kind: "human"}
}

// sealParams asks the question a P0 baseline seal needs. Tests lower the
// risk when they want a gate answerable from a logged-in session.
func sealParams() gatesvc.AskParams {
	return gatesvc.AskParams{
		Type:    gate.TypeSealed,
		RunID:   "r-1",
		StepID:  "seal-baseline",
		Feature: "f-1",
		Risk:    gate.RiskP0,
		Subject: gate.Subject{
			Kind:             gate.SubjectBaseline,
			Digest:           baseDigest,
			BaselineRevision: 3,
		},
		WillWrite: []string{"baseline/repo-state.yaml"},
		Proof:     "run 01AR finished green; the report is attached",
		Actor:     conductor(),
	}
}

// answerParams is a person's yes to the gate the test opened: the words
// they signed, the digest they were shown, over a logged-in session.
func answerParams(gateID, quote string) gatesvc.DecisionParams {
	return gatesvc.DecisionParams{
		GateID:           gateID,
		Quote:            quote,
		Channel:          gatesvc.ChannelOIDC,
		RecomputedDigest: baseDigest,
		Actor:            human(),
	}
}

func ask(t *testing.T, s gatesvc.Service, p gatesvc.AskParams) gate.Gate {
	t.Helper()
	g, err := s.Ask(context.Background(), p)
	if err != nil {
		t.Fatalf("Ask: %v", err)
	}
	return g
}

func decide(t *testing.T, s gatesvc.Service, p gatesvc.DecisionParams) gatesvc.Decision {
	t.Helper()
	d, err := s.Decide(context.Background(), p)
	if err != nil {
		t.Fatalf("Decide: %v", err)
	}
	return d
}

// wantGateErr is the refusal every negative test expects: a *gate.Error
// with its reason, wrapped or not.
func wantGateErr(t *testing.T, err error, reason gate.RejectReason, what string) {
	t.Helper()
	var ge *gate.Error
	if !errors.As(err, &ge) || ge.Reason != reason {
		t.Fatalf("%s: err = %v, want a gate refusal with reason %s", what, err, reason)
	}
}

func wantConflict(t *testing.T, err error, kind, what string) {
	t.Helper()
	var ce *ports.ConflictError
	if !errors.As(err, &ce) || ce.Kind != kind {
		t.Fatalf("%s: err = %v, want a %s conflict", what, err, kind)
	}
}

func TestAskOpensAGateAndRecordsIt(t *testing.T) {
	s, st, _ := newSvc(t)
	g := ask(t, s, sealParams())

	if g.Status != gate.StatusPending || g.RequiredAssurance != gate.AssuranceHigh {
		t.Errorf("gate = %s needing %s, want a pending question needing high", g.Status, g.RequiredAssurance)
	}
	if len(g.RequiredKeywords) != 0 {
		t.Errorf("a sealed gate demands keywords %v; only the destructive types do", g.RequiredKeywords)
	}
	if !g.CreatedAt.Equal(at) || !g.ExpiresAt.Equal(at.Add(72*time.Hour)) {
		t.Errorf("asked at %v until %v, want %v for the default 72h", g.CreatedAt, g.ExpiresAt, at)
	}
	// What was asked is readable back; the return value is not the store.
	if got, err := s.Get(context.Background(), g.ID); err != nil || got.ID != g.ID || got.Status != gate.StatusPending {
		t.Errorf("Get(%s) = %s, %v; the gate never reached the store", g.ID, got.Status, err)
	}

	events := st.Events()
	if len(events) != 1 || events[0].Action != audit.ActionGateRequested {
		t.Fatalf("audit = %v, want one gate.requested", events)
	}
	e := events[0]
	if e.Subject != g.ID || e.RunID != "r-1" || e.StepID != "seal-baseline" || e.Feature != "f-1" {
		t.Errorf("event scope = %s/%s/%s for %s", e.RunID, e.StepID, e.Feature, e.Subject)
	}
	if !e.At.Equal(at) {
		t.Errorf("At = %v, want the clock's %v", e.At, at)
	}
	if e.Actor.Handle != "conductor@claude" || e.Actor.Kind != "agent" || e.Actor.OnBehalfOf != "wangwei794" {
		t.Errorf("actor = %+v, want the conductor acting for a person", e.Actor)
	}
	want := map[string]any{
		"gate_type":          "sealed",
		"risk":               "P0",
		"subject_digest":     baseDigest,
		"required_assurance": "high",
		"will_write":         []string{"baseline/repo-state.yaml"},
		"expires_at":         at.Add(72 * time.Hour).Format(time.RFC3339),
	}
	if !reflect.DeepEqual(e.Detail, want) {
		t.Errorf("detail = %v, want %v", e.Detail, want)
	}
}

func TestAskDerivesTheKeywordsForDestructiveGates(t *testing.T) {
	s, st, _ := newSvc(t)

	p := sealParams()
	p.Type = gate.TypeDefectOrigin
	p.Risk = gate.RiskP2
	p.Subject = gate.Subject{Kind: gate.SubjectRunStep, Digest: baseDigest}
	p.Origin = "req"
	p.StepID = "triage-defect"
	p.WillWrite = []string{"tickets/F-2/defect.yaml"}
	p.TTL = time.Hour
	dg := ask(t, s, p)

	// I-5: the keywords are the question's. The approver cannot answer
	// "origin=req" without knowing where the defect came from.
	if !reflect.DeepEqual(dg.RequiredKeywords, []string{"origin=req"}) {
		t.Errorf("defect keywords = %v, want [origin=req]", dg.RequiredKeywords)
	}
	if want := at.Add(time.Hour); !dg.ExpiresAt.Equal(want) {
		t.Errorf("deadline = %v, want %v (the TTL the caller gave)", dg.ExpiresAt, want)
	}
	if dg.RequiredAssurance != gate.AssuranceLow {
		t.Errorf("a P2 defect question demands %s assurance", dg.RequiredAssurance)
	}

	p = sealParams()
	p.Type = gate.TypeReopenBaseline
	p.Risk = gate.RiskP1
	p.StepID = "reopen-baseline"
	rg := ask(t, s, p)

	if !reflect.DeepEqual(rg.RequiredKeywords, []string{"解除密封", "reopen"}) {
		t.Errorf("reopen keywords = %v, want [解除密封 reopen]", rg.RequiredKeywords)
	}
	if rg.RequiredAssurance != gate.AssuranceHigh {
		t.Errorf("a P1 reopen question demands %s; a reopened baseline is a destructive act", rg.RequiredAssurance)
	}

	events := st.Events()
	if len(events) != 2 {
		t.Fatalf("%d events, want one per question", len(events))
	}
	if got := events[0].Detail["required_keywords"]; !reflect.DeepEqual(got, []string{"origin=req"}) {
		t.Errorf("defect event required_keywords = %v", got)
	}
	if got := events[1].Detail["required_keywords"]; !reflect.DeepEqual(got, []string{"解除密封", "reopen"}) {
		t.Errorf("reopen event required_keywords = %v", got)
	}
}

func TestAskRefusesASecondPendingGateForTheStep(t *testing.T) {
	s, st, _ := newSvc(t)
	g := ask(t, s, sealParams())

	// The step already has an open question; a second would be two ways
	// to answer the same thing (T6's asking-side twin).
	_, err := s.Ask(context.Background(), sealParams())
	wantConflict(t, err, ports.ConflictGatePending, "a second pending gate for the step")
	if len(st.Events()) != 1 {
		t.Errorf("%d events; a refused question must not be recorded", len(st.Events()))
	}

	// Once the first question is withdrawn the step is free again.
	if _, err := s.Withdraw(context.Background(), g.ID, "asked the wrong thing", conductor()); err != nil {
		t.Fatalf("Withdraw: %v", err)
	}
	if _, err := s.Ask(context.Background(), sealParams()); err != nil {
		t.Fatalf("asking again after a withdrawal: %v", err)
	}
	if len(st.Events()) != 3 { // requested, withdrawn, requested
		t.Errorf("%d events, want request/withdrawal/re-request", len(st.Events()))
	}
}

func TestAskRefusesAGateItCannotAskFor(t *testing.T) {
	s, st, _ := newSvc(t)

	mut := func(f func(*gatesvc.AskParams)) gatesvc.AskParams {
		p := sealParams()
		f(&p)
		return p
	}
	for _, tc := range []struct {
		what string
		p    gatesvc.AskParams
	}{
		{"no feature", mut(func(p *gatesvc.AskParams) { p.Feature = "" })},
		{"no subject digest", mut(func(p *gatesvc.AskParams) { p.Subject.Digest = "" })},
		{"a seal of a non-baseline subject", mut(func(p *gatesvc.AskParams) {
			p.Subject = gate.Subject{Kind: gate.SubjectRunStep, Digest: baseDigest, BaselineRevision: 3}
		})},
		{"a seal of revision zero", mut(func(p *gatesvc.AskParams) { p.Subject.BaselineRevision = 0 })},
		{"a defect question without an origin", mut(func(p *gatesvc.AskParams) {
			p.Type = gate.TypeDefectOrigin
			p.Subject = gate.Subject{Kind: gate.SubjectRunStep, Digest: baseDigest}
		})},
		{"no fields it will write", mut(func(p *gatesvc.AskParams) { p.WillWrite = nil })},
		{"no proof", mut(func(p *gatesvc.AskParams) { p.Proof = "" })},
		{"an unknown gate type", mut(func(p *gatesvc.AskParams) { p.Type = gate.Type("trust-me") })},
		{"an unknown risk", mut(func(p *gatesvc.AskParams) { p.Risk = gate.RiskTier("P9") })},
	} {
		if _, err := s.Ask(context.Background(), tc.p); err == nil {
			t.Errorf("%s: a gate was opened", tc.what)
		}
	}
	if len(st.Events()) != 0 {
		t.Error("a refused question wrote an audit event")
	}

	// A step confirmation is the one type that asks nothing but the
	// person's yes: no writes to declare, no proof to show.
	p := sealParams()
	p.Type = gate.TypeStepConfirm
	p.Subject = gate.Subject{Kind: gate.SubjectRunStep, Digest: baseDigest}
	p.WillWrite, p.Proof = nil, ""
	g := ask(t, s, p)
	if g.RequiredAssurance != gate.AssuranceLow {
		t.Errorf("a step confirm demands %s; nobody should need hardware to confirm a step", g.RequiredAssurance)
	}
}

func TestDecideRecordsASignedApproval(t *testing.T) {
	s, st, az := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2 // a P2 seal is answerable from a logged-in session
	g := ask(t, s, p)

	d := decide(t, s, answerParams(g.ID, "全签 sealed 基线"))

	if d.Gate.Status != gate.StatusApproved {
		t.Errorf("gate = %s, want approved", d.Gate.Status)
	}
	a := d.Approval
	if a.ID == "" || a.GateID != g.ID || a.GateType != "sealed" || a.Decision != string(gate.DecisionApprove) {
		t.Errorf("approval = %+v, want one for %s deciding approve", a, g.ID)
	}
	if a.SubjectDigest != canonical.Digest(baseDigest) || a.Quote != "全签 sealed 基线" || a.Channel != gatesvc.ChannelOIDC {
		t.Errorf("approval = %+v; it must record what was signed and how it arrived", a)
	}
	if a.Handle != "wangwei794" || a.Kind != "human" || a.Assurance != string(gate.AssuranceLow) || a.Downgraded {
		t.Errorf("approval = %+v; the approver and their channel are wrong", a)
	}
	if !a.DecidedAt.Equal(at) {
		t.Errorf("decided at %v, want the clock's %v", a.DecidedAt, at)
	}

	// The two authz questions, in order: the role, then the feature.
	if want := []string{"gate.approve *", "gate.approve f-1"}; !reflect.DeepEqual(az.asked, want) {
		t.Errorf("the service asked %v, want %v", az.asked, want)
	}

	// A real signature over the exact payload, in the record's shape.
	var rec struct {
		Alg   string `json:"alg"`
		KeyID string `json:"key_id"`
		Value string `json:"value"`
	}
	if err := json.Unmarshal(a.Signature, &rec); err != nil {
		t.Fatalf("the signature is not a record: %v", err)
	}
	keyID, err := s.Signer.KeyID(context.Background())
	if err != nil {
		t.Fatalf("KeyID: %v", err)
	}
	if rec.Alg != "ed25519" || rec.KeyID != keyID {
		t.Errorf("signature record = %+v, want ed25519 by %s", rec, keyID)
	}
	if sig, err := hex.DecodeString(rec.Value); err != nil || len(sig) != ed25519.SignatureSize {
		t.Errorf("signature value = %q (%v)", rec.Value, err)
	}
	if err := s.VerifyApproval(context.Background(), a); err != nil {
		t.Errorf("the recorded approval does not verify: %v", err)
	}

	// And it is the store's copy, not just the return value's.
	stored, err := s.Approval(context.Background(), a.ID)
	if err != nil || stored.ID != a.ID || !reflect.DeepEqual(stored.Signature, a.Signature) {
		t.Errorf("Approval(%s) = %+v, %v; the record never reached the store", a.ID, stored, err)
	}

	events := st.Events()
	if len(events) != 2 || events[1].Action != audit.ActionGateApproved {
		t.Fatalf("audit = %v, want gate.requested then gate.approved", events)
	}
	e := events[1]
	if e.Subject != a.ID || e.RunID != "r-1" || e.StepID != "seal-baseline" || e.Feature != "f-1" {
		t.Errorf("event scope = %s/%s/%s for %s", e.RunID, e.StepID, e.Feature, e.Subject)
	}
	if e.Actor.Handle != "wangwei794" || e.Actor.Kind != "human" || e.Actor.OnBehalfOf != "" {
		t.Errorf("actor = %+v, want the person themselves", e.Actor)
	}
	if want := map[string]any{
		"gate_id":   g.ID,
		"gate_type": "sealed",
		"assurance": "low",
	}; !reflect.DeepEqual(e.Detail, want) {
		t.Errorf("detail = %v, want %v", e.Detail, want)
	}
}

// I-3: the questions are asked in a fixed order — is this a person, do they
// hold the role, is the feature theirs — and the first no ends the attempt
// without touching the gate.
func TestDecideRequiresAHumanWithRoleAndScope(t *testing.T) {
	s, st, az := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2
	g := ask(t, s, p)

	// An agent may open gates, but it may not answer them. Both authz
	// questions are still asked on the way in: the refusal must be able to
	// name what the agent failed, and a nil authorizer is one of them.
	a := answerParams(g.ID, "全签 sealed 基线")
	a.Actor = conductor()
	_, err := s.Decide(context.Background(), a)
	wantGateErr(t, err, gate.ReasonNotHuman, "an agent answering")
	if got, err := s.Get(context.Background(), g.ID); err != nil || got.Status != gate.StatusPending {
		t.Errorf("gate = %s (%v); a refused answer must leave it pending", got.Status, err)
	}
	if want := []string{"gate.approve *", "gate.approve f-1"}; !reflect.DeepEqual(az.asked, want) {
		t.Errorf("the service asked %v, want %v", az.asked, want)
	}
	if n := len(st.Events()); n != 1 {
		t.Errorf("%d events after a refused answer, want only the ask", n)
	}

	// A person without the role fails the second question.
	a.Actor = human()
	az.role = false
	_, err = s.Decide(context.Background(), a)
	wantGateErr(t, err, gate.ReasonNotApprover, "a person without the role")

	// The role but not the feature fails the third.
	az.role = true
	az.scopes = map[string]bool{"f-2": true}
	_, err = s.Decide(context.Background(), a)
	wantGateErr(t, err, gate.ReasonOutOfScope, "an approver of another feature")

	// And a service with no authorizer wired cannot vouch for anyone: it
	// can open gates, but nobody passes one.
	s.Authorizer = nil
	_, err = s.Decide(context.Background(), a)
	wantGateErr(t, err, gate.ReasonNotApprover, "no authorizer wired")
}

// Assurance is not chosen by the answerer; it follows from the channel the
// answer arrived on. A P0 seal demands high assurance, so a logged-in
// session cannot pass it — and the refusal leaves the gate open for an
// authenticator to answer.
func TestTheChannelDecidesTheAssurance(t *testing.T) {
	s, st, _ := newSvc(t)
	g := ask(t, s, sealParams()) // P0: high assurance required

	a := answerParams(g.ID, "全签 sealed 基线") // oidc proves low
	_, err := s.Decide(context.Background(), a)
	wantGateErr(t, err, gate.ReasonWeakAssurance, "a P0 gate answered from a logged-in session")
	if got, _ := s.Get(context.Background(), g.ID); got.Status != gate.StatusPending {
		t.Errorf("gate = %s; a weak answer must leave it pending", got.Status)
	}
	if n := len(st.Events()); n != 1 {
		t.Errorf("%d events after a weak answer, want only the ask", n)
	}

	// The same person, the same words, over an authenticator: high
	// assurance, and the approval records how it arrived.
	a.Channel = gatesvc.ChannelWebAuthn
	d := decide(t, s, a)
	if d.Approval.Assurance != string(gate.AssuranceHigh) || d.Approval.Channel != gatesvc.ChannelWebAuthn {
		t.Errorf("approval = %+v; assurance must follow the channel", d.Approval)
	}
	if d.Approval.Downgraded {
		t.Error("a webauthn answer meets the requirement; it is not a downgrade")
	}
	if n := len(st.Events()); n != 2 {
		t.Errorf("%d events, want the ask and the approval", n)
	}
}

// The documented transition switch: policy may let a low answer pass a
// high gate, but the approval is marked and the chain gets an
// assurance.downgraded event — the switch must be visible, not silent.
func TestPolicyMayDowngradeAssurance(t *testing.T) {
	s, st, _ := newSvc(t)
	s.Policy = gate.Policy{AllowLowForHigh: true}
	g := ask(t, s, sealParams()) // P0 demands high

	d := decide(t, s, answerParams(g.ID, "全签 sealed 基线")) // oidc proves low
	if d.Gate.Status != gate.StatusApproved {
		t.Errorf("gate = %s, want approved under the switch", d.Gate.Status)
	}
	if !d.Approval.Downgraded || d.Approval.Assurance != string(gate.AssuranceLow) {
		t.Errorf("approval = %+v; it must record what was proved, not what was required", d.Approval)
	}

	events := st.Events()
	if len(events) != 3 || events[2].Action != audit.ActionAssuranceDowngraded {
		t.Fatalf("audit = %v, want requested, approved, assurance.downgraded", events)
	}
	e := events[2]
	if want := map[string]any{
		"gate_id":     g.ID,
		"approval_id": d.Approval.ID,
		"required":    "high",
		"achieved":    "low",
	}; !reflect.DeepEqual(e.Detail, want) {
		t.Errorf("downgrade detail = %v, want %v", e.Detail, want)
	}
}

// Any sentence approves. The quote is stored, not parsed.
func TestAnySentenceApproves(t *testing.T) {
	s, _, _ := newSvc(t)
	for _, quote := range []string{"", "继续", "同意吗", "确认不了", "不要密封", "sealed 基线"} {
		p := sealParams()
		p.Risk = gate.RiskP2
		g := ask(t, s, p)
		d, err := s.Decide(context.Background(), answerParams(g.ID, quote))
		if err != nil || d.Gate.Status != gate.StatusApproved {
			t.Fatalf("%q: %v status %s", quote, err, d.Gate.Status)
		}
	}

	p := sealParams()
	p.Type = gate.TypeReopenBaseline
	p.Risk = gate.RiskP2
	p.Proof = "the run regressed; the baseline must reopen"
	r := ask(t, s, p)
	d, err := s.Decide(context.Background(), answerParams(r.ID, "确认"))
	if err != nil || d.Gate.Status != gate.StatusApproved {
		t.Fatalf("reopen without a keyword: %v status %s", err, d.Gate.Status)
	}
}

// I-4: an approval binds to the content the person was shown. The service
// never sees the content; it compares the digest of what is there now
// against what the gate recorded, and a change is a refusal to be shown to
// the person again — not an error for the caller to retry against.
func TestDecideBindsTheApprovalToTheContent(t *testing.T) {
	s, st, _ := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2
	g := ask(t, s, p)

	a := answerParams(g.ID, "全签 sealed 基线")
	a.RecomputedDigest = "sha256:" + strings.Repeat("0", 64) // the repo moved
	_, err := s.Decide(context.Background(), a)
	wantGateErr(t, err, gate.ReasonDigestMismatch, "deciding against changed content")
	if got, _ := s.Get(context.Background(), g.ID); got.Status != gate.StatusPending {
		t.Errorf("gate = %s; changed content must not decide it", got.Status)
	}
	if n := len(st.Events()); n != 1 {
		t.Errorf("%d events, want only the ask", n)
	}

	// The digest is not optional: without it there is nothing to compare
	// against, and the guard says so before anything is read.
	a.RecomputedDigest = ""
	if _, err := s.Decide(context.Background(), a); err == nil {
		t.Error("an empty digest decided a gate; it must be refused")
	}
}

// The guards run before anything is read: a caller that cannot name the
// gate, the words, the channel or the digest gets its bug back as an
// error, not as a half-decided gate.
func TestDecideValidatesItsParameters(t *testing.T) {
	s, st, _ := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2
	g := ask(t, s, p)

	cases := []struct {
		what string
		mut  func(*gatesvc.DecisionParams)
	}{
		{"no gate id", func(a *gatesvc.DecisionParams) { a.GateID = "" }},
		{"no digest", func(a *gatesvc.DecisionParams) { a.RecomputedDigest = "" }},
		{"unknown channel", func(a *gatesvc.DecisionParams) { a.Channel = "sms" }},
	}
	for _, tc := range cases {
		a := answerParams(g.ID, "全签 sealed 基线")
		tc.mut(&a)
		if _, err := s.Decide(context.Background(), a); err == nil {
			t.Errorf("%s: Decide succeeded; it must refuse", tc.what)
		}
	}

	// A gate that was never asked is a not-found conflict, not a gate
	// refusal: the caller cannot show a person a question that does not
	// exist.
	_, err := s.Decide(context.Background(), answerParams("no-such-gate", "全签 sealed 基线"))
	wantConflict(t, err, ports.ConflictNotFound, "deciding an unknown gate")

	// A service that cannot sign cannot record an approval (I-3): an
	// unsigned approval is a claim, and the store must not hold claims.
	s.Signer = nil
	if _, err := s.Decide(context.Background(), answerParams(g.ID, "全签 sealed 基线")); err == nil {
		t.Error("a service with no signer decided a gate; it must refuse")
	}
	if got, _ := s.Get(context.Background(), g.ID); got.Status != gate.StatusPending {
		t.Errorf("gate = %s; it must still be pending", got.Status)
	}
	if n := len(st.Events()); n != 1 {
		t.Errorf("%d events, want only the ask", n)
	}
}

// T6: a gate is answered at most once, whatever order the submissions
// arrive in. The second yes is refused as not-pending; the same holds for
// a no — and a no needs nothing but the word 驳回.
func TestADecisionIsFinal(t *testing.T) {
	s, st, _ := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2
	g := ask(t, s, p)
	decide(t, s, answerParams(g.ID, "全签 sealed 基线"))

	_, err := s.Decide(context.Background(), answerParams(g.ID, "同意 sealed 基线"))
	wantGateErr(t, err, gate.ReasonNotPending, "a second answer to the same gate")

	// A rejection is still a decision: the gate closes rejected, and the
	// record carries the person's refusal. The digest is not rechecked —
	// rejecting changed content is not a risk, approving it is.
	p.StepID = "seal-baseline-2"
	g2 := ask(t, s, p)
	a := answerParams(g2.ID, "驳回")
	a.Decision = gate.DecisionReject
	a.RecomputedDigest = "sha256:" + strings.Repeat("0", 64)
	d := decide(t, s, a)
	if d.Gate.Status != gate.StatusRejected {
		t.Errorf("gate = %s, want rejected", d.Gate.Status)
	}
	if d.Approval.Decision != "reject" || d.Approval.Quote != "驳回" {
		t.Errorf("approval = %+v; it must record the refusal", d.Approval)
	}

	// And answering either gate again changes nothing.
	_, err = s.Decide(context.Background(), answerParams(g2.ID, "驳回"))
	wantGateErr(t, err, gate.ReasonNotPending, "a second answer to the rejected gate")

	events := st.Events()
	if len(events) != 4 {
		t.Fatalf("%d events, want ask, approve, ask, reject", len(events))
	}
	if events[3].Action != audit.ActionGateRejected || events[3].Subject != d.Approval.ID {
		t.Errorf("event = %+v; the chain must name the refusal", events[3])
	}
}

// A withdrawn question must leave a trace of why (the note), and only a
// pending question can be withdrawn — cancelling a decision that was
// already made is exactly what not-pending refuses.
func TestWithdrawNeedsAReasonAndAPendingGate(t *testing.T) {
	s, st, _ := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2
	g := ask(t, s, p)

	// A question that vanishes without a reason is indistinguishable from
	// one that was never asked.
	_, err := s.Withdraw(context.Background(), g.ID, "", conductor())
	wantGateErr(t, err, gate.ReasonNotPending, "a note-less withdraw")
	if got, _ := s.Get(context.Background(), g.ID); got.Status != gate.StatusPending {
		t.Errorf("gate = %s; it must still be pending", got.Status)
	}

	w, err := s.Withdraw(context.Background(), g.ID, "the run was aborted; the question is moot", conductor())
	if err != nil {
		t.Fatalf("Withdraw: %v", err)
	}
	if w.Status != gate.StatusWithdrawn {
		t.Errorf("gate = %s, want withdrawn", w.Status)
	}

	events := st.Events()
	if len(events) != 2 || events[1].Action != audit.ActionGateWithdrawn {
		t.Fatalf("audit = %v, want requested then withdrawn", events)
	}
	e := events[1]
	if e.Subject != g.ID || e.Detail["note"] != "the run was aborted; the question is moot" {
		t.Errorf("event = %+v; the note is the record's answer", e)
	}
	if e.Actor.Handle != "conductor@claude" || e.Actor.Kind != "agent" || e.Actor.OnBehalfOf != "wangwei794" {
		t.Errorf("actor = %+v; a withdraw is the conductor acting for its owner", e.Actor)
	}

	// The withdrawn gate is closed: no second withdraw, no late decision,
	// and no withdrawing a gate that was never asked.
	_, err = s.Withdraw(context.Background(), g.ID, "again", conductor())
	wantGateErr(t, err, gate.ReasonNotPending, "a second withdraw")
	_, err = s.Decide(context.Background(), answerParams(g.ID, "全签 sealed 基线"))
	wantGateErr(t, err, gate.ReasonNotPending, "deciding a withdrawn gate")
	_, err = s.Withdraw(context.Background(), "no-such-gate", "note", conductor())
	wantConflict(t, err, ports.ConflictNotFound, "withdrawing an unknown gate")
}

// Nobody answering is not a refusal: the gate expires, the run falls back,
// and the record names the sweeper — not a person, not the conductor.
func TestExpireMarksGatesNobodyAnswered(t *testing.T) {
	s, st, _ := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2
	p.TTL = time.Hour
	g := ask(t, s, p)
	deadline := at.Add(time.Hour)

	// Before the deadline the sweeper has nothing to do.
	_, err := s.Expire(context.Background(), g.ID)
	wantGateErr(t, err, gate.ReasonNotPending, "a gate that has not expired yet")

	// Ninety minutes later it does.
	s.Clock = fixedClock{t: at.Add(90 * time.Minute)}
	e, err := s.Expire(context.Background(), g.ID)
	if err != nil {
		t.Fatalf("Expire: %v", err)
	}
	if e.Status != gate.StatusExpired {
		t.Errorf("gate = %s, want expired", e.Status)
	}

	events := st.Events()
	if len(events) != 2 || events[1].Action != audit.ActionGateExpired {
		t.Fatalf("audit = %v, want requested then expired", events)
	}
	ev := events[1]
	if ev.Actor.Handle != "sweeper" || ev.Actor.Kind != "system" || ev.Actor.OnBehalfOf != "" {
		t.Errorf("actor = %+v; the sweeper is the system, nobody else", ev.Actor)
	}
	if ev.Subject != g.ID || ev.Detail["expires_at"] != deadline.Format(time.RFC3339) {
		t.Errorf("event = %+v; it must name the gate and its deadline", ev)
	}

	// Expiry is final too.
	_, err = s.Expire(context.Background(), g.ID)
	wantGateErr(t, err, gate.ReasonNotPending, "a second expiry")
	if n := len(st.Events()); n != 2 {
		t.Errorf("%d events, want no second expiry", n)
	}
}

// I-6: the decision, the gate and the audit event land in one transaction
// or not at all. Every failpoint below fires mid-decision; after each, the
// gate is untouched, the chain holds only the ask, and a retry with the
// fault cleared succeeds — proof that nothing from the failed attempt
// survived.
func TestAFailedDecisionLeavesNothingBehind(t *testing.T) {
	s, st, _ := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2
	g := ask(t, s, p)
	quote := "全签 sealed 基线"

	st.FailOn["gates.RecordApproval"] = errors.New("record: disk full")
	if _, err := s.Decide(context.Background(), answerParams(g.ID, quote)); err == nil {
		t.Fatal("decide succeeded against a failing store")
	}
	delete(st.FailOn, "gates.RecordApproval")

	st.FailOn["audit.Append"] = errors.New("audit: disk full")
	if _, err := s.Decide(context.Background(), answerParams(g.ID, quote)); err == nil {
		t.Fatal("decide succeeded against a failing audit trail")
	}
	delete(st.FailOn, "audit.Append")

	if got, _ := s.Get(context.Background(), g.ID); got.Status != gate.StatusPending {
		t.Fatalf("gate = %s after two failed attempts; nothing may land", got.Status)
	}
	if n := len(st.Events()); n != 1 {
		t.Fatalf("%d events after two failed attempts, want only the ask", n)
	}

	decide(t, s, answerParams(g.ID, quote)) // the retry succeeds
	if n := len(st.Events()); n != 2 {
		t.Errorf("%d events after the retry, want ask and approval", n)
	}

	// The ask is transactional the same way: a gate whose open failed was
	// never asked, so asking again is not a conflict — the approved gate
	// below blocks nothing.
	st.FailOn["gates.Open"] = errors.New("open: disk full")
	if _, err := s.Ask(context.Background(), p); err == nil {
		t.Fatal("ask succeeded against a failing store")
	}
	delete(st.FailOn, "gates.Open")
	ask(t, s, p)
}

// The signature covers the whole record — the words, the approver, the
// channel, the verdict. Change any one field after the fact and the
// verifier, which rebuilds the payload from the record it is handed, must
// refuse: that is what makes a stored approval evidence rather than a
// claim.
func TestVerifyApprovalCatchesTampering(t *testing.T) {
	s, _, _ := newSvc(t)
	p := sealParams()
	p.Risk = gate.RiskP2
	g := ask(t, s, p)
	d := decide(t, s, answerParams(g.ID, "全签 sealed 基线"))
	honest := d.Approval

	ctx := context.Background()
	if err := s.VerifyApproval(ctx, honest); err != nil {
		t.Fatalf("the honest approval does not verify: %v", err)
	}

	edits := []struct {
		what string
		edit func(*ports.Approval)
	}{
		{"the quote", func(a *ports.Approval) { a.Quote = "全签 sealed 基线 和提测" }},
		{"the approver", func(a *ports.Approval) { a.Handle = "someone-else" }},
		{"the channel", func(a *ports.Approval) { a.Channel = gatesvc.ChannelWebAuthn }},
		{"the verdict", func(a *ports.Approval) { a.Decision = "reject" }},
		{"the signature", func(a *ports.Approval) { a.Signature = []byte("not json") }},
	}
	for _, tc := range edits {
		a := honest
		tc.edit(&a)
		if err := s.VerifyApproval(ctx, a); err == nil {
			t.Errorf("tampering with %s still verifies", tc.what)
		}
	}

	// A different key: the record names its key, so an approval handed to
	// a service whose signer did not sign it fails at the key it names.
	s2 := s
	s2.Signer = newSigner(t)
	if err := s2.VerifyApproval(ctx, honest); err == nil {
		t.Error("the approval verifies under a key that did not sign it")
	}
}
