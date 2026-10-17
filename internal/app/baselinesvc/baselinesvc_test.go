package baselinesvc_test

import (
	"context"
	"errors"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/memstore"
	"github.com/idev/internal/app/baselinesvc"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/baseline"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/ports"
)

// The tests pin the baseline service's promises: a seal (or reopen) is
// bound to the exact manifest a person approved — same feature, same
// manifest_root, same revision (I-4) — the baseline row and its audit
// event land in one transaction or not at all (I-6), a feature seals at
// most once, and drift is the only verdict that becomes a fact in the
// chain, because it is the one that blocks runs.

var at = time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

func newSvc() (baselinesvc.Service, *memstore.Store) {
	st := memstore.New()
	return baselinesvc.Service{Store: st, Clock: fixedClock{t: at}}, st
}

func conductor() ports.Principal {
	return ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "wangwei794"}
}

// manifest builds a one-file manifest with the given goal as the sealed
// content, so two goals mean two different manifest roots.
func manifest(t *testing.T, feature string, revision int, goal string) baseline.Manifest {
	t.Helper()
	f, err := baseline.YAMLFile(
		"baseline/repo-state.yaml",
		[]byte("goal: "+goal+"\n"),
		map[string]any{"goal": goal},
		nil,
	)
	if err != nil {
		t.Fatalf("YAMLFile: %v", err)
	}
	m, err := baseline.Build(feature, revision, []baseline.File{f}, "abc123", false, at)
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	return m
}

// sealGate is an approved sealed question about a manifest.
func sealGate(m baseline.Manifest) gate.Gate {
	return boundGate("g-seal", "seal-baseline", gate.TypeSealed, gate.StatusApproved, m)
}

// reopenGate is an approved reopen question about a manifest.
func reopenGate(m baseline.Manifest) gate.Gate {
	return boundGate("g-reopen", "reopen-baseline", gate.TypeReopenBaseline, gate.StatusApproved, m)
}

// boundGate builds a gate literal with the given shape, bound to the
// manifest: the subject digest is the manifest root and the revision is
// the manifest's. Tests bend one field at a time from here.
func boundGate(id, step string, typ gate.Type, status gate.Status, m baseline.Manifest) gate.Gate {
	return gate.Gate{
		ID:        id,
		Type:      typ,
		RunID:     "r-1",
		StepID:    step,
		Feature:   m.Feature,
		Risk:      gate.RiskP1,
		Subject:   gate.Subject{Kind: gate.SubjectBaseline, Digest: string(m.ManifestRoot), BaselineRevision: m.Revision},
		WillWrite: []string{"baseline/repo-state.yaml"},
		Proof:     "run 01AR finished green",
		Status:    status,
		CreatedAt: at,
		ExpiresAt: at.Add(72 * time.Hour),
	}
}

// storeGate puts a gate literal in the store the way a conductor's Ask
// would have, minus the ceremony: the service under test only reads it.
func storeGate(t *testing.T, st *memstore.Store, g gate.Gate) {
	t.Helper()
	if err := st.InTx(context.Background(), func(tx ports.Tx) error {
		return tx.Gates().Open(context.Background(), g, g.Feature)
	}); err != nil {
		t.Fatalf("storing gate %s: %v", g.ID, err)
	}
}

func wantConflict(t *testing.T, err error, kind, what string) {
	t.Helper()
	var ce *ports.ConflictError
	if !errors.As(err, &ce) || ce.Kind != kind {
		t.Fatalf("%s: err = %v, want a %s conflict", what, err, kind)
	}
}

// wantRefusal asserts the error names what was wrong, and that the refusal
// left nothing behind: no sealed baseline, no audit event. A refusal is an
// answer to the caller, not a fact about the world.
func wantRefusal(t *testing.T, err error, st *memstore.Store, feature, what, wantIn string) {
	t.Helper()
	if err == nil {
		t.Fatalf("%s: got no error, want a refusal", what)
	}
	if wantIn != "" && !strings.Contains(err.Error(), wantIn) {
		t.Errorf("%s: err = %q, want it to say %q", what, err.Error(), wantIn)
	}
	if _, serr := svcSealed(st, feature); !isNotFound(serr) {
		t.Errorf("%s: the refusal still left a sealed baseline behind", what)
	}
	if events := st.Events(); len(events) != 0 {
		t.Errorf("%s: the refusal still wrote %d audit events", what, len(events))
	}
}

// svcSealed reads the sealed baseline straight from the store, so a
// refusal test can prove nothing was written without going through the
// service under test.
func svcSealed(st *memstore.Store, feature string) (baseline.Manifest, error) {
	var m baseline.Manifest
	err := st.InTx(context.Background(), func(tx ports.Tx) error {
		var err error
		m, err = tx.Baselines().Sealed(context.Background(), feature)
		return err
	})
	return m, err
}

func isNotFound(err error) bool {
	var ce *ports.ConflictError
	return errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound
}

func TestSealBindsTheManifestThePersonApproved(t *testing.T) {
	s, st := newSvc()
	m := manifest(t, "f-1", 3, "ship the report")
	storeGate(t, st, sealGate(m))

	got, err := s.Seal(context.Background(), baselinesvc.SealParams{
		Feature: "f-1", Manifest: m, GateID: "g-seal", Actor: conductor(),
	})
	if err != nil {
		t.Fatalf("Seal: %v", err)
	}
	if got.ManifestRoot != m.ManifestRoot {
		t.Errorf("Seal returned the manifest it was given, not %s", m.ManifestRoot)
	}
	if sealed, err := s.Sealed(context.Background(), "f-1"); err != nil || sealed.ManifestRoot != m.ManifestRoot {
		t.Errorf("Sealed() = (%v, %v), want the sealed manifest back", sealed.ManifestRoot, err)
	}

	events := st.Events()
	if len(events) != 1 {
		t.Fatalf("a seal writes exactly one audit event, got %d", len(events))
	}
	e := events[0]
	want := audit.Event{
		Action:  audit.ActionBaselineSealed,
		Actor:   audit.Actor{Handle: "conductor@claude", Kind: "agent", OnBehalfOf: "wangwei794"},
		RunID:   "r-1",
		StepID:  "seal-baseline",
		Feature: "f-1",
		Subject: string(m.ManifestRoot),
		At:      at,
		Detail: map[string]any{
			"revision":      3,
			"manifest_root": string(m.ManifestRoot),
			"raw_root":      string(m.RawRoot),
			"files":         1,
			"repo_head":     "abc123",
			"dirty":         false,
			"gate_id":       "g-seal",
		},
	}
	if e.Action != want.Action || e.Actor != want.Actor || e.RunID != want.RunID ||
		e.StepID != want.StepID || e.Feature != want.Feature || e.Subject != want.Subject ||
		!e.At.Equal(want.At) {
		t.Errorf("the sealed event = %+v, want the shape of %+v", e, want)
	}
	if !reflect.DeepEqual(e.Detail, want.Detail) {
		t.Errorf("the sealed event detail = %#v, want %#v", e.Detail, want.Detail)
	}
}

func TestSealRefusesAGateThatDidNotApproveThisManifest(t *testing.T) {
	m := manifest(t, "f-1", 3, "ship the report")
	// other-root is the same revision with different content: the digest
	// differs but nothing else does.
	otherRoot := manifest(t, "f-1", 3, "ship the report, but different")
	// other-rev is the same content at revision 2: the root matches but the
	// revision does not — approval is per (root, revision), not per root.
	otherRev := manifest(t, "f-1", 2, "ship the report")

	cases := []struct {
		what   string
		mut    func(g gate.Gate) gate.Gate
		wantIn string
	}{
		{
			what:   "a pending gate",
			mut:    func(g gate.Gate) gate.Gate { g.Status = gate.StatusPending; return g },
			wantIn: "pending",
		},
		{
			what:   "a rejected gate",
			mut:    func(g gate.Gate) gate.Gate { g.Status = gate.StatusRejected; return g },
			wantIn: "rejected",
		},
		{
			what:   "a withdrawn gate",
			mut:    func(g gate.Gate) gate.Gate { g.Status = gate.StatusWithdrawn; return g },
			wantIn: "withdrawn",
		},
		{
			what:   "an approved gate of the wrong type",
			mut:    func(g gate.Gate) gate.Gate { g.Type = gate.TypeStepConfirm; return g },
			wantIn: "step_confirm question",
		},
		{
			what: "a gate bound to another manifest's root",
			mut: func(g gate.Gate) gate.Gate {
				g.Subject.Digest = string(otherRoot.ManifestRoot)
				return g
			},
			wantIn: "approving one thing and sealing another",
		},
		{
			what: "a gate bound to another revision",
			mut: func(g gate.Gate) gate.Gate {
				g.Subject.BaselineRevision = otherRev.Revision
				return g
			},
			wantIn: "approved revision 2",
		},
		{
			what: "a gate about another feature",
			mut: func(g gate.Gate) gate.Gate {
				g.Feature = "f-2"
				return g
			},
			wantIn: "about feature",
		},
		{
			what: "a gate whose subject is not a baseline",
			mut: func(g gate.Gate) gate.Gate {
				g.Subject.Kind = gate.SubjectArtifactSet
				return g
			},
			wantIn: "signs a artifact_set",
		},
	}

	for i, tc := range cases {
		t.Run(tc.what, func(t *testing.T) {
			s, st := newSvc()
			g := tc.mut(sealGate(m))
			g.ID = "g-" + strconv.Itoa(i)
			g.StepID = "step-" + strconv.Itoa(i)
			storeGate(t, st, g)

			_, err := s.Seal(context.Background(), baselinesvc.SealParams{
				Feature: "f-1", Manifest: m, GateID: g.ID, Actor: conductor(),
			})
			wantRefusal(t, err, st, "f-1", tc.what, tc.wantIn)
		})
	}
}

func TestAFeatureSealsAtMostOnce(t *testing.T) {
	s, st := newSvc()
	m1 := manifest(t, "f-1", 3, "ship the report")
	storeGate(t, st, sealGate(m1))
	if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
		Feature: "f-1", Manifest: m1, GateID: "g-seal", Actor: conductor(),
	}); err != nil {
		t.Fatalf("first Seal: %v", err)
	}

	// A second, fully legitimate approval of a newer revision still loses:
	// the baseline is a fact now, and changing it is a reopen, not a seal.
	m2 := manifest(t, "f-1", 4, "ship the report and the follow-up")
	g2 := sealGate(m2)
	g2.ID, g2.StepID = "g-seal-2", "seal-baseline-2"
	storeGate(t, st, g2)
	_, err := s.Seal(context.Background(), baselinesvc.SealParams{
		Feature: "f-1", Manifest: m2, GateID: "g-seal-2", Actor: conductor(),
	})
	wantConflict(t, err, ports.ConflictSealedBaseline, "sealing an already-sealed feature")

	if events := st.Events(); len(events) != 1 {
		t.Errorf("the refused second seal wrote %d events on top of the first, want 1", len(events))
	}
	if sealed, err := s.Sealed(context.Background(), "f-1"); err != nil || sealed.Revision != 3 {
		t.Errorf("Sealed() = (rev %d, %v), want the original rev 3", sealed.Revision, err)
	}
}

func TestCheckComparesAgainstTheSealedManifest(t *testing.T) {
	s, st := newSvc()
	sealed := manifest(t, "f-1", 3, "ship the report")
	storeGate(t, st, sealGate(sealed))
	if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
		Feature: "f-1", Manifest: sealed, GateID: "g-seal", Actor: conductor(),
	}); err != nil {
		t.Fatalf("Seal: %v", err)
	}

	// Intact: same bytes, no event — nothing happened worth remembering.
	out, err := s.Check(context.Background(), "f-1", sealed, conductor())
	if err != nil || out.Verdict != baseline.VerdictIntact {
		t.Fatalf("Check(intact) = (%+v, %v), want intact", out, err)
	}
	if n := len(st.Events()); n != 1 {
		t.Errorf("an intact check wrote an event; still %d events", n)
	}

	// Format-only: same meaning, different bytes. A warning to the caller,
	// not a fact in the chain.
	f2, err := baseline.YAMLFile(
		"baseline/repo-state.yaml",
		[]byte("goal:   ship the report\n\n"),
		map[string]any{"goal": "ship the report"},
		nil,
	)
	if err != nil {
		t.Fatalf("YAMLFile: %v", err)
	}
	reformatted, err := baseline.Build("f-1", 3, []baseline.File{f2}, "abc123", false, at)
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	out, err = s.Check(context.Background(), "f-1", reformatted, conductor())
	if err != nil {
		t.Fatalf("Check(format-only): %v", err)
	}
	if out.Verdict != baseline.VerdictFormatOnly {
		t.Errorf("reformatted = %s, want format_only", out.Verdict)
	}
	if len(out.Changes) != 1 || out.Changes[0].Kind != "reformatted" || out.Changes[0].Path != "baseline/repo-state.yaml" {
		t.Errorf("the format-only change = %+v, want one reformatted repo-state.yaml", out.Changes)
	}
	if n := len(st.Events()); n != 1 {
		t.Errorf("a format-only change wrote an event; still %d events", n)
	}

	// Drift: a sealed field changed. This one blocks runs, so it becomes a
	// fact in the chain.
	drifted := manifest(t, "f-1", 4, "ship the report and the follow-up")
	out, err = s.Check(context.Background(), "f-1", drifted, conductor())
	if err != nil {
		t.Fatalf("Check(drift): %v", err)
	}
	if out.Verdict != baseline.VerdictDrift {
		t.Fatalf("drifted = %s, want drift", out.Verdict)
	}
	if out.Line != "BLOCKED baseline-drift baseline/repo-state.yaml (sealed rev 3)" {
		t.Errorf("the drift line = %q", out.Line)
	}
	events := st.Events()
	if len(events) != 2 {
		t.Fatalf("drift writes one event, got %d", len(events))
	}
	e := events[1]
	if e.Action != audit.ActionBaselineDrift || e.Feature != "f-1" || e.Subject != string(sealed.ManifestRoot) {
		t.Errorf("the drift event = %+v", e)
	}
	wantDetail := map[string]any{
		"sealed_revision": 3,
		"line":            "BLOCKED baseline-drift baseline/repo-state.yaml (sealed rev 3)",
		"changes":         []string{"changed baseline/repo-state.yaml"},
	}
	if !reflect.DeepEqual(e.Detail, wantDetail) {
		t.Errorf("the drift detail = %#v, want %#v", e.Detail, wantDetail)
	}
}

func TestCheckNeedsASealedBaseline(t *testing.T) {
	s, st := newSvc()
	m := manifest(t, "f-1", 3, "ship the report")

	_, err := s.Check(context.Background(), "f-1", m, conductor())
	if err == nil || !isNotFound(err) {
		t.Fatalf("checking an unsealed feature: err = %v, want not-found", err)
	}
	if events := st.Events(); len(events) != 0 {
		t.Errorf("the refused check wrote %d events", len(events))
	}
}

func TestReopenNeedsThePersonsApprovalOfThisManifest(t *testing.T) {
	m := manifest(t, "f-1", 3, "ship the report")
	other := manifest(t, "f-1", 3, "ship the report, but different")

	cases := []struct {
		what   string
		gate   func() gate.Gate
		wantIn string
	}{
		{
			what:   "a pending reopen gate",
			gate:   func() gate.Gate { g := reopenGate(m); g.Status = gate.StatusPending; return g },
			wantIn: "pending",
		},
		{
			what:   "a seal gate passed off as a reopen",
			gate:   func() gate.Gate { return sealGate(m) },
			wantIn: "sealed question, not reopen_baseline",
		},
		{
			what:   "a reopen gate bound to another manifest",
			gate:   func() gate.Gate { return reopenGate(other) },
			wantIn: "approving one thing and sealing another",
		},
	}
	for i, tc := range cases {
		t.Run(tc.what, func(t *testing.T) {
			s, st := newSvc()
			storeGate(t, st, sealGate(m))
			if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
				Feature: "f-1", Manifest: m, GateID: "g-seal", Actor: conductor(),
			}); err != nil {
				t.Fatalf("Seal: %v", err)
			}
			g := tc.gate()
			g.ID, g.StepID = "g-r-"+strconv.Itoa(i), "reopen-"+strconv.Itoa(i)
			storeGate(t, st, g)

			_, err := s.Reopen(context.Background(), baselinesvc.ReopenParams{
				Feature: "f-1", GateID: g.ID, Actor: conductor(),
			})
			if err == nil || !strings.Contains(err.Error(), tc.wantIn) {
				t.Fatalf("%s: err = %v, want a refusal saying %q", tc.what, err, tc.wantIn)
			}
			// The refusal must leave the seal standing.
			if sealed, serr := svcSealed(st, "f-1"); serr != nil || sealed.ManifestRoot != m.ManifestRoot {
				t.Errorf("%s: the refusal unsealed the feature (sealed=%v err=%v)", tc.what, sealed.ManifestRoot, serr)
			}
			if n := len(st.Events()); n != 1 {
				t.Errorf("%s: the refusal wrote events; still %d", tc.what, n)
			}
		})
	}

	// With the right approval, the reopen goes through.
	t.Run("with the right approval", func(t *testing.T) {
		s, st := newSvc()
		storeGate(t, st, sealGate(m))
		if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
			Feature: "f-1", Manifest: m, GateID: "g-seal", Actor: conductor(),
		}); err != nil {
			t.Fatalf("Seal: %v", err)
		}
		storeGate(t, st, reopenGate(m))

		was, err := s.Reopen(context.Background(), baselinesvc.ReopenParams{
			Feature: "f-1", GateID: "g-reopen", Actor: conductor(),
		})
		if err != nil {
			t.Fatalf("Reopen: %v", err)
		}
		if was.ManifestRoot != m.ManifestRoot {
			t.Errorf("Reopen returned %s, want what was sealed", was.ManifestRoot)
		}
		if _, err := svcSealed(st, "f-1"); !isNotFound(err) {
			t.Errorf("after a reopen the feature has no sealed baseline, got err %v", err)
		}
		events := st.Events()
		if len(events) != 2 {
			t.Fatalf("seal + reopen = 2 events, got %d", len(events))
		}
		e := events[1]
		if e.Action != audit.ActionBaselineReopened || e.Subject != string(m.ManifestRoot) ||
			e.RunID != "r-1" || e.StepID != "reopen-baseline" {
			t.Errorf("the reopened event = %+v", e)
		}
		wantDetail := map[string]any{
			"revision":      3,
			"manifest_root": string(m.ManifestRoot),
			"gate_id":       "g-reopen",
		}
		if !reflect.DeepEqual(e.Detail, wantDetail) {
			t.Errorf("the reopened detail = %#v, want %#v", e.Detail, wantDetail)
		}
	})

	// Reopening with nothing sealed is not a reopen.
	t.Run("nothing sealed", func(t *testing.T) {
		s, st := newSvc()
		storeGate(t, st, reopenGate(m))
		_, err := s.Reopen(context.Background(), baselinesvc.ReopenParams{
			Feature: "f-1", GateID: "g-reopen", Actor: conductor(),
		})
		if err == nil || !isNotFound(err) {
			t.Fatalf("reopening an unsealed feature: err = %v, want not-found", err)
		}
		if events := st.Events(); len(events) != 0 {
			t.Errorf("the refused reopen wrote %d events", len(events))
		}
	})
}

// TestAFailedSealLeavesNothingBehind pins I-6: the baseline row and its
// event are one transaction. Fail the write at either half — before the
// row exists, or after it exists but before the event — and the store must
// hold neither. The same goes for the drift event of a check and the
// reopen.
func TestAFailedSealLeavesNothingBehind(t *testing.T) {
	seed := func(t *testing.T) (baselinesvc.Service, *memstore.Store, baseline.Manifest) {
		t.Helper()
		s, st := newSvc()
		m := manifest(t, "f-1", 3, "ship the report")
		storeGate(t, st, sealGate(m))
		return s, st, m
	}

	t.Run("the draft never lands", func(t *testing.T) {
		s, st, m := seed(t)
		st.FailOn["baselines.Put"] = errors.New("disk full")
		if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
			Feature: "f-1", Manifest: m, GateID: "g-seal", Actor: conductor(),
		}); err == nil {
			t.Fatal("Seal with a failing store: got no error")
		}
		if _, err := svcSealed(st, "f-1"); !isNotFound(err) {
			t.Errorf("the failed seal left a baseline behind (err = %v)", err)
		}
		if events := st.Events(); len(events) != 0 {
			t.Errorf("the failed seal left %d events behind", len(events))
		}
	})

	t.Run("the event fails, the row rolls back", func(t *testing.T) {
		s, st, m := seed(t)
		st.FailOn["audit.Append"] = errors.New("disk full")
		if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
			Feature: "f-1", Manifest: m, GateID: "g-seal", Actor: conductor(),
		}); err == nil {
			t.Fatal("Seal with a failing audit: got no error")
		}
		if _, err := svcSealed(st, "f-1"); !isNotFound(err) {
			t.Errorf("a seal without its event survived (err = %v)", err)
		}
		if events := st.Events(); len(events) != 0 {
			t.Errorf("the failed seal left %d events behind", len(events))
		}

		// And the retry, once the fault is gone, succeeds — the failure
		// poisoned nothing.
		delete(st.FailOn, "audit.Append")
		if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
			Feature: "f-1", Manifest: m, GateID: "g-seal", Actor: conductor(),
		}); err != nil {
			t.Fatalf("the retry: %v", err)
		}
		if sealed, err := svcSealed(st, "f-1"); err != nil || sealed.ManifestRoot != m.ManifestRoot {
			t.Errorf("after the retry the feature is still not sealed (%v)", err)
		}
	})

	t.Run("the drift event fails, nothing else moves", func(t *testing.T) {
		s, st, m := seed(t)
		if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
			Feature: "f-1", Manifest: m, GateID: "g-seal", Actor: conductor(),
		}); err != nil {
			t.Fatalf("Seal: %v", err)
		}
		drifted := manifest(t, "f-1", 4, "ship the report and the follow-up")
		st.FailOn["audit.Append"] = errors.New("disk full")
		if _, err := s.Check(context.Background(), "f-1", drifted, conductor()); err == nil {
			t.Fatal("Check with a failing audit: got no error")
		}
		if events := st.Events(); len(events) != 1 {
			t.Errorf("the failed check left %d events, want only the seal", len(events))
		}
		if sealed, err := svcSealed(st, "f-1"); err != nil || sealed.ManifestRoot != m.ManifestRoot {
			t.Errorf("the failed check disturbed the seal (%v)", err)
		}
	})

	t.Run("the reopen event fails, the seal stands", func(t *testing.T) {
		s, st, m := seed(t)
		if _, err := s.Seal(context.Background(), baselinesvc.SealParams{
			Feature: "f-1", Manifest: m, GateID: "g-seal", Actor: conductor(),
		}); err != nil {
			t.Fatalf("Seal: %v", err)
		}
		storeGate(t, st, reopenGate(m))
		st.FailOn["audit.Append"] = errors.New("disk full")
		if _, err := s.Reopen(context.Background(), baselinesvc.ReopenParams{
			Feature: "f-1", GateID: "g-reopen", Actor: conductor(),
		}); err == nil {
			t.Fatal("Reopen with a failing audit: got no error")
		}
		if sealed, err := svcSealed(st, "f-1"); err != nil || sealed.ManifestRoot != m.ManifestRoot {
			t.Errorf("a reopen without its event went through (err = %v)", err)
		}
		if events := st.Events(); len(events) != 1 {
			t.Errorf("the failed reopen left %d events, want only the seal", len(events))
		}
	})
}

func TestSealValidatesItsParameters(t *testing.T) {
	s, st := newSvc()
	m := manifest(t, "f-1", 3, "ship the report")

	cases := []struct {
		what   string
		p      baselinesvc.SealParams
		wantIn string
	}{
		{"no feature", baselinesvc.SealParams{Manifest: m, GateID: "g", Actor: conductor()}, "names its feature"},
		{"an empty manifest", baselinesvc.SealParams{Feature: "f-1", GateID: "g", Actor: conductor()}, "empty manifest"},
		{
			"a manifest from another feature",
			baselinesvc.SealParams{Feature: "f-2", Manifest: m, GateID: "g", Actor: conductor()},
			"not \"f-2\"",
		},
		{"no gate", baselinesvc.SealParams{Feature: "f-1", Manifest: m, Actor: conductor()}, "needs the gate"},
		{"no actor", baselinesvc.SealParams{Feature: "f-1", Manifest: m, GateID: "g"}, "not an audit record"},
	}
	for _, tc := range cases {
		if _, err := s.Seal(context.Background(), tc.p); err == nil || !strings.Contains(err.Error(), tc.wantIn) {
			t.Errorf("%s: err = %v, want a refusal saying %q", tc.what, err, tc.wantIn)
		}
	}
	if events := st.Events(); len(events) != 0 {
		t.Errorf("the refused seals wrote %d events", len(events))
	}
}
