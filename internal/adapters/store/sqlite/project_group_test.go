package sqlite_test

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/idev/internal/adapters/store/sqlite"
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
