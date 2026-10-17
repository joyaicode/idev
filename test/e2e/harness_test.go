// Package e2e walks a whole lite-change run through the app services, the
// way the conductor and its subagents will actually drive them.
//
// The unit tests pin each service's promises separately. This file pins
// the promises that only exist between services: that a run started by
// runsvc can be walked to done by alternating runsvc events, leasesvc
// acquisitions and gatesvc decisions; that a FAIL in the middle blocks the
// run and a retry un-blocks it; that every transition left exactly one
// audit event, the chain verifies, and a checkpoint over the finished run
// verifies offline (design §20.5's e2e scenario: "假 subagent 跑完
// lite-change，期间注入一次 FAIL 和一次重试，人签用测试密钥").
//
// The "subagents" are pre-scripted event sequences — the same stand-in
// design §20.5 describes: no model runs here, but every boundary a real
// subagent crosses (delegation out, report back, independent verification,
// a human gate) is crossed by this test.
package e2e_test

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/idev/internal/adapters/kindreg"
	"github.com/idev/internal/adapters/memstore"
	"github.com/idev/internal/app/auditsvc"
	"github.com/idev/internal/app/gatesvc"
	"github.com/idev/internal/app/leasesvc"
	"github.com/idev/internal/app/runsvc"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

// The lite-change recipe's steps, in order, with the kinds from
// registry/kinds.yaml. The conductor step, the delegated steps with their
// executors filled by the registry, and the two gates.
func liteChangeSteps() []run.Step {
	return []run.Step{
		{ID: "preflight", Kind: "preflight.inputs"},
		{ID: "scope-guard", Kind: "route.s4"},
		{ID: "code-pass", Kind: "deliver.code_pass"},
		{ID: "plan", Kind: "verify.plan"},
		{ID: "gate-plan", Kind: "human.gate"},
		{ID: "run", Kind: "verify.run"},
		{ID: "gate-next", Kind: "human.gate"},
	}
}

var at = time.Date(2026, 10, 17, 9, 0, 0, 0, time.UTC)

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

// steppingIDs makes ids a test can predict: the prefix names what the id
// is for, so a failure message names the actor rather than a bare ULID.
type steppingIDs struct {
	prefix string
	n      int
	mu     sync.Mutex
}

func (g *steppingIDs) New() string {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.n++
	return fmt.Sprintf("01%s%018d", g.prefix, g.n)
}

func conductor() ports.Principal {
	return ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "wangwei794"}
}

func person() ports.Principal {
	return ports.Principal{Handle: "wangwei794", Kind: "human"}
}

// edSigner is a real ed25519 pair, for the same reason the gatesvc and
// auditsvc tests use one: a signature nobody can recompute binds nothing.
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

func (s *edSigner) keyID() string {
	return "ed25519:" + hex.EncodeToString(s.pub[:8])
}

func (s *edSigner) Sign(_ context.Context, payload []byte) ([]byte, string, error) {
	return ed25519.Sign(s.priv, payload), s.keyID(), nil
}

func (s *edSigner) Verify(_ context.Context, payload, sig []byte, keyID string) error {
	if keyID != s.keyID() {
		return fmt.Errorf("unknown key %s", keyID)
	}
	if !ed25519.Verify(s.pub, payload, sig) {
		return errors.New("the signature does not verify")
	}
	return nil
}

func (s *edSigner) KeyID(_ context.Context) (string, error) { return s.keyID(), nil }

// allowAll is the Authorizer stand-in: the person has the approver role
// and scope over the one feature this run belongs to. The gatesvc tests
// cover the refusals; the e2e needs the yes path.
type allowAll struct{}

func (allowAll) Can(_ context.Context, _ ports.Principal, _, _ string) bool { return true }

// world is every service wired over one store.
type world struct {
	run   runsvc.Service
	lease leasesvc.Service
	gate  gatesvc.Service
	audit auditsvc.Service
	st    *memstore.Store
}

func newWorld(t *testing.T) *world {
	t.Helper()
	st := memstore.New()
	reg, err := kindreg.Load()
	if err != nil {
		t.Fatalf("kindreg.Load: %v", err)
	}
	signer := newSigner(t)
	w := &world{
		st: st,
		run: runsvc.Service{
			Store: st, Clock: fixedClock{t: at},
			IDs: &steppingIDs{prefix: "RUN"}, Registry: reg,
		},
		lease: leasesvc.Service{
			Store: st, Clock: fixedClock{t: at}, IDs: &steppingIDs{prefix: "LSE"},
		},
		gate: gatesvc.Service{
			Store: st, Clock: fixedClock{t: at},
			IDs: &steppingIDs{prefix: "GTE"}, Signer: signer,
			Authorizer: allowAll{},
		},
		audit: auditsvc.Service{
			Store: st, Clock: fixedClock{t: at}, Signer: signer,
		},
	}
	return w
}

// apply is the conductor's one move, with the failure made loud.
func apply(t *testing.T, w *world, runID string, ev run.Event, actor ports.Principal) run.Run {
	t.Helper()
	r, err := w.run.Apply(context.Background(), runID, ev, actor)
	if err != nil {
		t.Fatalf("Apply %s on %s: %v", ev.Kind, ev.StepID, err)
	}
	return r
}

// refuse asserts a move the machine must reject — the negative half of the
// walk, which is as much lite-change's behaviour as the positive half.
func refuse(t *testing.T, w *world, runID string, ev run.Event, actor ports.Principal, why string) {
	t.Helper()
	if _, err := w.run.Apply(context.Background(), runID, ev, actor); err == nil {
		t.Fatalf("%s: the machine accepted %s by %s", why, ev.Kind, ev.Actor)
	}
}

// startLiteChange starts the run under test.
func startLiteChange(t *testing.T, w *world) run.Run {
	t.Helper()
	r, err := w.run.Start(context.Background(), runsvc.StartParams{
		WorkflowID: "lite-change",
		FeatureID:  "f-1",
		Feature:    "demo",
		Steps:      liteChangeSteps(),
		Params:     map[string]string{"mode": "selftest"},
		Actor:      conductor(),
	})
	if err != nil {
		t.Fatalf("Start: %v", err)
	}
	return r
}

// activate fires the system event that makes the next pending step
// current. E2 is not automatic: the driver (the conductor, in P3 the
// client) activates each step once its priors are done, exactly like
// workflow.py's `next` does on the YAML side. The first step is activated
// by Start already, so activating it again is skipped here.
func activate(t *testing.T, w *world, runID, stepID string) {
	t.Helper()
	r, ok := w.st.Run(runID)
	if !ok {
		t.Fatalf("no run %s", runID)
	}
	var step *run.Step
	for i := range r.Steps {
		if r.Steps[i].ID == stepID {
			step = &r.Steps[i]
		}
	}
	if step == nil {
		t.Fatalf("no step %s", stepID)
	}
	if step.State != run.StepPending {
		// Already activated — the first step by Start, or a re-walk.
		return
	}
	apply(t, w, runID, run.Event{
		Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: stepID,
	}, conductor())
}

// conductorStep walks a conductor-owned step: start, then record PASS.
func conductorStep(t *testing.T, w *world, runID, stepID, evidence string) {
	t.Helper()
	activate(t, w, runID, stepID)
	apply(t, w, runID, run.Event{
		Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: stepID,
	}, conductor())
	apply(t, w, runID, run.Event{
		Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: stepID,
		Outcome: run.StepPASS, Evidence: evidence,
	}, conductor())
}

// delegate walks the full delegation cycle for an agent step: the
// conductor issues it, the lease is acquired for the writer, the agent
// returns, and the conductor accepts the outcome. A PASS on a kind that
// needs independent verification routes through the verifier instead.
func delegate(t *testing.T, w *world, runID, stepID, agent, verifier string, outcome run.StepState) {
	t.Helper()
	ctx := context.Background()
	activate(t, w, runID, stepID)
	apply(t, w, runID, run.Event{
		Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: stepID, Agent: agent,
	}, conductor())

	held, err := w.lease.Acquire(ctx, leasesvc.AcquireParams{
		Purpose: lease.PurposeWrite, Feature: "f-1", RunID: runID, StepID: stepID,
		Agent: agent, WritePaths: []string{"**"}, Actor: conductor(),
	})
	if err != nil {
		t.Fatalf("Acquire for %s: %v", stepID, err)
	}

	apply(t, w, runID, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: stepID, Agent: agent,
	}, ports.Principal{Handle: agent, Kind: "agent"})

	if outcome == run.StepPASS {
		// The conductor accepts PASS; the machine checks route kinds that
		// need verification into verifying, and the verifier (a different
		// agent) confirms.
		after := apply(t, w, runID, run.Event{
			Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: stepID,
			Outcome: run.StepPASS, Evidence: stepID + "/review.md",
		}, conductor())
		step := after.Current()
		if step != nil && step.ID == stepID && step.State == run.StepVerifying {
			_, err := w.lease.Acquire(ctx, leasesvc.AcquireParams{
				Purpose: lease.PurposeVerify, Feature: "f-1", RunID: runID, StepID: stepID,
				Agent: verifier, TicketDir: "tickets/demo",
				WritePaths: []string{"tickets/demo/**"}, Actor: conductor(),
			})
			if err != nil {
				t.Fatalf("verify Acquire for %s: %v", stepID, err)
			}
			apply(t, w, runID, run.Event{
				Kind: run.EvVerificationRecorded, Actor: run.ActorAgent, StepID: stepID,
				Agent: verifier, Outcome: run.StepPASS, Evidence: stepID + "/verify.md",
			}, ports.Principal{Handle: verifier, Kind: "agent"})
		}
	} else {
		apply(t, w, runID, run.Event{
			Kind: run.EvDelegationAccepted, Actor: run.ActorConductor, StepID: stepID,
			Outcome: outcome,
		}, conductor())
	}
	_ = held
}

// approveGate puts a person's real answer through gatesvc and feeds the
// recorded approval back into the run — the loop P3's clients will run:
// ask, decide, then EvGateApproved with the approval id.
func approveGate(t *testing.T, w *world, runID, stepID string, quote string) {
	t.Helper()
	ctx := context.Background()
	r, ok := w.st.Run(runID)
	if !ok {
		t.Fatalf("no run %s", runID)
	}
	if cur := r.Current(); cur == nil || cur.ID != stepID {
		t.Fatalf("step %s is not current (current is %v)", stepID, r.Current())
	}

	g, err := w.gate.Ask(ctx, gatesvc.AskParams{
		Type: gate.TypeAcceptedPlan, RunID: runID, StepID: stepID, Feature: "f-1",
		Risk: gate.RiskP1,
		Subject: gate.Subject{
			Kind: gate.SubjectRunStep, Digest: "sha256:" + stepID, BaselineRevision: 1,
		},
		WillWrite: []string{"verify/plan.yaml accepted"},
		Proof:     "verify-plan gate: 0 FAIL; 3 cases",
		Actor:     conductor(),
	})
	if err != nil {
		t.Fatalf("Ask(%s): %v", stepID, err)
	}
	activate(t, w, runID, stepID)
	apply(t, w, runID, run.Event{
		Kind: run.EvGateRequested, Actor: run.ActorConductor, StepID: stepID,
	}, conductor())
	d, err := w.gate.Decide(ctx, gatesvc.DecisionParams{
		GateID: g.ID, Quote: quote, Channel: gatesvc.ChannelOIDC,
		RecomputedDigest: "sha256:" + stepID, Actor: person(),
	})
	if err != nil {
		t.Fatalf("Decide(%s): %v", stepID, err)
	}
	apply(t, w, runID, run.Event{
		Kind: run.EvGateApproved, Actor: run.ActorHuman, StepID: stepID,
		ApprovalID: d.Approval.ID,
	}, person())
}

// walkHappyPath is the no-faults path, asserted once on its own. The kind
// table decides who walks each step: preflight.inputs stays with the
// conductor, route.s4 belongs to idev-ops, deliver.code_pass to idev-coder
// with independent verification by idev-reviewer, the verify steps to
// idev-verifier, and the two gates to a person.
func walkHappyPath(t *testing.T, w *world, r run.Run) {
	t.Helper()
	conductorStep(t, w, r.ID, "preflight", "preflight/probe.md")
	delegate(t, w, r.ID, "scope-guard", "idev-ops", "idev-ops", run.StepPASS)
	delegate(t, w, r.ID, "code-pass", "idev-coder", "idev-reviewer", run.StepPASS)
	delegate(t, w, r.ID, "plan", "idev-verifier", "idev-verifier", run.StepPASS)
	approveGate(t, w, r.ID, "gate-plan", "确认")
	delegate(t, w, r.ID, "run", "idev-verifier", "idev-verifier", run.StepPASS)
	approveGate(t, w, r.ID, "gate-next", "确认")
}

// leasesvcAcquireParams is the writer lease the concurrency test races for.
func leasesvcAcquireParams(runID, stepID string) leasesvc.AcquireParams {
	return leasesvc.AcquireParams{
		Purpose: lease.PurposeWrite, Feature: "f-1", RunID: runID, StepID: stepID,
		Agent: "idev-coder", WritePaths: []string{"**"}, Actor: conductor(),
	}
}
