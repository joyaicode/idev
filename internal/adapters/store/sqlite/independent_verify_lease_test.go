package sqlite_test

import (
	"context"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/kindreg"
	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/app/leasesvc"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

// E3.1: a projected verifying step of a verify:independent kind hands the
// verify lease to the registry's verifier, and refuses the writer.
func TestIndependentVerifyLeaseFromProjection(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	err = st.ProjectRun(ctx, sqlite.ProjectedRun{
		ID: "Rind", WorkflowID: "lite-change", Feature: "demo", Risk: "P1",
		Steps: []sqlite.ProjectedStep{
			{ID: "code", Kind: "deliver.code_pass", State: run.StepVerifying, Writer: "idev-coder"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}

	svc := leasesvc.Service{
		Store: st, Clock: &clock{t: time.Date(2026, 10, 28, 14, 0, 0, 0, time.UTC)},
		IDs: &seq{}, TTL: time.Hour, Kinds: kindreg.MustLoad(),
	}
	verify := func(agent string) (leasesvc.Held, error) {
		return svc.Acquire(ctx, leasesvc.AcquireParams{
			Purpose: lease.PurposeVerify, Feature: "demo", RunID: "Rind", StepID: "code",
			Agent: agent, TicketDir: "tickets/demo", WritePaths: []string{"tickets/demo/**"},
			Actor: ports.Principal{Handle: "workflow.py", Kind: "service"},
		})
	}

	held, err := verify("idev-reviewer")
	if err != nil {
		t.Fatalf("verifier acquire: %v", err)
	}
	if held.Lease.Purpose != lease.PurposeVerify || held.Lease.Fencing == 0 {
		t.Fatalf("lease %+v", held.Lease)
	}

	_, err = verify("idev-coder")
	if err == nil {
		t.Fatal("the writer got the independent verify lease")
	}
	if !strings.Contains(err.Error(), "idev-reviewer verifies") &&
		!strings.Contains(err.Error(), "writer does not verify") {
		t.Fatalf("refusal = %q", err)
	}
}
