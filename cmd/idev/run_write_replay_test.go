package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"go.yaml.in/yaml/v3"
)

// kafkaState is the kafka code-review run.yaml as it stood when its first
// `recorded` steps had been recorded: later steps lose their record, and
// steps not yet reached lose their delegation too.
func kafkaState(t *testing.T, raw []byte, recorded int) (string, map[string]any) {
	t.Helper()
	var doc map[string]any
	must(t, yaml.Unmarshal(raw, &doc))
	steps, _ := doc["steps"].([]any)
	for j, s := range steps {
		step := s.(map[string]any)
		if j >= recorded {
			for _, key := range []string{"status", "at", "evidence", "note", "signoff", "verification", "auto", "accepted_findings"} {
				delete(step, key)
			}
		}
		if j > recorded {
			for _, key := range []string{"delegated", "lease", "verify_lease"} {
				delete(step, key)
			}
		}
	}
	doc["status"] = "running"
	if recorded == len(steps) {
		doc["status"] = "done"
	}
	out, err := yaml.Marshal(doc)
	must(t, err)
	return string(out), steps[max(recorded-1, 0)].(map[string]any)
}

func TestReplayingKafkaCodeReviewListsEveryStep(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("..", "..", "test", "fixtures", "runs", "kafka-code-review.yaml"))
	must(t, err)
	var head struct {
		RunID string `yaml:"run_id"`
		Steps []any  `yaml:"steps"`
	}
	must(t, yaml.Unmarshal(raw, &head))

	f := newFixture(t, "")
	path := filepath.Join(f.ticket, "workflow", "run.yaml")
	body, _ := kafkaState(t, raw, 0)
	sum := writeRun(t, f, path, body, "")
	issued := map[string]string{}
	for i := 1; i <= len(head.Steps); i++ {
		body, step := kafkaState(t, raw, i)
		id, _ := step["id"].(string)
		if delegated, ok := step["delegated"].(map[string]any); ok {
			code, out, errOut := f.do(false, "", "delegation", "allocate", "--run-id", head.RunID,
				"--step", id, "--agent", delegated["agent"].(string), "--feature", "code-review")
			if code != exitOK {
				t.Fatalf("allocate %s: %s %s", id, out, errOut)
			}
			var got map[string]any
			must(t, json.Unmarshal([]byte(out), &got))
			issued[id] = got["id"].(string)
		}
		if verified, ok := step["verification"].(map[string]any); ok {
			if code, out, errOut := f.do(false, "", "delegation", "verify", "--id", issued[id],
				"--verifier", verified["by"].(string), "--verdict", "PASS", "--evidence", verified["evidence"].(string)); code != exitOK {
				t.Fatalf("verify %s: %s %s", id, out, errOut)
			}
		}
		sum = writeRun(t, f, path, body, sum)
	}

	code, out, errOut := f.do(false, "", "audit", "export", "--run", head.RunID)
	if code != exitOK {
		t.Fatalf("export: %s", errOut)
	}
	var trail, signed []string
	count := map[string]int{}
	for _, line := range strings.Split(strings.TrimSpace(out), "\n") {
		var ev map[string]any
		must(t, json.Unmarshal([]byte(line), &ev))
		action, _ := ev["action"].(string)
		step, _ := ev["step_id"].(string)
		detail, _ := ev["detail"].(map[string]any)
		count[action]++
		switch {
		case strings.HasPrefix(action, "step."):
			outcome, _ := detail["outcome"].(string)
			trail = append(trail, strings.TrimSpace(step+" "+outcome))
			if by, _ := detail["signed_by"].(string); by != "" {
				signed = append(signed, step+" by "+by)
			}
			if want := issued[step]; want != "" && detail["delegation_id"] != want {
				t.Fatalf("%s names delegation %v, want %s", step, detail["delegation_id"], want)
			}
		case action == "delegation.issued" && issued[step] == "":
			t.Fatalf("delegation.issued for %s was never allocated", step)
		}
	}
	if got, want := strings.Join(trail, ", "), "report PASS, gate-report PASS, plan PASS, gate-plan PASS, fix PASS, run PASS"; got != want {
		t.Fatalf("step events\n got %s\nwant %s", got, want)
	}
	if got, want := strings.Join(signed, ", "), "gate-report by wangwei794, gate-plan by wangwei794"; got != want {
		t.Fatalf("signoffs\n got %s\nwant %s", got, want)
	}
	if count["delegation.issued"] != 4 || count["verification.recorded"] != 1 ||
		count["run.started"] != 1 || count["run.completed"] != 1 {
		t.Fatalf("delegations and run events: %v", count)
	}
}
