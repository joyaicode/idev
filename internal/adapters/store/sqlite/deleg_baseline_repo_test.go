package sqlite_test

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/domain/baseline"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/canonical"
)

func openStore(t *testing.T) *sqlite.Store {
	t.Helper()
	st, err := sqlite.Open(context.Background(), filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = st.Close() })
	return st
}

func seedLiveRun(t *testing.T, st *sqlite.Store, runID, feature string) {
	t.Helper()
	ctx := context.Background()
	err := st.InTx(ctx, func(tx ports.Tx) error {
		return tx.Runs().Create(ctx, run.Run{
			ID: runID, WorkflowID: "lite-change", Feature: feature,
			Steps: []run.Step{{ID: "code", Kind: "deliver.code_pass", State: run.StepPending}},
		}, feature)
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestDelegationRepoAssignsAttemptAndRejectsDuplicate(t *testing.T) {
	ctx := context.Background()
	st := openStore(t)
	seedLiveRun(t, st, "R1", "demo")

	err := st.InTx(ctx, func(tx ports.Tx) error {
		return tx.Delegations().Insert(ctx, ports.Delegation{
			ID: "d-1", RunID: "R1", StepID: "code", Attempt: 0,
			Agent: "idev-coder", Packet: []byte(`{}`), State: "issued",
			IssuedAt: time.Now().UTC(),
		})
	})
	if err != nil {
		t.Fatal(err)
	}
	var first ports.Delegation
	err = st.InTx(ctx, func(tx ports.Tx) error {
		var err error
		first, err = tx.Delegations().Get(ctx, "d-1")
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if first.Attempt != 1 {
		t.Fatalf("server-assigned attempt = %d, want 1", first.Attempt)
	}

	err = st.InTx(ctx, func(tx ports.Tx) error {
		return tx.Delegations().Insert(ctx, ports.Delegation{
			ID: "d-2", RunID: "R1", StepID: "code", Attempt: 1,
			Agent: "idev-coder", Packet: []byte(`{}`), State: "issued",
			IssuedAt: time.Now().UTC(),
		})
	})
	var conflict *ports.ConflictError
	if !errors.As(err, &conflict) || conflict.Kind != ports.ConflictAttemptExists {
		t.Fatalf("duplicate attempt: %v, want ConflictAttemptExists", err)
	}

	err = st.InTx(ctx, func(tx ports.Tx) error {
		return tx.Delegations().Insert(ctx, ports.Delegation{
			ID: "d-3", RunID: "R1", StepID: "code", Attempt: 0,
			Agent: "idev-coder", Packet: []byte(`{}`), State: "issued",
			IssuedAt: time.Now().UTC(),
		})
	})
	if err != nil {
		t.Fatal(err)
	}
	var second ports.Delegation
	err = st.InTx(ctx, func(tx ports.Tx) error {
		var err error
		second, err = tx.Delegations().Latest(ctx, "R1", "code")
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if second.ID != "d-3" || second.Attempt != 2 {
		t.Fatalf("latest = %+v, want d-3 attempt 2", second)
	}
}

func TestBaselineRepoSecondSealConflicts(t *testing.T) {
	ctx := context.Background()
	st := openStore(t)
	at := time.Now().UTC()
	m1 := baseline.Manifest{
		Schema: baseline.Schema, Feature: "demo", Revision: 1,
		ManifestRoot: canonical.Digest("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
		RawRoot:      canonical.Digest("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
		CreatedAt:    at,
	}
	m2 := m1
	m2.Revision = 2
	m2.ManifestRoot = canonical.Digest("cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")

	var id1 string
	err := st.InTx(ctx, func(tx ports.Tx) error {
		var err error
		id1, err = tx.Baselines().Put(ctx, "demo", m1, "draft")
		if err != nil {
			return err
		}
		return tx.Baselines().Seal(ctx, id1, at)
	})
	if err != nil {
		t.Fatal(err)
	}

	err = st.InTx(ctx, func(tx ports.Tx) error {
		id2, err := tx.Baselines().Put(ctx, "demo", m2, "draft")
		if err != nil {
			return err
		}
		return tx.Baselines().Seal(ctx, id2, at)
	})
	var conflict *ports.ConflictError
	if !errors.As(err, &conflict) || conflict.Kind != ports.ConflictSealedBaseline {
		t.Fatalf("second seal: %v, want ConflictSealedBaseline", err)
	}

	var sealed baseline.Manifest
	err = st.InTx(ctx, func(tx ports.Tx) error {
		var err error
		sealed, err = tx.Baselines().Sealed(ctx, "demo")
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if sealed.Revision != 1 {
		t.Fatalf("sealed revision = %d, want 1 (first seal kept)", sealed.Revision)
	}
}
