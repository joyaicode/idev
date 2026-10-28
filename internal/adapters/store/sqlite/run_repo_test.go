package sqlite_test

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/idev/internal/adapters/kindreg"
	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/app/leasesvc"
	"github.com/idev/internal/app/runsvc"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

type seqIDs struct{ n int }

func (g *seqIDs) New() string {
	g.n++
	return "01RUN0000000000000000000" + string(rune('0'+g.n))
}

func TestRunRepoCreateSaveFindLiveAndStale(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	r := run.Run{
		ID: "R1", WorkflowID: "lite-change", Feature: "demo",
		Steps: []run.Step{
			{ID: "preflight", Kind: "preflight.inputs", State: run.StepPending},
			{ID: "code", Kind: "deliver.code_pass", State: run.StepPending},
		},
	}
	err = st.InTx(ctx, func(tx ports.Tx) error {
		return tx.Runs().Create(ctx, r, "demo")
	})
	if err != nil {
		t.Fatal(err)
	}

	err = st.InTx(ctx, func(tx ports.Tx) error {
		return tx.Runs().Create(ctx, run.Run{
			ID: "R2", WorkflowID: "lite-change", Feature: "demo",
			Steps: []run.Step{{ID: "a", Kind: "preflight.inputs", State: run.StepPending}},
		}, "demo")
	})
	var conflict *ports.ConflictError
	if !errors.As(err, &conflict) || conflict.Kind != ports.ConflictLiveRun {
		t.Fatalf("second create: %v, want ConflictLiveRun", err)
	}

	var loaded run.Run
	var version int64
	err = st.InTx(ctx, func(tx ports.Tx) error {
		var err error
		loaded, version, err = tx.Runs().FindLive(ctx, "demo", "lite-change")
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if loaded.ID != "R1" || version != 1 {
		t.Fatalf("live = id=%s version=%d", loaded.ID, version)
	}

	next, _, err := run.Apply(loaded, run.Event{
		Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "preflight",
	})
	if err != nil {
		t.Fatal(err)
	}
	err = st.InTx(ctx, func(tx ports.Tx) error {
		return tx.Runs().Save(ctx, next, version)
	})
	if err != nil {
		t.Fatal(err)
	}

	err = st.InTx(ctx, func(tx ports.Tx) error {
		return tx.Runs().Save(ctx, next, 1)
	})
	if !errors.As(err, &conflict) || conflict.Kind != ports.ConflictStaleVersion {
		t.Fatalf("stale save: %v, want ConflictStaleVersion", err)
	}

	err = st.InTx(ctx, func(tx ports.Tx) error {
		loaded, version, err = tx.Runs().Get(ctx, "R1")
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if version != 2 {
		t.Fatalf("version = %d, want 2", version)
	}
	if loaded.Status() != run.StatusRunning {
		t.Fatalf("status = %s, want running", loaded.Status())
	}
	if loaded.Steps[0].State != run.StepReady {
		t.Fatalf("step0 = %s, want ready", loaded.Steps[0].State)
	}
}

func TestRunsvcStartOnSQLite(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	svc := runsvc.Service{
		Store:    st,
		Clock:    fixedClock{t: time.Date(2026, 10, 28, 12, 0, 0, 0, time.UTC)},
		IDs:      &seqIDs{},
		Registry: kindreg.MustLoad(),
	}
	out, err := svc.Start(ctx, runsvc.StartParams{
		WorkflowID: "lite-change", FeatureID: "demo", Feature: "demo",
		Steps: []run.Step{
			{ID: "preflight", Kind: "preflight.inputs"},
			{ID: "plan", Kind: "verify.plan"},
		},
		Actor: ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "wangwei794"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if out.Status() != run.StatusRunning {
		t.Fatalf("status = %s, want running", out.Status())
	}
	got, err := svc.Get(ctx, out.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Steps[0].State == run.StepPending {
		t.Fatal("first step should be activated inside Start")
	}
}

func TestStaleFencingRefusedOnSQLite(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	clock := fixedClock{t: time.Date(2026, 10, 28, 12, 0, 0, 0, time.UTC)}
	ids := &seqIDs{}
	reg := kindreg.MustLoad()
	runs := runsvc.Service{Store: st, Clock: clock, IDs: ids, Registry: reg}
	leases := leasesvc.Service{Store: st, Clock: clock, IDs: ids, Kinds: reg, TTL: time.Hour}
	actor := ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "wangwei794"}
	agent := ports.Principal{Handle: "idev-coder", Kind: "agent", OwnerHandle: "wangwei794"}

	rn, err := runs.Start(ctx, runsvc.StartParams{
		WorkflowID: "lite-change", FeatureID: "demo", Feature: "demo",
		Steps: []run.Step{
			{ID: "preflight", Kind: "preflight.inputs"},
			{ID: "code", Kind: "deliver.code_pass"},
		},
		Actor: actor,
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, ev := range []run.Event{
		{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight"},
		{Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
			Outcome: run.StepPASS, Evidence: "docs/p.md"},
		{Kind: run.EvStepActivated, Actor: run.ActorSystem, StepID: "code"},
		{Kind: run.EvDelegationIssued, Actor: run.ActorConductor, StepID: "code", Agent: "idev-coder"},
	} {
		if _, err := runs.Apply(ctx, rn.ID, ev, actor); err != nil {
			t.Fatalf("%s: %v", ev.Kind, err)
		}
	}
	first, err := leases.Acquire(ctx, leasesvc.AcquireParams{
		Purpose: lease.PurposeWrite, Feature: "demo", RunID: rn.ID, StepID: "code",
		Agent: "idev-coder", WritePaths: []string{"src/**"}, Actor: agent,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := leases.Release(ctx, first.Lease.ID, first.Token, agent); err != nil {
		t.Fatal(err)
	}
	second, err := leases.Acquire(ctx, leasesvc.AcquireParams{
		Purpose: lease.PurposeWrite, Feature: "demo", RunID: rn.ID, StepID: "code",
		Agent: "idev-coder", WritePaths: []string{"src/**"}, Actor: agent,
	})
	if err != nil {
		t.Fatal(err)
	}
	if second.Lease.Fencing <= first.Lease.Fencing {
		t.Fatalf("fencing did not advance: %d -> %d", first.Lease.Fencing, second.Lease.Fencing)
	}

	var headBefore int64
	_ = st.InTx(ctx, func(tx ports.Tx) error {
		_, headBefore, _ = tx.Audit().Head(ctx)
		return nil
	})
	_, err = runs.Apply(ctx, rn.ID, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "code",
		Agent: "idev-coder", Fencing: first.Lease.Fencing,
	}, agent)
	if err == nil {
		t.Fatal("stale fencing accepted on sqlite")
	}
	var headAfter int64
	_ = st.InTx(ctx, func(tx ports.Tx) error {
		_, headAfter, _ = tx.Audit().Head(ctx)
		return nil
	})
	if headAfter != headBefore {
		t.Fatalf("audit head %d → %d; late return left residue", headBefore, headAfter)
	}
	got, err := runs.Get(ctx, rn.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Steps[1].State != run.StepDelegated {
		t.Fatalf("step = %s, want delegated", got.Steps[1].State)
	}
	if _, err := runs.Apply(ctx, rn.ID, run.Event{
		Kind: run.EvDelegationReturned, Actor: run.ActorAgent, StepID: "code",
		Agent: "idev-coder", Fencing: second.Lease.Fencing,
	}, agent); err != nil {
		t.Fatalf("live fencing refused: %v", err)
	}
}

func TestApplyConductorRecordAndAuditSameTx(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	svc := runsvc.Service{
		Store:    st,
		Clock:    fixedClock{t: time.Date(2026, 10, 28, 12, 0, 0, 0, time.UTC)},
		IDs:      &seqIDs{},
		Registry: kindreg.MustLoad(),
	}
	actor := ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "wangwei794"}
	rn, err := svc.Start(ctx, runsvc.StartParams{
		WorkflowID: "lite-change", FeatureID: "demo", Feature: "demo",
		Steps: []run.Step{
			{ID: "preflight", Kind: "preflight.inputs"},
			{ID: "plan", Kind: "verify.plan"},
		},
		Actor: actor,
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, ev := range []run.Event{
		{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: "preflight"},
		{Kind: run.EvConductorStepRecorded, Actor: run.ActorConductor, StepID: "preflight",
			Outcome: run.StepPASS, Evidence: "docs/p.md"},
	} {
		rn, err = svc.Apply(ctx, rn.ID, ev, actor)
		if err != nil {
			t.Fatalf("%s: %v", ev.Kind, err)
		}
	}
	if rn.Steps[0].State != run.StepPASS {
		t.Fatalf("preflight = %s, want PASS", rn.Steps[0].State)
	}
	stored, err := st.RunStoredStatus(ctx, rn.ID)
	if err != nil || stored == "external" || stored == "" {
		t.Fatalf("stored status = %q err=%v", stored, err)
	}
	var head int64
	err = st.InTx(ctx, func(tx ports.Tx) error {
		_, head, err = tx.Audit().Head(ctx)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if head < 1 {
		t.Fatal("Apply wrote no audit event")
	}
}
