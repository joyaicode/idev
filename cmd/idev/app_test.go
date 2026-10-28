package main

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/local"
	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/ports"
)

type fixture struct {
	t      *testing.T
	data   string
	ticket string
	people string
}

func newFixture(t *testing.T, handle string) fixture {
	t.Helper()
	dir := t.TempDir()
	f := fixture{t: t, data: filepath.Join(dir, "data"), ticket: filepath.Join(dir, "ticket"), people: filepath.Join(dir, "people.yaml")}
	t.Setenv("IDEV_DATA", f.data)
	must(t, os.MkdirAll(filepath.Join(f.ticket, "verify"), 0o755))
	must(t, os.WriteFile(filepath.Join(f.ticket, "verify", "plan.yaml"), []byte("cases: []\n"), 0o644))
	must(t, os.WriteFile(filepath.Join(f.ticket, "baseline.yaml"), []byte("revision: 1\n"), 0o644))
	must(t, os.WriteFile(filepath.Join(f.ticket, "req.yaml"), []byte("items: []\n"), 0o644))
	must(t, os.WriteFile(f.people, []byte("people:\n  - alice\n"), 0o644))
	if handle != "" {
		cred := local.Credential{Handle: handle, Token: local.TokenPrefix + "test"}
		path := filepath.Join(f.data, "secrets", "human.yaml")
		must(t, os.MkdirAll(filepath.Dir(path), 0o700))
		must(t, os.WriteFile(path, []byte("handle: "+cred.Handle+"\ntoken: "+cred.Token+"\n"), 0o600))
	}
	return f
}

func must(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

// do runs one command. tty is what the terminal check sees; input is what
// the person types.
func (f fixture) do(tty bool, input string, args ...string) (int, string, string) {
	var out, errb bytes.Buffer
	a := app{
		stdin: strings.NewReader(input), stdout: &out, stderr: &errb,
		isTTY: func() bool { return tty }, peopleFiles: []string{f.people},
	}
	code := a.run(args)
	return code, out.String(), errb.String()
}

func (f fixture) ask(args ...string) requestOut {
	f.t.Helper()
	base := []string{"gate", "request", "--feature", "demo", "--run-id", "R1", "--step", "plan_ok"}
	code, out, errs := f.do(false, "", append(base, args...)...)
	if code != exitOK {
		f.t.Fatalf("request exit %d: %s", code, errs)
	}
	var r requestOut
	must(f.t, json.Unmarshal([]byte(out), &r))
	return r
}

func (f fixture) askPlan() requestOut {
	return f.ask("--type", "accepted_plan", "--risk", "P1", "--root", f.ticket,
		"--subject", "verify/plan.yaml", "--will-write", "verify/plan.yaml accepted", "--proof", "plan-check 0 FAIL")
}

func (f fixture) state(id string) statusOut {
	f.t.Helper()
	code, out, errs := f.do(false, "", "gate", "status", id)
	if code != exitOK {
		f.t.Fatalf("status exit %d: %s", code, errs)
	}
	var s statusOut
	must(f.t, json.Unmarshal([]byte(out), &s))
	return s
}

func TestAnAgentShellCannotAnswer(t *testing.T) {
	f := newFixture(t, "alice")
	r := f.askPlan()
	code, _, errs := f.do(false, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认")
	if code != exitRefused || !strings.Contains(errs, "TTY") {
		t.Fatalf("approve without a terminal: exit %d, %q", code, errs)
	}
	if s := f.state(r.GateID); s.Status != "pending" || s.Approval != nil {
		t.Fatalf("refused answer left %+v", s)
	}
}

func TestThePersonApprovesFromTheirTerminal(t *testing.T) {
	f := newFixture(t, "alice")
	r := f.askPlan()
	code, out, errs := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认")
	if code != exitOK {
		t.Fatalf("approve exit %d: %s", code, errs)
	}
	if !strings.Contains(out, "approved") {
		t.Fatalf("approve said %q", out)
	}
	s := f.state(r.GateID)
	if s.Status != "approved" || !s.DigestMatch || s.Approval == nil {
		t.Fatalf("status %+v", s)
	}
	ap := s.Approval
	if ap.Handle != "alice" || ap.Quote != "确认" || ap.Assurance != "low" || !ap.SignatureOK || ap.Channel != "local_token_tty" {
		t.Fatalf("approval %+v", ap)
	}
	if ap.Downgraded {
		t.Fatalf("accepted_plan at P1 needs low; nothing was downgraded")
	}
}

func TestTheAuditChainHoldsAfterADecision(t *testing.T) {
	f := newFixture(t, "alice")
	r := f.askPlan()
	if code, _, errs := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认"); code != exitOK {
		t.Fatal(errs)
	}
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(f.data, "idev.db"))
	must(t, err)
	defer st.Close()
	var events []audit.Event
	must(t, st.InTx(ctx, func(tx ports.Tx) error {
		var err error
		events, err = tx.Audit().Range(ctx, 1, 0)
		return err
	}))
	if len(events) != 2 || events[0].Action != audit.ActionGateRequested || events[1].Action != audit.ActionGateApproved {
		t.Fatalf("events %+v", events)
	}
	must(t, audit.Verify(audit.Genesis, events))
	if _, err := st.DB().ExecContext(ctx, `UPDATE approvals SET quote = 'forged'`); err == nil {
		t.Fatal("an approval was edited in place")
	}
}

func TestTheWrongShortCodeRecordsNothing(t *testing.T) {
	f := newFixture(t, "alice")
	r := f.askPlan()
	code, _, errs := f.do(true, "ZZZZ\n", "gate", "approve", r.GateID, "--quote", "确认")
	if code != exitRefused || !strings.Contains(errs, "short code") {
		t.Fatalf("exit %d, %q", code, errs)
	}
	if s := f.state(r.GateID); s.Status != "pending" {
		t.Fatalf("status %s", s.Status)
	}
}

func TestSomeoneOffTheWhitelistCannotSign(t *testing.T) {
	for _, handle := range []string{"bob", "claude"} {
		t.Run(handle, func(t *testing.T) {
			f := newFixture(t, handle)
			r := f.askPlan()
			code, _, errs := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认")
			if code != exitRefused {
				t.Fatalf("%s signed: exit %d %q", handle, code, errs)
			}
			if s := f.state(r.GateID); s.Status != "pending" {
				t.Fatalf("status %s", s.Status)
			}
		})
	}
}

func TestContentChangedAfterTheQuestionIsRefused(t *testing.T) {
	f := newFixture(t, "alice")
	r := f.askPlan()
	must(t, os.WriteFile(filepath.Join(f.ticket, "verify", "plan.yaml"), []byte("cases: [edited]\n"), 0o644))
	if s := f.state(r.GateID); s.DigestMatch {
		t.Fatal("status says the edited plan still matches")
	}
	code, out, errs := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认")
	if code != exitRefused || !strings.Contains(out, "CHANGED") {
		t.Fatalf("approved stale content: exit %d %q %q", code, out, errs)
	}
}

func TestAnUnclearAnswerIsNotAnApproval(t *testing.T) {
	f := newFixture(t, "alice")
	r := f.askPlan()
	code, _, _ := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "看着差不多")
	if code != exitRefused {
		t.Fatalf("a non-answer approved: exit %d", code)
	}
	if s := f.state(r.GateID); s.Status != "pending" {
		t.Fatalf("status %s", s.Status)
	}
}

func TestARejectionSaysSoAndIsFinal(t *testing.T) {
	f := newFixture(t, "alice")
	r := f.askPlan()
	if code, _, _ := f.do(true, r.Short+"\n", "gate", "reject", r.GateID, "--quote", "确认"); code != exitRefused {
		t.Fatal("reject accepted words that confirm")
	}
	if code, _, errs := f.do(true, r.Short+"\n", "gate", "reject", r.GateID, "--quote", "驳回"); code != exitOK {
		t.Fatal(errs)
	}
	s := f.state(r.GateID)
	if s.Status != "rejected" || s.Approval == nil || s.Approval.Decision != "reject" {
		t.Fatalf("status %+v", s)
	}
	if code, _, _ := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认"); code != exitRefused {
		t.Fatal("a decided gate was answered again")
	}
}

func TestTheSealAtP1BindsBaselineAndReqAndIsMarkedDowngraded(t *testing.T) {
	f := newFixture(t, "alice")
	if code, _, _ := f.do(false, "", "gate", "request", "--feature", "demo", "--type", "sealed", "--risk", "P1",
		"--root", f.ticket, "--subject", "baseline.yaml", "--will-write", "sealed", "--proof", "grill frontier empty"); code != exitRefused {
		t.Fatal("a seal with no baseline revision was asked")
	}
	r := f.ask("--type", "sealed", "--risk", "P1", "--revision", "1", "--root", f.ticket,
		"--subject", "baseline.yaml", "--subject", "req.yaml",
		"--will-write", "baseline sealed", "--will-write", "req.yaml accepted", "--proof", "grill frontier empty")
	if r.RequiredAssurance != "high" || r.SubjectKind != "baseline" {
		t.Fatalf("request %+v", r)
	}
	must(t, os.WriteFile(filepath.Join(f.ticket, "baseline.yaml"), []byte("revision: 1\ngoal: tampered\n"), 0o644))
	if s := f.state(r.GateID); s.DigestMatch {
		t.Fatal("editing baseline.yaml did not change what the seal binds to")
	}
	must(t, os.WriteFile(filepath.Join(f.ticket, "baseline.yaml"), []byte("revision: 1\n"), 0o644))
	if code, _, errs := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认"); code != exitOK {
		t.Fatal(errs)
	}
	if s := f.state(r.GateID); s.Approval == nil || !s.Approval.Downgraded {
		t.Fatalf("a high requirement answered at low must say so: %+v", s.Approval)
	}
}

func TestAuditDowngradesCountsADowngradeInItsOwnWeek(t *testing.T) {
	f := newFixture(t, "alice")
	// A low ask answered at low is the ordinary case and must not count.
	p := f.askPlan()
	if code, _, errs := f.do(true, p.Short+"\n", "gate", "approve", p.GateID, "--quote", "确认"); code != exitOK {
		t.Fatal(errs)
	}
	// A high ask (the P1 seal) answered at low is one downgrade.
	r := f.ask("--type", "sealed", "--risk", "P1", "--revision", "1", "--root", f.ticket,
		"--subject", "baseline.yaml", "--subject", "req.yaml",
		"--will-write", "baseline sealed", "--proof", "grill frontier empty")
	if code, _, errs := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认"); code != exitOK {
		t.Fatal(errs)
	}
	code, out, errs := f.do(false, "", "audit", "downgrades")
	if code != exitOK {
		t.Fatalf("audit downgrades exit %d: %s", code, errs)
	}
	var d downgradesOut
	must(t, json.Unmarshal([]byte(out), &d))
	y, w := time.Now().UTC().ISOWeek()
	want := downgradesOut{Total: 1, Weeks: []downgradeWeek{{Week: fmt.Sprintf("%04d-W%02d", y, w), Count: 1}}}
	if !reflect.DeepEqual(d, want) {
		t.Fatalf("downgrades = %+v, want %+v", d, want)
	}
}

func TestAuditDowngradesGroupsEventsByISOWeek(t *testing.T) {
	f := newFixture(t, "alice")
	// The CLI writes events at "now"; weeks other than this one can only
	// exist in the chain, so seed them directly.
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(f.data, "idev.db"))
	must(t, err)
	actor := audit.Actor{Handle: "alice", Kind: "human"}
	seed := []audit.Event{
		{At: time.Date(2025, 12, 25, 9, 0, 0, 0, time.UTC), Action: audit.ActionAssuranceDowngraded, Actor: actor},
		{At: time.Date(2026, 1, 2, 9, 0, 0, 0, time.UTC), Action: audit.ActionGateApproved, Actor: actor},
		{At: time.Date(2026, 1, 2, 10, 0, 0, 0, time.UTC), Action: audit.ActionAssuranceDowngraded, Actor: actor},
		{At: time.Date(2026, 1, 3, 9, 0, 0, 0, time.UTC), Action: audit.ActionAssuranceDowngraded, Actor: actor},
		{At: time.Date(2026, 1, 8, 9, 0, 0, 0, time.UTC), Action: audit.ActionAssuranceDowngraded, Actor: actor},
	}
	must(t, st.InTx(ctx, func(tx ports.Tx) error {
		for _, ev := range seed {
			if _, err := tx.Audit().Append(ctx, ev); err != nil {
				return err
			}
		}
		return nil
	}))
	must(t, st.Close()) // the CLI opens the same file; hand it over unlocked

	code, out, errs := f.do(false, "", "audit", "downgrades")
	if code != exitOK {
		t.Fatalf("audit downgrades exit %d: %s", code, errs)
	}
	var d downgradesOut
	must(t, json.Unmarshal([]byte(out), &d))
	want := downgradesOut{Total: 4, Weeks: []downgradeWeek{
		{Week: "2025-W52", Count: 1},
		{Week: "2026-W01", Count: 2},
		{Week: "2026-W02", Count: 1},
	}}
	if !reflect.DeepEqual(d, want) {
		t.Fatalf("downgrades = %+v, want %+v", d, want)
	}
}

func TestTheCredentialIsIssuedOnlyAtATerminalToAPerson(t *testing.T) {
	f := newFixture(t, "")
	if code, _, _ := f.do(false, "", "token", "init", "--handle", "alice"); code != exitRefused {
		t.Fatal("credential issued without a terminal")
	}
	if code, _, _ := f.do(true, "", "token", "init", "--handle", "claude"); code != exitRefused {
		t.Fatal("credential issued to a model")
	}
	if code, _, errs := f.do(true, "", "token", "init", "--handle", "alice"); code != exitOK {
		t.Fatal(errs)
	}
	info, err := os.Stat(filepath.Join(f.data, "secrets", "human.yaml"))
	must(t, err)
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("credential mode %v", info.Mode().Perm())
	}
	if code, _, _ := f.do(true, "", "token", "init", "--handle", "alice"); code != exitRefused {
		t.Fatal("an existing credential was overwritten")
	}
}

func TestOnePendingQuestionPerStep(t *testing.T) {
	f := newFixture(t, "alice")
	first := f.askPlan()
	code, _, errs := f.do(false, "", "gate", "request", "--feature", "demo", "--run-id", "R1", "--step", "plan_ok",
		"--type", "accepted_plan", "--risk", "P1", "--root", f.ticket, "--subject", "verify/plan.yaml",
		"--will-write", "verify/plan.yaml accepted", "--proof", "x")
	if code != exitRefused || !strings.Contains(errs, "gate_pending") || !strings.Contains(errs, first.GateID+" already pending") {
		t.Fatalf("second pending gate on a step: exit %d %q", code, errs)
	}
}

func TestAFileGateWithNoBindingIsNotCheckedAsAQuestion(t *testing.T) {
	f := newFixture(t, "")
	r := f.askPlan()
	if before := f.state(r.GateID); !before.DigestMatch {
		t.Fatalf("fresh file gate does not match its files: %+v", before)
	}
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(f.data, "idev.db"))
	must(t, err)
	defer st.Close()
	must(t, st.Tx(ctx, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx, `DELETE FROM gate_subjects WHERE gate_id = ?`, r.GateID)
		return err
	}))
	after := f.state(r.GateID)
	if after.DigestMatch || !strings.Contains(after.DigestNow, "subject binding missing") {
		t.Fatalf("a missing file binding was treated as some other digest: %+v", after)
	}
}
