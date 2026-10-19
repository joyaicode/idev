package sqlite_test

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/app/leasesvc"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
)

type clock struct{ t time.Time }

func (c *clock) Now() time.Time { return c.t }

type seq struct{ n int }

func (s *seq) New() string {
	s.n++
	return "01JLEASE00000000000000000" + string(rune('A'+s.n))
}

func project(t *testing.T, st *sqlite.Store, runID, writer string) {
	t.Helper()
	err := st.ProjectRun(context.Background(), sqlite.ProjectedRun{
		ID: runID, WorkflowID: "dev-logic", Feature: "demo", Risk: "P1",
		Steps: []sqlite.ProjectedStep{
			{ID: "plan", Kind: "verify.plan", State: run.StepPASS},
			{ID: "code", Kind: "deliver.code_pass", State: run.StepDelegated, Writer: writer},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
}

func acquire(svc leasesvc.Service, runID, agent string) (leasesvc.Held, error) {
	return svc.Acquire(context.Background(), leasesvc.AcquireParams{
		Purpose: lease.PurposeWrite, Feature: "demo", RunID: runID, StepID: "code",
		Agent: agent, WritePaths: []string{"src/**"},
		Actor: ports.Principal{Handle: "workflow.py", Kind: "service"},
	})
}

func isConflict(err error, kind string) bool {
	var ce *ports.ConflictError
	return errors.As(err, &ce) && ce.Kind == kind
}

func TestLeasesFollowTheProjectedRunAndHoldOneWriter(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	c := &clock{t: time.Date(2026, 10, 19, 9, 0, 0, 0, time.UTC)}
	svc := leasesvc.Service{Store: st, Clock: c, IDs: &seq{}, TTL: time.Hour}

	project(t, st, "R1", "idev-coder")
	if _, err := acquire(svc, "R1", "idev-reviewer"); err == nil {
		t.Fatal("an agent the step was not delegated to got the write lease")
	}
	first, err := acquire(svc, "R1", "idev-coder")
	if err != nil {
		t.Fatal(err)
	}
	if first.Lease.Fencing != 1 || first.Token == "" {
		t.Fatalf("first lease %+v", first.Lease)
	}

	project(t, st, "R2", "idev-coder")
	if _, err := acquire(svc, "R2", "idev-coder"); !isConflict(err, ports.ConflictLeaseHeld) {
		t.Fatalf("a second writer on the feature: %v", err)
	}

	actor := ports.Principal{Handle: "workflow.py", Kind: "service"}
	if err := svc.Release(ctx, first.Lease.ID, "not-the-token", actor); !isConflict(err, ports.ConflictLeaseHeld) {
		t.Fatalf("released without the token: %v", err)
	}
	if err := svc.Release(ctx, first.Lease.ID, first.Token, actor); err != nil {
		t.Fatal(err)
	}
	second, err := acquire(svc, "R2", "idev-coder")
	if err != nil {
		t.Fatalf("the slot was not freed: %v", err)
	}
	if second.Lease.Fencing != 2 {
		t.Fatalf("fencing went %d -> %d", first.Lease.Fencing, second.Lease.Fencing)
	}

	// The deadline falls on a whole second; one nanosecond later it must
	// sweep. A variable-width timestamp sorts "…00Z" after "…00.000000001Z"
	// and keeps the lease alive.
	c.t = second.Lease.ExpiresAt.Add(time.Nanosecond)
	n, err := svc.Sweep(ctx)
	if err != nil || n != 1 {
		t.Fatalf("sweep at the deadline: n=%d err=%v", n, err)
	}
	if _, err := svc.Renew(ctx, second.Lease.ID, second.Token); !isConflict(err, ports.ConflictLeaseHeld) {
		t.Fatalf("an expired lease was renewed: %v", err)
	}
	if _, err := acquire(svc, "R2", "idev-coder"); err != nil {
		t.Fatalf("an expired lease kept the slot: %v", err)
	}
}
