package feature_test

import (
	"errors"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
	"pgregory.net/rapid"

	"github.com/idev/internal/domain/feature"
)

func sealed() feature.State {
	return feature.State{
		Stage:          feature.StageReq,
		Revision:       1,
		BaselineSealed: true,
		Approvals:      map[feature.Stage]bool{feature.StageReqReview: true},
	}
}

func TestHappyPathWalksOneStageAtATime(t *testing.T) {
	s := feature.State{Stage: feature.StageReqReview, Revision: 1, Approvals: map[feature.Stage]bool{}}

	steps := []struct {
		gate feature.GateType
		want feature.Stage
		pre  func(*feature.State)
	}{
		{gate: feature.GateSealed, want: feature.StageReq},
		{gate: feature.GateAcceptedReq, want: feature.StageArch},
		{gate: feature.GateAcceptedArch, want: feature.StageCode},
		{
			gate: feature.GateSelftest,
			want: feature.StageTest,
			pre:  func(st *feature.State) { st.SelftestPassed = true },
		},
		{gate: feature.GateAligned, want: feature.StageDone},
	}

	for _, step := range steps {
		if step.pre != nil {
			step.pre(&s)
		}
		next, effects, err := feature.Apply(s, feature.Event{Gate: step.gate, By: "tester"})
		if err != nil {
			t.Fatalf("gate %s from %s: %v", step.gate, s.Stage, err)
		}
		if next.Stage != step.want {
			t.Fatalf("gate %s: stage = %s, want %s", step.gate, next.Stage, step.want)
		}
		if len(effects) == 0 {
			t.Errorf("gate %s produced no effects; the audit record would be missing", step.gate)
		}
		s = next
	}
}

func TestAGateOnlyExitsItsOwnStage(t *testing.T) {
	// The whole point of "只能前进一格": an accepted(arch) signature must not
	// move a ticket that is still in req.
	s := sealed()
	if _, _, err := feature.Apply(s, feature.Event{Gate: feature.GateAcceptedArch}); err == nil {
		t.Fatal("accepted(arch) advanced a ticket sitting in req")
	}
}

func TestNothingAdvancesBeforeTheBaselineIsSealed(t *testing.T) {
	s := feature.State{Stage: feature.StageReq, Revision: 1, Approvals: map[feature.Stage]bool{}}
	if _, _, err := feature.Apply(s, feature.Event{Gate: feature.GateAcceptedReq}); err == nil {
		t.Fatal("req was accepted with no sealed baseline behind it")
	}
}

func TestSelftestGateNeedsAGreenRun(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageCode
	if _, _, err := feature.Apply(s, feature.Event{Gate: feature.GateSelftest}); err == nil {
		t.Fatal("code advanced to test without the self-test passing")
	}
	s.SelftestPassed = true
	next, _, err := feature.Apply(s, feature.Event{Gate: feature.GateSelftest})
	if err != nil {
		t.Fatalf("a green self-test must open the gate: %v", err)
	}
	if next.Stage != feature.StageTest {
		t.Fatalf("stage = %s, want test", next.Stage)
	}
}

func TestRollbackGoesBackwardsOnly(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageCode
	s.Approvals[feature.StageReq] = true
	s.Approvals[feature.StageArch] = true

	// Backwards is fine.
	next, effects, err := feature.Apply(s, feature.Event{
		Gate: feature.GateDefectOrigin, Origin: feature.StageArch,
	})
	if err != nil {
		t.Fatalf("rolling code back to arch: %v", err)
	}
	if next.Stage != feature.StageArch {
		t.Fatalf("stage = %s, want arch", next.Stage)
	}
	if next.Approvals[feature.StageArch] {
		t.Error("arch's approval must expire when arch becomes the origin")
	}
	if !next.Approvals[feature.StageReq] {
		t.Error("an approval before the origin must survive")
	}
	if !hasEffect(effects, feature.EffectRecordRevision) {
		t.Error("a rollback must be written into revisions, not silently applied")
	}

	// Forwards disguised as a rollback is not.
	if _, _, err := feature.Apply(s, feature.Event{
		Gate: feature.GateDefectOrigin, Origin: feature.StageTest,
	}); err == nil {
		t.Fatal("defect_origin jumped the ticket forward")
	}
}

func TestReqReviewIsReachableOnlyByReopen(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageCode
	if _, _, err := feature.Apply(s, feature.Event{
		Gate: feature.GateDefectOrigin, Origin: feature.StageReqReview,
	}); err == nil {
		t.Fatal("defect_origin=req-review bypassed reopen_baseline and rewrote a sealed baseline")
	}
}

func TestOpsIsNeverADefectOrigin(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageTest
	if _, _, err := feature.Apply(s, feature.Event{
		Gate: feature.GateDefectOrigin, Origin: feature.StageOps,
	}); err == nil {
		t.Fatal("ops was accepted as a defect origin")
	}
}

func TestReopenBumpsRevisionAndVoidsEverything(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageDone
	s.Approvals[feature.StageReq] = true
	s.Approvals[feature.StageArch] = true
	s.SelftestPassed = true

	next, effects, err := feature.Apply(s, feature.Event{
		Gate: feature.GateReopenBaseline, Quote: "确认 解除密封",
	})
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	if next.Stage != feature.StageReqReview {
		t.Fatalf("stage = %s, want req-review", next.Stage)
	}
	if next.Revision != s.Revision+1 {
		t.Errorf("revision = %d, want %d", next.Revision, s.Revision+1)
	}
	if next.BaselineSealed {
		t.Error("reopen must unseal the baseline")
	}
	if len(next.Approvals) != 0 {
		t.Errorf("approvals survived a reopen: %v", next.SignedStages())
	}
	for _, want := range []feature.Effect{
		feature.EffectBumpRevision, feature.EffectVoidItemIDs, feature.EffectUnsealBaseline,
	} {
		if !hasEffect(effects, want) {
			t.Errorf("reopen did not ask for %s", want)
		}
	}
}

func TestOpsTrackDoesNotLoseDeliveryProgress(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageDone
	onOps, _, err := feature.EnterOps(s)
	if err != nil {
		t.Fatalf("entering ops: %v", err)
	}
	back, _, err := feature.Apply(onOps, feature.Event{Gate: feature.GateResolved})
	if err != nil {
		t.Fatalf("resolving: %v", err)
	}
	if back.Stage != feature.StageDone {
		t.Fatalf("stage = %s, want done after resolved", back.Stage)
	}
}

func TestRefusalLeavesTheStateUntouched(t *testing.T) {
	s := sealed()
	got, effects, err := feature.Apply(s, feature.Event{Gate: feature.GateAligned})
	if err == nil {
		t.Fatal("aligned advanced a ticket in req")
	}
	if got.Stage != s.Stage || len(effects) != 0 {
		t.Error("a refused event must not half-advance the ticket")
	}
}

// --- properties ------------------------------------------------------------

// Any sequence of gates, valid or not, must never leave a ticket further
// forward than one stage per accepted event, and must never land it in
// req-review except through a reopen.
func TestPropertyNoStageIsEverSkipped(t *testing.T) {
	stages := feature.Stages()
	position := map[feature.Stage]int{}
	for i, s := range stages {
		position[s] = i
	}

	gates := []feature.GateType{
		feature.GateSealed, feature.GateAcceptedReq, feature.GateAcceptedArch,
		feature.GateSelftest, feature.GateAligned, feature.GateResolved,
		feature.GateReopenBaseline, feature.GateDefectOrigin,
	}
	origins := []feature.Stage{
		feature.StageReqReview, feature.StageReq, feature.StageArch,
		feature.StageCode, feature.StageTest, feature.StageDone, feature.StageOps,
	}

	rapid.Check(t, func(t *rapid.T) {
		state := feature.State{
			Stage: feature.StageReqReview, Revision: 1, Approvals: map[feature.Stage]bool{},
		}
		n := rapid.IntRange(1, 40).Draw(t, "events")
		for i := 0; i < n; i++ {
			ev := feature.Event{
				Gate:   rapid.SampledFrom(gates).Draw(t, "gate"),
				Origin: rapid.SampledFrom(origins).Draw(t, "origin"),
			}
			if rapid.Bool().Draw(t, "selftest") {
				state.SelftestPassed = true
			}
			before := state
			next, _, err := feature.Apply(state, ev)
			if err != nil {
				if next.Stage != before.Stage || next.Revision != before.Revision {
					t.Fatalf("refused event changed the state: %v -> %v", before, next)
				}
				continue
			}

			if next.Stage == feature.StageOps {
				t.Fatalf("a gate moved the ticket onto the ops track; only EnterOps may")
			}
			// Forward moves are exactly one stage.
			bp, np := position[before.Stage], position[next.Stage]
			if np > bp && np != bp+1 {
				t.Fatalf("stage jumped %s -> %s", before.Stage, next.Stage)
			}
			// req-review is only ever reached by reopen, which also bumps.
			if next.Stage == feature.StageReqReview && before.Stage != feature.StageReqReview {
				if ev.Gate != feature.GateReopenBaseline {
					t.Fatalf("reached req-review via %s, not reopen_baseline", ev.Gate)
				}
				if next.Revision != before.Revision+1 {
					t.Fatalf("reopen did not bump the revision")
				}
				if next.BaselineSealed {
					t.Fatalf("reopen left the baseline sealed")
				}
			}
			// Nothing advances past req on an unsealed baseline.
			if !next.BaselineSealed && position[next.Stage] > position[feature.StageReq] {
				t.Fatalf("reached %s with an unsealed baseline", next.Stage)
			}
			state = next
		}
	})
}

// A revision only ever increases, and only a reopen increases it.
func TestPropertyRevisionIsMonotonic(t *testing.T) {
	gates := []feature.GateType{
		feature.GateSealed, feature.GateAcceptedReq, feature.GateAcceptedArch,
		feature.GateSelftest, feature.GateAligned, feature.GateReopenBaseline,
		feature.GateDefectOrigin,
	}
	rapid.Check(t, func(t *rapid.T) {
		state := feature.State{
			Stage: feature.StageReqReview, Revision: 1, Approvals: map[feature.Stage]bool{},
		}
		for i := 0; i < rapid.IntRange(1, 30).Draw(t, "events"); i++ {
			gate := rapid.SampledFrom(gates).Draw(t, "gate")
			state.SelftestPassed = rapid.Bool().Draw(t, "selftest")
			next, _, err := feature.Apply(state, feature.Event{
				Gate:   gate,
				Origin: rapid.SampledFrom(feature.Stages()).Draw(t, "origin"),
			})
			if err != nil {
				continue
			}
			switch {
			case next.Revision < state.Revision:
				t.Fatalf("revision went backwards: %d -> %d", state.Revision, next.Revision)
			case next.Revision > state.Revision && gate != feature.GateReopenBaseline:
				t.Fatalf("gate %s bumped the revision", gate)
			}
			state = next
		}
	})
}

func hasEffect(effects []feature.Effect, want feature.Effect) bool {
	for _, e := range effects {
		if e == want {
			return true
		}
	}
	return false
}

func TestRefusalNamesTheRuleThatRefused(t *testing.T) {
	// The conductor repeats this to the person, so it has to read as a
	// sentence rather than a code.
	_, _, err := feature.Apply(sealed(), feature.Event{Gate: feature.GateAligned})
	if err == nil {
		t.Fatal("expected a refusal")
	}
	var te *feature.TransitionError
	if !errors.As(err, &te) {
		t.Fatalf("error type = %T, want *feature.TransitionError", err)
	}
	if te.From != feature.StageReq || te.Gate != feature.GateAligned || te.Reason == "" {
		t.Errorf("refusal is missing its context: %+v", te)
	}
	for _, want := range []string{"req", "aligned"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("Error() = %q, missing %q", err.Error(), want)
		}
	}
}

func TestSignedStagesComeBackInOrder(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageTest
	s.Approvals[feature.StageArch] = true
	s.Approvals[feature.StageReq] = true
	s.Approvals[feature.StageCode] = true

	want := []feature.Stage{
		feature.StageReqReview, feature.StageReq, feature.StageArch, feature.StageCode,
	}
	if diff := cmp.Diff(want, s.SignedStages()); diff != "" {
		t.Errorf("SignedStages() mismatch (-want +got):\n%s", diff)
	}

	// A stage explicitly recorded as not signed is not "signed".
	s.Approvals[feature.StageTest] = false
	if got := s.SignedStages(); len(got) != len(want) {
		t.Errorf("SignedStages() = %v, a false entry must not count", got)
	}
}

func TestEnterOpsRefusesWhenAlreadyThere(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageOps
	if _, _, err := feature.EnterOps(s); err == nil {
		t.Fatal("entering ops twice must be refused")
	}
}

func TestUnknownStageAndGateAreRefused(t *testing.T) {
	bogus := feature.State{Stage: feature.Stage("nowhere"), Approvals: map[feature.Stage]bool{}}
	if _, _, err := feature.Apply(bogus, feature.Event{Gate: feature.GateSealed}); err == nil {
		t.Error("an unknown stage must not transition")
	}
	if _, _, err := feature.Apply(sealed(), feature.Event{Gate: feature.GateType("invented")}); err == nil {
		t.Error("an unknown gate must not transition")
	}
	if feature.Known(feature.Stage("nowhere")) {
		t.Error("Known() accepted a stage that does not exist")
	}
}

func TestDefectOriginNeedsAStage(t *testing.T) {
	s := sealed()
	s.Stage = feature.StageTest
	if _, _, err := feature.Apply(s, feature.Event{Gate: feature.GateDefectOrigin}); err == nil {
		t.Fatal("defect_origin with no origin named must be refused")
	}
}

func TestRollbackFromOpsIsRefused(t *testing.T) {
	// ops is off the ordered machine, so there is no "backwards" from it.
	s := sealed()
	s.Stage = feature.StageOps
	if _, _, err := feature.Apply(s, feature.Event{
		Gate: feature.GateDefectOrigin, Origin: feature.StageCode,
	}); err == nil {
		t.Fatal("rolling back from the ops track must be refused")
	}
}

func TestSealedOnlyFromReqReview(t *testing.T) {
	if _, _, err := feature.Apply(sealed(), feature.Event{Gate: feature.GateSealed}); err == nil {
		t.Fatal("a second sealed gate from req must be refused")
	}
}

func TestResolvedOnlyFromOps(t *testing.T) {
	if _, _, err := feature.Apply(sealed(), feature.Event{Gate: feature.GateResolved}); err == nil {
		t.Fatal("resolved outside the ops track must be refused")
	}
}

func TestReopenFromReqReviewIsRefused(t *testing.T) {
	s := feature.State{Stage: feature.StageReqReview, Revision: 1, Approvals: map[feature.Stage]bool{}}
	if _, _, err := feature.Apply(s, feature.Event{Gate: feature.GateReopenBaseline}); err == nil {
		t.Fatal("reopening an already-open baseline must be refused")
	}
}

func TestStagesIsACopy(t *testing.T) {
	got := feature.Stages()
	got[0] = feature.Stage("tampered")
	if feature.Stages()[0] != feature.StageReqReview {
		t.Error("Stages() handed out its own slice; a caller can rewrite the machine")
	}
}
