package sqlite_test

import (
	"context"
	"errors"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/ports"
)

func TestAGateReadsBackAsItWasAsked(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()

	now := time.Date(2026, 10, 19, 8, 0, 0, 123, time.UTC)
	want, err := gate.Open(gate.Policy{}, gate.Request{
		ID: "01JGATE0000000000000000001", Type: gate.TypeDefectOrigin, RunID: "R1", StepID: "s1",
		Feature: "demo", Risk: gate.RiskP1, Origin: "req",
		Subject:   gate.Subject{Kind: gate.SubjectArtifactSet, Digest: "sha256:ab"},
		WillWrite: []string{"defect.origin"}, Proof: "repro log", Now: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	err = st.InTx(ctx, func(tx ports.Tx) error {
		if err := tx.Gates().Open(ctx, want, "demo"); err != nil {
			return err
		}
		_, err := tx.Audit().Append(ctx, audit.Event{At: now, Action: audit.ActionGateRequested,
			Actor: audit.Actor{Handle: "workflow.py", Kind: "service"}, Subject: want.ID})
		return err
	})
	if err != nil {
		t.Fatal(err)
	}

	var got gate.Gate
	var events []audit.Event
	err = st.InTx(ctx, func(tx ports.Tx) error {
		var err error
		if got, err = tx.Gates().Get(ctx, want.ID); err != nil {
			return err
		}
		events, err = tx.Audit().Range(ctx, 1, 0)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("read back\n %+v\nasked\n %+v", got, want)
	}
	if err := audit.Verify(audit.Genesis, events); err != nil {
		t.Fatal(err)
	}

	err = st.InTx(ctx, func(tx ports.Tx) error {
		_, err := tx.Delegations().Get(ctx, "D1")
		return err
	})
	if err == nil {
		t.Fatal("a repo this build does not wire answered as if it did")
	}
	var ce *ports.ConflictError
	err = st.InTx(ctx, func(tx ports.Tx) error {
		_, err := tx.Gates().Get(ctx, "missing")
		return err
	})
	if !errors.As(err, &ce) || ce.Kind != ports.ConflictNotFound {
		t.Fatalf("missing gate: %v", err)
	}
}
