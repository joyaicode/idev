package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
)

const auditRunID = "01AUDITRUN0000000000000000"

const runOpened = `schema_version: 1
run_id: 01AUDITRUN0000000000000000
workflow_id: code-review
feature: code-review
status: running
steps:
- id: report
  kind: review.report
- id: gate-report
  kind: human.gate
`

const runReported = `schema_version: 1
run_id: 01AUDITRUN0000000000000000
workflow_id: code-review
feature: code-review
status: running
steps:
- id: report
  kind: review.report
  delegated:
    agent: idev-reviewer
    at: '2026-10-23T16:26:11+08:00'
  lease:
    id: 01LEASEREPORT0000000000000
    released_at: '2026-10-23T16:58:44+08:00'
  note: 无 blocking
  status: PASS
  at: '2026-10-23T16:58:44+08:00'
  evidence: docs/task/code-review/review.md
- id: gate-report
  kind: human.gate
`

const runSigned = `schema_version: 1
run_id: 01AUDITRUN0000000000000000
workflow_id: code-review
feature: code-review
status: done
steps:
- id: report
  kind: review.report
  delegated:
    agent: idev-reviewer
    at: '2026-10-23T16:26:11+08:00'
  lease:
    id: 01LEASEREPORT0000000000000
    released_at: '2026-10-23T16:58:44+08:00'
  note: 无 blocking
  status: PASS
  at: '2026-10-23T16:58:44+08:00'
  evidence: docs/task/code-review/review.md
- id: gate-report
  kind: human.gate
  signoff:
    by: alice
    quote: 确认
    at: '2026-10-23T17:32:49+08:00'
    assurance: chat
  status: PASS
  at: '2026-10-23T17:32:49+08:00'
  evidence: review.md I1-I3 全部签收
`

func writeRun(t *testing.T, f fixture, path, body, expect string) string {
	t.Helper()
	code, out, errOut := f.do(false, body, "run", "write", "--file", path, "--expect-sha256", expect)
	if code != exitOK {
		t.Fatalf("run write: %s %s", out, errOut)
	}
	var got map[string]string
	must(t, json.Unmarshal([]byte(out), &got))
	return got["sha256"]
}

func runEvents(t *testing.T, f fixture) []map[string]any {
	t.Helper()
	code, out, errOut := f.do(false, "", "audit", "export", "--run", auditRunID)
	if code != exitOK {
		t.Fatalf("export: %s", errOut)
	}
	var events []map[string]any
	for _, line := range strings.Split(strings.TrimSpace(out), "\n") {
		if line == "" {
			continue
		}
		var ev map[string]any
		must(t, json.Unmarshal([]byte(line), &ev))
		events = append(events, ev)
	}
	return events
}

func stepTrail(events []map[string]any) []string {
	var trail []string
	for _, ev := range events {
		action, _ := ev["action"].(string)
		if !strings.HasPrefix(action, "step.") && !strings.HasPrefix(action, "run.") {
			continue
		}
		step, _ := ev["step_id"].(string)
		detail, _ := ev["detail"].(map[string]any)
		outcome, _ := detail["outcome"].(string)
		trail = append(trail, strings.TrimSpace(action+" "+step+" "+outcome))
	}
	return trail
}

func detailOf(t *testing.T, events []map[string]any, action, step string) map[string]any {
	t.Helper()
	for _, ev := range events {
		if ev["action"] == action && ev["step_id"] == step {
			detail, _ := ev["detail"].(map[string]any)
			return detail
		}
	}
	t.Fatalf("no %s for %s in %v", action, step, stepTrail(events))
	return nil
}

func TestRunWriteAuditsEachStepItRecords(t *testing.T) {
	f := newFixture(t, "")
	path := filepath.Join(f.ticket, "workflow", "run.yaml")
	code, out, errOut := f.do(false, "", "delegation", "allocate",
		"--run-id", auditRunID, "--step", "report", "--agent", "idev-reviewer", "--feature", "code-review")
	if code != exitOK {
		t.Fatalf("allocate: %s %s", out, errOut)
	}
	var allocated map[string]any
	must(t, json.Unmarshal([]byte(out), &allocated))

	sum := writeRun(t, f, path, runOpened, "")
	sum = writeRun(t, f, path, runReported, sum)
	writeRun(t, f, path, runSigned, sum)

	events := runEvents(t, f)
	want := []string{"run.started", "step.recorded report PASS", "step.recorded gate-report PASS", "run.completed"}
	if got := stepTrail(events); strings.Join(got, " | ") != strings.Join(want, " | ") {
		t.Fatalf("step trail\n got %q\nwant %q", got, want)
	}
	report := detailOf(t, events, "step.recorded", "report")
	for key, value := range map[string]any{
		"kind": "review.report", "agent": "idev-reviewer", "evidence": "docs/task/code-review/review.md",
		"lease_id": "01LEASEREPORT0000000000000", "delegation_id": allocated["id"],
	} {
		if report[key] != value {
			t.Fatalf("report detail %s = %v, want %v (%v)", key, report[key], value, report)
		}
	}
	gate := detailOf(t, events, "step.recorded", "gate-report")
	if gate["signed_by"] != "alice" || gate["assurance"] != "chat" {
		t.Fatalf("gate detail = %v", gate)
	}
	if _, ok := gate["sha256"]; !ok {
		t.Fatalf("a step event no longer binds the run.yaml it came from: %v", gate)
	}
}

func TestRunWriteAuditsNothingWhenNoStepChanged(t *testing.T) {
	f := newFixture(t, "")
	path := filepath.Join(f.ticket, "workflow", "run.yaml")
	sum := writeRun(t, f, path, runOpened, "")
	before := len(runEvents(t, f))
	writeRun(t, f, path, runOpened+"feedback:\n  status: pending\n", sum)
	if after := runEvents(t, f); len(after) != before {
		t.Fatalf("a write that changed no step added %v", stepTrail(after[before:]))
	}
}

func TestRunWriteAuditsAnAmendedStep(t *testing.T) {
	f := newFixture(t, "")
	path := filepath.Join(f.ticket, "workflow", "run.yaml")
	sum := writeRun(t, f, path, runOpened, "")
	sum = writeRun(t, f, path, runReported, sum)
	amended := strings.Replace(runReported, "at: '2026-10-23T16:58:44+08:00'\n  evidence: docs/task/code-review/review.md",
		"at: '2026-10-23T18:00:00+08:00'\n  evidence: docs/task/code-review/review-v2.md", 1)
	writeRun(t, f, path, amended, sum)
	detail := detailOf(t, runEvents(t, f), "step.amended", "report")
	if detail["evidence"] != "docs/task/code-review/review-v2.md" || detail["outcome"] != "PASS" {
		t.Fatalf("step.amended detail = %v", detail)
	}
}
