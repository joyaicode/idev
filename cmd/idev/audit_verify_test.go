package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/ports"
)

func seedChain(t *testing.T, f fixture, n int) {
	t.Helper()
	ctx := context.Background()
	must(t, os.MkdirAll(f.data, 0o700))
	st, err := sqlite.Open(ctx, filepath.Join(f.data, "idev.db"))
	must(t, err)
	defer st.Close()
	now := time.Date(2026, 10, 28, 9, 0, 0, 0, time.UTC)
	for i := 1; i <= n; i++ {
		must(t, st.InTx(ctx, func(tx ports.Tx) error {
			_, err := tx.Audit().Append(ctx, audit.Event{At: now, Action: audit.ActionRunStarted,
				Actor: audit.Actor{Handle: "workflow.py", Kind: "service"}, RunID: fmt.Sprintf("R%d", i), Feature: "demo"})
			return err
		}))
	}
}

func TestAuditVerifyWalksAYoungChainFromGenesis(t *testing.T) {
	f := newFixture(t, "")
	seedChain(t, f, 3)
	for _, args := range [][]string{{"audit", "verify"}, {"audit", "verify", "--from", "1"}} {
		code, out, errs := f.do(false, "", args...)
		if code != exitOK {
			t.Fatalf("%v: exit %d: %s", args, code, errs)
		}
		var got verifyOut
		must(t, json.Unmarshal([]byte(out), &got))
		if want := (verifyOut{From: 1, To: 3}); got != want {
			t.Fatalf("%v: got %+v, want %+v", args, got, want)
		}
	}
}

func TestAuditVerifyNamesTheEditedRow(t *testing.T) {
	f := newFixture(t, "")
	seedChain(t, f, 3)
	db, err := sql.Open("sqlite", filepath.Join(f.data, "idev.db"))
	must(t, err)
	_, err = db.Exec("DROP TRIGGER audit_no_update")
	must(t, err)
	_, err = db.Exec("UPDATE audit_events SET feature = 'other' WHERE seq = 2")
	must(t, err)
	must(t, db.Close())

	code, out, errs := f.do(false, "", "audit", "verify", "--from", "1")
	if code != exitRefused || !strings.Contains(errs, "chain broken at seq 2") {
		t.Fatalf("exit %d, stdout %q, stderr %q; want a refusal naming seq 2", code, out, errs)
	}
}

func TestAuditVerifyRefusesAnUnknownFlag(t *testing.T) {
	f := newFixture(t, "")
	if code, _, errs := f.do(false, "", "audit", "verify", "--since", "1"); code != exitUsage {
		t.Fatalf("exit %d: %s; want usage", code, errs)
	}
}
