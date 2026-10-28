package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"go.yaml.in/yaml/v3"
)

// E2.5: the simplified lite-change walk (six steps) through the default
// Go CLI — start, apply, lease acquire with fencing, gate approve — ending
// in status done. Python golden txtar is a separate lane.
func TestLiteChangeWalksToDoneViaCLI(t *testing.T) {
	f := newFixture(t, "alice")
	runFile := filepath.Join(f.ticket, "workflow", "run.yaml")
	must(t, os.MkdirAll(filepath.Dir(runFile), 0o755))
	ticketRel := "tickets/demo"

	code, out, errs := f.do(false, "",
		"run", "start",
		"--file", runFile,
		"--workflow", "lite-change",
		"--feature", "demo",
		"--step", "preflight:preflight.inputs",
		"--step", "scope-guard:route.s4",
		"--step", "code-pass:deliver.code_pass",
		"--step", "plan:verify.plan",
		"--step", "gate-plan:human.gate",
		"--step", "run:verify.run",
	)
	if code != exitOK {
		t.Fatalf("start: %s", errs)
	}
	var started map[string]string
	must(t, json.Unmarshal([]byte(out), &started))
	runID := started["run_id"]

	apply := func(args ...string) {
		t.Helper()
		base := []string{"run", "apply", "--run-id", runID, "--file", runFile}
		code, _, err := f.do(false, "", append(base, args...)...)
		if code != exitOK {
			t.Fatalf("apply %v: %s", args, err)
		}
	}
	acquire := func(step, agent, purpose string) leaseOut {
		t.Helper()
		args := []string{"lease", "acquire", "--run", runFile, "--step", step, "--agent", agent}
		if purpose == "verify" {
			args = append(args, "--purpose", "verify",
				"--ticket-dir", ticketRel, "--write-path", ticketRel+"/**")
		} else {
			args = append(args, "--write-path", "src/**")
		}
		code, out, err := f.do(false, "", args...)
		if code != exitOK {
			t.Fatalf("acquire %s (%s): %s\n%s", step, agent, err, out)
		}
		var held leaseOut
		must(t, json.Unmarshal([]byte(out), &held))
		if held.Agent != agent || held.Fencing == 0 {
			t.Fatalf("lease %+v, want agent %s", held, agent)
		}
		return held
	}
	delegate := func(step, agent, purpose, verifyAgent string) {
		t.Helper()
		apply("--event", "StepActivated", "--step", step)
		apply("--event", "DelegationIssued", "--step", step, "--agent", agent)
		held := acquire(step, agent, purpose)
		apply("--event", "DelegationReturned", "--step", step,
			"--agent", agent, "--fencing", strconv.FormatUint(held.Fencing, 10))
		apply("--event", "DelegationAccepted", "--step", step,
			"--outcome", "PASS", "--evidence", step+"/review.md")
		if verifyAgent == "" {
			return
		}
		vheld := acquire(step, verifyAgent, "verify")
		apply("--event", "VerificationRecorded", "--step", step,
			"--agent", verifyAgent, "--outcome", "PASS",
			"--evidence", step+"/verify.md",
			"--fencing", strconv.FormatUint(vheld.Fencing, 10))
	}

	apply("--event", "ConductorStepStarted", "--step", "preflight")
	apply("--event", "ConductorStepRecorded", "--step", "preflight",
		"--outcome", "PASS", "--evidence", "preflight/probe.md")

	delegate("scope-guard", "idev-ops", "verify", "")
	delegate("code-pass", "idev-coder", "write", "idev-reviewer")
	delegate("plan", "idev-verifier", "verify", "")

	apply("--event", "StepActivated", "--step", "gate-plan")
	apply("--event", "GateRequested", "--step", "gate-plan")

	code, out, errs = f.do(false, "",
		"gate", "request",
		"--feature", "demo", "--run-id", runID, "--step", "gate-plan",
		"--type", "accepted_plan", "--risk", "P1",
		"--root", f.ticket,
		"--subject", "verify/plan.yaml",
		"--will-write", "verify/plan.yaml accepted",
		"--proof", "verify-plan gate: 0 FAIL",
	)
	if code != exitOK {
		t.Fatalf("gate request: %s", errs)
	}
	var req requestOut
	must(t, json.Unmarshal([]byte(out), &req))
	code, _, errs = f.do(true, req.Short+"\n",
		"gate", "approve", req.GateID, "--quote", "确认")
	if code != exitOK {
		t.Fatalf("gate approve: %s", errs)
	}
	st := f.state(req.GateID)
	if st.Approval == nil || st.Approval.ID == "" {
		t.Fatalf("no approval on gate: %+v", st)
	}
	apply("--event", "GateApproved", "--step", "gate-plan",
		"--approval-id", st.Approval.ID, "--by", "alice")

	delegate("run", "idev-verifier", "verify", "")

	raw, err := os.ReadFile(runFile)
	must(t, err)
	var doc map[string]any
	must(t, yaml.Unmarshal(raw, &doc))
	if doc["status"] != "done" {
		t.Fatalf("status = %v, want done\n%s", doc["status"], raw)
	}
	steps, _ := doc["steps"].([]any)
	want := []string{"preflight", "scope-guard", "code-pass", "plan", "gate-plan", "run"}
	if len(steps) != len(want) {
		t.Fatalf("steps = %d, want %d", len(steps), len(want))
	}
	for i, id := range want {
		m := steps[i].(map[string]any)
		if m["id"] != id {
			t.Fatalf("step[%d] id = %v, want %s", i, m["id"], id)
		}
		if m["status"] != "PASS" {
			t.Fatalf("step %s status = %v, want PASS", id, m["status"])
		}
	}
	if !strings.Contains(string(raw), "run_id: "+runID) {
		t.Fatalf("export missing run_id %s", runID)
	}
}
