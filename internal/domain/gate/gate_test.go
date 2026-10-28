package gate_test

import (
	"errors"
	"testing"
	"time"

	"pgregory.net/rapid"

	"github.com/idev/internal/domain/gate"
)

var now = time.Date(2026, 10, 16, 9, 0, 0, 0, time.UTC)

func openSealed(t *testing.T, p gate.Policy, risk gate.RiskTier) gate.Gate {
	t.Helper()
	g, err := gate.Open(p, gate.Request{
		ID: "g1", Type: gate.TypeSealed, Feature: "demo", Risk: risk,
		Subject:   gate.Subject{Kind: gate.SubjectBaseline, Digest: "sha256:aaa", BaselineRevision: 1},
		WillWrite: []string{"baseline.sealed"}, Proof: "check-feature PASS",
		Now: now,
	})
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	return g
}

func person() gate.Approver {
	return gate.Approver{
		Handle: "wangwei794", Kind: gate.PrincipalHuman,
		HasApproverRole: true, ScopeCoversFeature: true, Assurance: gate.AssuranceHigh,
	}
}

func submit(g gate.Gate) gate.Submission {
	return gate.Submission{
		Decision: gate.DecisionApprove, Approver: person(),
		QuoteOK: true, RecomputedDigest: g.Subject.Digest,
		ApprovalID: "ap-1", Now: now,
	}
}

func denied(t *testing.T, err error, want gate.RejectReason) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected %s, got no error", want)
	}
	var ge *gate.Error
	if !errors.As(err, &ge) {
		t.Fatalf("error type = %T, want *gate.Error", err)
	}
	if ge.Reason != want {
		t.Fatalf("reason = %s, want %s (%s)", ge.Reason, want, ge.Detail)
	}
	if ge.Detail == "" {
		t.Error("a refusal with no detail cannot be shown to the person")
	}
}

// --- the assurance matrix --------------------------------------------------

func TestAssuranceMatrixMatchesTheDesign(t *testing.T) {
	// design §10.4. Destructive and delivery-closing gates need strong
	// authentication at P0 and P1; a plain step confirmation never does.
	cases := []struct {
		typ  gate.Type
		risk gate.RiskTier
		want gate.Assurance
	}{
		{gate.TypeSealed, gate.RiskP0, gate.AssuranceHigh},
		{gate.TypeSealed, gate.RiskP1, gate.AssuranceHigh},
		{gate.TypeSealed, gate.RiskP2, gate.AssuranceLow},
		{gate.TypeReopenBaseline, gate.RiskP1, gate.AssuranceHigh},
		{gate.TypeAligned, gate.RiskP1, gate.AssuranceHigh},
		{gate.TypeDefectOrigin, gate.RiskP1, gate.AssuranceHigh},
		{gate.TypeAcceptedReq, gate.RiskP0, gate.AssuranceHigh},
		{gate.TypeAcceptedReq, gate.RiskP1, gate.AssuranceLow},
		{gate.TypeAcceptedPlan, gate.RiskP1, gate.AssuranceLow},
		{gate.TypeResolved, gate.RiskP1, gate.AssuranceLow},
		{gate.TypeStepConfirm, gate.RiskP0, gate.AssuranceLow},
	}
	for _, tc := range cases {
		got, err := gate.DefaultAssurance(tc.typ, tc.risk)
		if err != nil {
			t.Errorf("%s/%s: %v", tc.typ, tc.risk, err)
			continue
		}
		if got != tc.want {
			t.Errorf("%s at %s = %s, want %s", tc.typ, tc.risk, got, tc.want)
		}
	}
	if _, err := gate.DefaultAssurance(gate.Type("invented"), gate.RiskP1); err == nil {
		t.Error("an unknown gate type must not get a default")
	}
	if _, err := gate.DefaultAssurance(gate.TypeSealed, gate.RiskTier("P9")); err == nil {
		t.Error("an unknown risk tier must not get a default")
	}
}

func TestEveryGateTypeHasAMatrixRow(t *testing.T) {
	// A new gate type with no row would silently get no requirement.
	for _, typ := range gate.Types() {
		for _, risk := range []gate.RiskTier{gate.RiskP0, gate.RiskP1, gate.RiskP2} {
			if _, err := gate.DefaultAssurance(typ, risk); err != nil {
				t.Errorf("%s at %s has no assurance requirement: %v", typ, risk, err)
			}
		}
	}
}

func TestPolicyCanTightenButNotLoosen(t *testing.T) {
	// Tightening works.
	tight := gate.Policy{Overrides: map[gate.Type]gate.Assurance{
		gate.TypeStepConfirm: gate.AssuranceHigh,
	}}
	got, err := tight.RequiredAssurance(gate.TypeStepConfirm, gate.RiskP2)
	if err != nil {
		t.Fatal(err)
	}
	if got != gate.AssuranceHigh {
		t.Errorf("tightened step_confirm = %s, want high", got)
	}
	if errs := tight.Validate(); len(errs) != 0 {
		t.Errorf("tightening must be accepted silently, got %v", errs)
	}

	// Loosening is ignored, and reported.
	loose := gate.Policy{Overrides: map[gate.Type]gate.Assurance{
		gate.TypeSealed: gate.AssuranceLow,
	}}
	got, err = loose.RequiredAssurance(gate.TypeSealed, gate.RiskP1)
	if err != nil {
		t.Fatal(err)
	}
	if got != gate.AssuranceHigh {
		t.Fatalf("sealed at P1 = %s; a policy must not drop the floor", got)
	}
	if errs := loose.Validate(); len(errs) == 0 {
		t.Error("a loosening policy must be reported, not silently dropped")
	}
}

func TestPolicyValidateReportsUnknownTypes(t *testing.T) {
	p := gate.Policy{Overrides: map[gate.Type]gate.Assurance{
		gate.Type("invented"): gate.AssuranceHigh,
	}}
	if errs := p.Validate(); len(errs) == 0 {
		t.Error("a policy naming an unknown gate type must be reported")
	}
}

func TestHighSatisfiesLowButNotTheReverse(t *testing.T) {
	if !gate.AssuranceHigh.Satisfies(gate.AssuranceLow) {
		t.Error("high must satisfy low")
	}
	if gate.AssuranceLow.Satisfies(gate.AssuranceHigh) {
		t.Error("low must not satisfy high")
	}
}

// --- asking the question ---------------------------------------------------

func TestOpenRequiresADigest(t *testing.T) {
	_, err := gate.Open(gate.Policy{}, gate.Request{
		ID: "g1", Type: gate.TypeAligned, Risk: gate.RiskP1,
		Subject:   gate.Subject{Kind: gate.SubjectArtifactSet},
		WillWrite: []string{"deliver.aligned"}, Proof: "counts", Now: now,
	})
	if err == nil {
		t.Fatal("a gate with no subject digest must be refused: an approval has to bind to content")
	}
}

func TestOpenRequiresWillWriteAndProof(t *testing.T) {
	base := gate.Request{
		ID: "g1", Type: gate.TypeAligned, Risk: gate.RiskP1,
		Subject: gate.Subject{Kind: gate.SubjectArtifactSet, Digest: "sha256:a"},
		Now:     now,
	}
	noWrite := base
	noWrite.Proof = "counts"
	if _, err := gate.Open(gate.Policy{}, noWrite); err == nil {
		t.Error("a writing gate must say which fields it writes")
	}
	noProof := base
	noProof.WillWrite = []string{"deliver.aligned"}
	if _, err := gate.Open(gate.Policy{}, noProof); err == nil {
		t.Error("asking for a signature with no proof is forbidden")
	}

	// step_confirm is the documented exception: it confirms an action.
	step := gate.Request{
		ID: "g2", Type: gate.TypeStepConfirm, Risk: gate.RiskP1,
		Subject: gate.Subject{Kind: gate.SubjectRunStep, Digest: "sha256:b"}, Now: now,
	}
	if _, err := gate.Open(gate.Policy{}, step); err != nil {
		t.Errorf("step_confirm needs no will_write: %v", err)
	}
}

func TestBaselineGatesNeedABaselineSubject(t *testing.T) {
	for _, typ := range []gate.Type{gate.TypeSealed, gate.TypeReopenBaseline} {
		wrongKind := gate.Request{
			ID: "g1", Type: typ, Risk: gate.RiskP1,
			Subject:   gate.Subject{Kind: gate.SubjectRunStep, Digest: "sha256:a", BaselineRevision: 1},
			WillWrite: []string{"x"}, Proof: "p", Now: now,
		}
		if _, err := gate.Open(gate.Policy{}, wrongKind); err == nil {
			t.Errorf("%s must sign a baseline subject", typ)
		}
		noRev := wrongKind
		noRev.Subject = gate.Subject{Kind: gate.SubjectBaseline, Digest: "sha256:a"}
		if _, err := gate.Open(gate.Policy{}, noRev); err == nil {
			t.Errorf("%s must name the baseline revision", typ)
		}
	}
}

func TestDefectOriginMustNameItsOrigin(t *testing.T) {
	r := gate.Request{
		ID: "g1", Type: gate.TypeDefectOrigin, Risk: gate.RiskP1,
		Subject:   gate.Subject{Kind: gate.SubjectRunStep, Digest: "sha256:a"},
		WillWrite: []string{"defect_origin"}, Proof: "p", Now: now,
	}
	if _, err := gate.Open(gate.Policy{}, r); err == nil {
		t.Fatal("defect_origin with no origin must be refused")
	}
	r.Origin = "code"
	g, err := gate.Open(gate.Policy{}, r)
	if err != nil {
		t.Fatal(err)
	}
	if len(g.RequiredKeywords) != 1 || g.RequiredKeywords[0] != "origin=code" {
		t.Errorf("keywords = %v, want [origin=code]", g.RequiredKeywords)
	}
}

func TestOpenNeedsAnID(t *testing.T) {
	if _, err := gate.Open(gate.Policy{}, gate.Request{Type: gate.TypeStepConfirm}); err == nil {
		t.Error("a gate with no id must be refused")
	}
}

func TestOpenSetsATTL(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	if g.ExpiresAt.Sub(g.CreatedAt) != gate.DefaultTTL {
		t.Errorf("ttl = %s, want %s", g.ExpiresAt.Sub(g.CreatedAt), gate.DefaultTTL)
	}
	short, err := gate.Open(gate.Policy{}, gate.Request{
		ID: "g3", Type: gate.TypeStepConfirm, Risk: gate.RiskP2,
		Subject: gate.Subject{Kind: gate.SubjectRunStep, Digest: "d"},
		Now:     now, TTL: time.Hour,
	})
	if err != nil {
		t.Fatal(err)
	}
	if short.ExpiresAt.Sub(short.CreatedAt) != time.Hour {
		t.Error("an explicit TTL must be honoured")
	}
}

// --- answering it ----------------------------------------------------------

func TestAPersonWithStrongAuthApproves(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	out, err := gate.Decide(g, gate.Policy{}, submit(g))
	if err != nil {
		t.Fatalf("Decide: %v", err)
	}
	if out.Gate.Status != gate.StatusApproved {
		t.Fatalf("status = %s, want approved", out.Gate.Status)
	}
	if out.Downgraded {
		t.Error("a high-assurance approval must not report a downgrade")
	}
}

func TestOnlyAPersonSigns(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	for _, kind := range []gate.PrincipalKind{gate.PrincipalAgent, gate.PrincipalService} {
		s := submit(g)
		s.Approver.Kind = kind
		s.Approver.Handle = "idev-coder"
		_, err := gate.Decide(g, gate.Policy{}, s)
		denied(t, err, gate.ReasonNotHuman)
	}
}

func TestRoleAndScopeAreChecked(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)

	noRole := submit(g)
	noRole.Approver.HasApproverRole = false
	denied(t, mustErr(gate.Decide(g, gate.Policy{}, noRole)), gate.ReasonNotApprover)

	outOfScope := submit(g)
	outOfScope.Approver.ScopeCoversFeature = false
	denied(t, mustErr(gate.Decide(g, gate.Policy{}, outOfScope)), gate.ReasonOutOfScope)
}

func TestWeakAuthenticationIsRefused(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1) // needs high
	s := submit(g)
	s.Approver.Assurance = gate.AssuranceLow
	denied(t, mustErr(gate.Decide(g, gate.Policy{}, s)), gate.ReasonWeakAssurance)
}

func TestTransitionSwitchDowngradesAndSaysSo(t *testing.T) {
	// P2-era switch: passkeys are not live yet, so a high requirement
	// completes at low — and the audit has to record that it happened.
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	p := gate.Policy{AllowLowForHigh: true}
	s := submit(g)
	s.Approver.Assurance = gate.AssuranceLow
	out, err := gate.Decide(g, p, s)
	if err != nil {
		t.Fatalf("Decide: %v", err)
	}
	if !out.Downgraded {
		t.Error("a downgraded approval must report it, or the audit is wrong")
	}
	if out.Gate.Status != gate.StatusApproved {
		t.Errorf("status = %s, want approved", out.Gate.Status)
	}

	// The switch does not make an agent a person.
	s.Approver.Kind = gate.PrincipalAgent
	denied(t, mustErr(gate.Decide(g, p, s)), gate.ReasonNotHuman)
}

func TestAQuoteIsNotParsed(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	s := submit(g)
	s.QuoteOK = false
	if _, err := gate.Decide(g, gate.Policy{}, s); err != nil {
		t.Fatalf("a quote flag refused the gate: %v", err)
	}
}

func TestReopenDoesNotNeedAKeyword(t *testing.T) {
	g, err := gate.Open(gate.Policy{}, gate.Request{
		ID: "g1", Type: gate.TypeReopenBaseline, Risk: gate.RiskP2,
		Subject:   gate.Subject{Kind: gate.SubjectBaseline, Digest: "sha256:a", BaselineRevision: 2},
		WillWrite: []string{"baseline.sealed"}, Proof: "p", Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := gate.Decide(g, gate.Policy{}, submit(g)); err != nil {
		t.Fatalf("reopen without a keyword: %v", err)
	}
}

func TestDefectOriginKeywordMustMatchTheOrigin(t *testing.T) {
	g, err := gate.Open(gate.Policy{}, gate.Request{
		ID: "g1", Type: gate.TypeDefectOrigin, Risk: gate.RiskP2, Origin: "code",
		Subject:   gate.Subject{Kind: gate.SubjectRunStep, Digest: "sha256:a"},
		WillWrite: []string{"defect_origin"}, Proof: "p", Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	wrong := submit(g)
	wrong.QuoteKeywords = []string{"origin=arch"}
	if _, err := gate.Decide(g, gate.Policy{}, wrong); err != nil {
		t.Fatalf("a mismatched origin keyword refused the gate: %v", err)
	}
}

func TestSignThenEditIsCaught(t *testing.T) {
	// I-4 and threat T5: the content moved between the question and the
	// answer, so the signature is on something that no longer exists.
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	s := submit(g)
	s.RecomputedDigest = "sha256:something-else"
	denied(t, mustErr(gate.Decide(g, gate.Policy{}, s)), gate.ReasonDigestMismatch)
}

func TestAnApprovalMustBeRecorded(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	s := submit(g)
	s.ApprovalID = ""
	denied(t, mustErr(gate.Decide(g, gate.Policy{}, s)), gate.ReasonNoApprovalID)
}

func TestExpiredGatesAreNotAnswerable(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	s := submit(g)
	s.Now = g.ExpiresAt.Add(time.Second)
	denied(t, mustErr(gate.Decide(g, gate.Policy{}, s)), gate.ReasonExpired)
}

func TestAGateIsAnsweredOnce(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	out, err := gate.Decide(g, gate.Policy{}, submit(g))
	if err != nil {
		t.Fatal(err)
	}
	denied(t, mustErr(gate.Decide(out.Gate, gate.Policy{}, submit(g))), gate.ReasonNotPending)
}

func TestRejectionNeedsIdentityButNotAQuoteParse(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)
	s := submit(g)
	s.Decision = gate.DecisionReject
	s.QuoteOK = false // a rejection is not a confirmation
	out, err := gate.Decide(g, gate.Policy{}, s)
	if err != nil {
		t.Fatalf("Decide: %v", err)
	}
	if out.Gate.Status != gate.StatusRejected {
		t.Fatalf("status = %s, want rejected", out.Gate.Status)
	}

	// But an agent still cannot reject.
	s.Approver.Kind = gate.PrincipalAgent
	denied(t, mustErr(gate.Decide(g, gate.Policy{}, s)), gate.ReasonNotHuman)
}

func TestWithdrawAndExpire(t *testing.T) {
	g := openSealed(t, gate.Policy{}, gate.RiskP1)

	if _, err := gate.Withdraw(g, ""); err == nil {
		t.Error("withdrawing needs a note")
	}
	w, err := gate.Withdraw(g, "asked the wrong thing")
	if err != nil {
		t.Fatal(err)
	}
	if w.Status != gate.StatusWithdrawn {
		t.Errorf("status = %s, want withdrawn", w.Status)
	}
	if _, err := gate.Withdraw(w, "again"); err == nil {
		t.Error("withdrawing twice must be refused")
	}

	if _, err := gate.Expire(g, now); err == nil {
		t.Error("a gate that has not expired must not be marked expired")
	}
	e, err := gate.Expire(g, g.ExpiresAt.Add(time.Second))
	if err != nil {
		t.Fatal(err)
	}
	if e.Status != gate.StatusExpired {
		t.Errorf("status = %s, want expired", e.Status)
	}
	if _, err := gate.Expire(e, g.ExpiresAt.Add(time.Hour)); err == nil {
		t.Error("expiring twice must be refused")
	}
}

// --- property --------------------------------------------------------------

// Whatever the submission looks like, a gate only becomes approved when the
// approver is a human whose authentication was strong enough and whose quote
// matched the content.
//
// The generator builds a *valid* submission and then breaks exactly one
// thing, rather than drawing every field independently. Independent draws
// have to satisfy seven conjunctions at once to reach the approval branch at
// all — roughly one draw in two hundred — so the first version of this test
// never exercised the assurance check, and a mutation that deleted it passed.
func TestPropertyOnlyHumansWithMatchingDigestsApprove(t *testing.T) {
	risks := []gate.RiskTier{gate.RiskP0, gate.RiskP1, gate.RiskP2}
	// Each flaw breaks one requirement of a valid approval.
	flaws := []string{
		"none", "agent", "service", "no-role", "out-of-scope",
		"weak-auth", "changed-content", "unrecorded",
	}

	rapid.Check(t, func(t *rapid.T) {
		typ := rapid.SampledFrom(gate.Types()).Draw(t, "type")
		risk := rapid.SampledFrom(risks).Draw(t, "risk")
		allowLow := rapid.Bool().Draw(t, "allowLow")
		p := gate.Policy{AllowLowForHigh: allowLow}

		g, err := gate.Open(p, gate.Request{
			ID: "g", Type: typ, Risk: risk, Origin: "code", Feature: "demo",
			Subject: gate.Subject{
				Kind: baselineKind(typ), Digest: "sha256:aaa", BaselineRevision: 1,
			},
			WillWrite: []string{"f"}, Proof: "p", Now: now,
		})
		if err != nil {
			return // an invalid request is not what this property is about
		}

		// A submission that should be accepted, before the flaw.
		s := gate.Submission{
			Decision: rapid.SampledFrom([]gate.Decision{
				gate.DecisionApprove, gate.DecisionReject,
			}).Draw(t, "decision"),
			Approver: gate.Approver{
				Handle: "wangwei794", Kind: gate.PrincipalHuman,
				HasApproverRole: true, ScopeCoversFeature: true,
				Assurance: gate.AssuranceHigh,
			},
			QuoteOK:          true,
			QuoteKeywords:    satisfyingKeywords(typ),
			RecomputedDigest: g.Subject.Digest,
			ApprovalID:       "ap-1",
			Now:              now,
		}

		switch rapid.SampledFrom(flaws).Draw(t, "flaw") {
		case "agent":
			s.Approver.Kind, s.Approver.Handle = gate.PrincipalAgent, "idev-coder"
		case "service":
			s.Approver.Kind = gate.PrincipalService
		case "no-role":
			s.Approver.HasApproverRole = false
		case "out-of-scope":
			s.Approver.ScopeCoversFeature = false
		case "weak-auth":
			s.Approver.Assurance = gate.AssuranceLow
		case "changed-content":
			s.RecomputedDigest = "sha256:bbb"
		case "unrecorded":
			s.ApprovalID = ""
		}

		out, err := gate.Decide(g, p, s)
		if err != nil {
			return
		}
		switch out.Gate.Status {
		case gate.StatusApproved:
			if s.Approver.Kind != gate.PrincipalHuman {
				t.Fatalf("%s approved a gate", s.Approver.Kind)
			}
			if s.Decision != gate.DecisionApprove {
				t.Fatal("a rejection produced an approval")
			}
			if s.RecomputedDigest != g.Subject.Digest {
				t.Fatal("a gate was approved against changed content")
			}
			if s.ApprovalID == "" {
				t.Fatal("an unrecorded approval was accepted")
			}
			if !s.Approver.HasApproverRole || !s.Approver.ScopeCoversFeature {
				t.Fatal("authorisation was skipped")
			}
			if !s.Approver.Assurance.Satisfies(g.RequiredAssurance) {
				if !out.Downgraded {
					t.Fatal("weak authentication was accepted without recording a downgrade")
				}
				if !p.AllowLowForHigh {
					t.Fatal("weak authentication was accepted with the transition switch off")
				}
			}
		case gate.StatusRejected:
			if s.Approver.Kind != gate.PrincipalHuman {
				t.Fatalf("%s rejected a gate", s.Approver.Kind)
			}
		default:
			t.Fatalf("Decide produced status %s", out.Gate.Status)
		}
	})
}

// satisfyingKeywords is a quote that meets whatever the gate type demands.
func satisfyingKeywords(t gate.Type) []string {
	switch t {
	case gate.TypeDefectOrigin:
		return []string{"origin=code"}
	case gate.TypeReopenBaseline:
		return []string{"解除密封"}
	}
	return nil
}

func baselineKind(t gate.Type) gate.SubjectKind {
	if t == gate.TypeSealed || t == gate.TypeReopenBaseline {
		return gate.SubjectBaseline
	}
	return gate.SubjectRunStep
}

func mustErr(_ gate.Outcome, err error) error { return err }
