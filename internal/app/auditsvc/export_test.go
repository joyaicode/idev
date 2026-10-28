package auditsvc_test

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/memstore"
	"github.com/idev/internal/app/auditsvc"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/ports"
)

func TestExportFiltersByRunAndKeepsSeqOrder(t *testing.T) {
	st := memstore.New()
	svc := auditsvc.Service{Store: st, Clock: fixedClock{at}}
	ctx := context.Background()
	actor := audit.Actor{Handle: "c", Kind: "conductor"}
	seed := []audit.Event{
		{At: at, Action: audit.ActionRunStarted, Actor: actor, RunID: "run-a", Feature: "f"},
		{At: at.Add(time.Second), Action: audit.ActionStepActivated, Actor: actor, RunID: "run-a", StepID: "s1"},
		{At: at.Add(2 * time.Second), Action: audit.ActionDelegationIssued, Actor: actor, RunID: "run-a", StepID: "s1"},
		{At: at.Add(3 * time.Second), Action: audit.ActionRunStarted, Actor: actor, RunID: "run-b", Feature: "f"},
	}
	if err := st.InTx(ctx, func(tx ports.Tx) error {
		for _, ev := range seed {
			if _, err := tx.Audit().Append(ctx, ev); err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}

	var buf bytes.Buffer
	n, err := svc.Export(ctx, "run-a", &buf)
	if err != nil {
		t.Fatal(err)
	}
	if n != 3 {
		t.Fatalf("exported %d lines, want 3", n)
	}
	lines := strings.Split(strings.TrimSpace(buf.String()), "\n")
	if len(lines) != 3 {
		t.Fatalf("jsonl lines = %d", len(lines))
	}
	var actions []string
	var prevSeq int64
	for i, line := range lines {
		var row auditsvc.ExportLine
		if err := json.Unmarshal([]byte(line), &row); err != nil {
			t.Fatalf("line %d: %v", i, err)
		}
		if row.RunID != "run-a" {
			t.Fatalf("line %d run_id=%s", i, row.RunID)
		}
		if row.Seq <= prevSeq {
			t.Fatalf("seq not increasing: %d after %d", row.Seq, prevSeq)
		}
		prevSeq = row.Seq
		actions = append(actions, string(row.Action))
		if row.Hash == "" || row.PrevHash == "" {
			t.Fatalf("line %d missing hash chain fields", i)
		}
	}
	want := "run.started step.activated delegation.issued"
	if strings.Join(actions, " ") != want {
		t.Fatalf("actions = %v, want %s", actions, want)
	}
}
