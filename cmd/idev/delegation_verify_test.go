package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func allocateWriter(t *testing.T, f fixture) string {
	t.Helper()
	code, out, errOut := f.do(false, "", "delegation", "allocate",
		"--run-id", "01VERIFYRUN000000000000000", "--step", "fix", "--agent", "idev-coder", "--feature", "demo")
	if code != exitOK {
		t.Fatalf("allocate: %s %s", out, errOut)
	}
	var got map[string]any
	must(t, json.Unmarshal([]byte(out), &got))
	return got["id"].(string)
}

func auditActions(t *testing.T, f fixture) map[string]map[string]any {
	t.Helper()
	code, out, errOut := f.do(false, "", "audit", "export")
	if code != exitOK {
		t.Fatalf("export: %s", errOut)
	}
	byAction := map[string]map[string]any{}
	for _, line := range strings.Split(strings.TrimSpace(out), "\n") {
		var ev map[string]any
		must(t, json.Unmarshal([]byte(line), &ev))
		byAction[ev["action"].(string)] = ev
	}
	return byAction
}

func TestDelegationVerifyAttachesToTheWritersAttempt(t *testing.T) {
	f := newFixture(t, "")
	id := allocateWriter(t, f)

	if code, _, errOut := f.do(false, "", "delegation", "verify",
		"--id", id, "--verifier", "idev-coder", "--verdict", "PASS"); code == exitOK || !strings.Contains(errOut, "another agent") {
		t.Fatalf("the writer verified itself: code=%d err=%s", code, errOut)
	}
	code, out, errOut := f.do(false, "", "delegation", "verify",
		"--id", id, "--verifier", "idev-reviewer", "--verdict", "PASS", "--evidence", "review.md")
	if code != exitOK {
		t.Fatalf("verify: %s %s", out, errOut)
	}
	var got map[string]any
	must(t, json.Unmarshal([]byte(out), &got))
	if got["attempt"] != float64(1) || got["delegation_id"] != id {
		t.Fatalf("verify out = %v", got)
	}
	if code, _, errOut := f.do(false, "", "delegation", "verify",
		"--id", id, "--verifier", "idev-reviewer", "--verdict", "PASS"); code == exitOK || !strings.Contains(errOut, "already verified") {
		t.Fatalf("a second verification of one attempt: code=%d err=%s", code, errOut)
	}

	ev := auditActions(t, f)["verification.recorded"]
	if ev == nil || ev["step_id"] != "fix" || ev["subject"] != id {
		t.Fatalf("verification.recorded = %v", ev)
	}

	code, out, errOut = f.do(false, "", "delegation", "allocate",
		"--run-id", "01VERIFYRUN000000000000000", "--step", "fix", "--agent", "idev-coder", "--feature", "demo")
	if code != exitOK {
		t.Fatalf("second allocate: %s", errOut)
	}
	must(t, json.Unmarshal([]byte(out), &got))
	if got["attempt"] != float64(2) {
		t.Fatalf("the verification took an attempt number: next writer attempt = %v", got["attempt"])
	}
}

func TestDelegationAcceptRecordsTheFindingsAndTheReason(t *testing.T) {
	f := newFixture(t, "")
	id := allocateWriter(t, f)

	if code, _, _ := f.do(false, "", "delegation", "accept",
		"--id", id, "--finding", "scope-honest"); code != exitUsage {
		t.Fatalf("accept without a reason: code=%d", code)
	}
	code, out, errOut := f.do(false, "", "delegation", "accept", "--id", id,
		"--finding", "scope-honest", "--finding", "red-first", "--reason", "the checker misreads a rename as scope creep")
	if code != exitOK {
		t.Fatalf("accept: %s %s", out, errOut)
	}
	ev := auditActions(t, f)["delegation.accepted"]
	detail, _ := ev["detail"].(map[string]any)
	findings, _ := detail["accepted_with_findings"].([]any)
	if len(findings) != 2 || !strings.Contains(detail["reason"].(string), "rename") {
		t.Fatalf("delegation.accepted = %v", ev)
	}
}
