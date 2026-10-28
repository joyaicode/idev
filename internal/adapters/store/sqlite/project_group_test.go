package sqlite_test

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

func TestProjectRunKeepsTheWave(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	err = st.ProjectRun(ctx, sqlite.ProjectedRun{
		ID: "Rwave", WorkflowID: "lite-change", Feature: "demo", Risk: "P1",
		Steps: []sqlite.ProjectedStep{
			{ID: "plan", Kind: "verify.plan", State: run.StepPending, Group: "check", Writes: []string{"verify/plan.yaml"}},
			{ID: "run", Kind: "verify.run", State: run.StepPending, Group: "check", Writes: []string{"verify/selftest.md"}},
			{ID: "gate", Kind: "human.gate", State: run.StepPending},
		},
	})
	if err != nil {
		t.Fatal(err)
	}

	var loaded run.Run
	err = st.InTx(ctx, func(tx ports.Tx) error {
		var err error
		loaded, _, err = tx.Runs().Get(ctx, "Rwave")
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	opened := loaded.Open()
	if len(opened) != 2 || opened[0].ID != "plan" || opened[1].ID != "run" {
		t.Fatalf("open = %+v", opened)
	}
	if len(opened[0].Writes) != 1 || opened[0].Writes[0] != "verify/plan.yaml" {
		t.Fatalf("writes = %v", opened[0].Writes)
	}
}

func TestProjectRunWithAuditIsOneTransaction(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	err = st.ProjectRunWithAudit(ctx, sqlite.ProjectedRun{
		ID: "Rtx", WorkflowID: "lite-change", Feature: "demo", Risk: "P1",
		Steps: []sqlite.ProjectedStep{
			{ID: "plan", Kind: "verify.plan", State: run.StepPending},
		},
	}, audit.Event{
		At: time.Now().UTC(), Action: audit.ActionStepRecorded,
		Actor: audit.Actor{Handle: "idev", Kind: "system"},
		RunID: "Rtx", Feature: "demo", Subject: "run.yaml",
		Detail: map[string]any{"source": "run.yaml", "steps": 1},
	})
	if err != nil {
		t.Fatal(err)
	}

	var headSeq int64
	err = st.InTx(ctx, func(tx ports.Tx) error {
		_, seq, err := tx.Audit().Head(ctx)
		headSeq = seq
		if err != nil {
			return err
		}
		_, _, err = tx.Runs().Get(ctx, "Rtx")
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if headSeq != 1 {
		t.Fatalf("audit seq = %d, want 1 (projection and append in one TX)", headSeq)
	}
}
