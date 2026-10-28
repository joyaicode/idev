package runyaml_test

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/idev/internal/adapters/runyaml"
	"go.yaml.in/yaml/v3"
)

func TestRecordStampsOneStepUnderLock(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "run.yaml")
	initial := []byte(`schema_version: 1
run_id: 01TESTRECORD000000000000000
workflow_id: lite-change
status: running
steps:
  - id: plan
    kind: verify.plan
  - id: gate-plan
    kind: human.gate
`)
	if err := os.WriteFile(path, initial, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := runyaml.Record(path, "plan", "PASS", "verify/plan.yaml", ""); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	steps := doc["steps"].([]any)
	plan := steps[0].(map[string]any)
	if plan["status"] != "PASS" {
		t.Fatalf("plan status = %v, want PASS", plan["status"])
	}
	if plan["evidence"] != "verify/plan.yaml" {
		t.Fatalf("evidence = %v", plan["evidence"])
	}
	if plan["at"] == nil || plan["at"] == "" {
		t.Fatal("missing at")
	}
	gate := steps[1].(map[string]any)
	if _, ok := gate["status"]; ok {
		t.Fatalf("gate should stay unstamped, got %v", gate)
	}
}

func TestRecordUnknownStep(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "run.yaml")
	if err := os.WriteFile(path, []byte("steps:\n  - {id: a}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	err := runyaml.Record(path, "missing", "PASS", "", "")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestWriteRefusesAStaleExpect(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "run.yaml")
	if err := os.WriteFile(path, []byte("status: running\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	err := runyaml.Write(path, []byte("status: done\n"), "deadbeef")
	if err == nil {
		t.Fatal("expected stale error")
	}
	var stale *runyaml.ErrStale
	if !errors.As(err, &stale) {
		t.Fatalf("got %T %v, want ErrStale", err, err)
	}
	got, err := runyaml.SHA256Hex(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := runyaml.Write(path, []byte("status: done\n"), got); err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(path)
	if string(raw) != "status: done\n" {
		t.Fatalf("body = %q", raw)
	}
}

func TestWriteEmptyExpectSerializesCreators(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "run.yaml")
	if err := runyaml.Write(path, []byte("run_id: first\n"), ""); err != nil {
		t.Fatal(err)
	}
	err := runyaml.Write(path, []byte("run_id: second\n"), "")
	if err == nil {
		t.Fatal("second empty expect must be stale after the first write")
	}
	var stale *runyaml.ErrStale
	if !errors.As(err, &stale) {
		t.Fatalf("got %T %v, want ErrStale", err, err)
	}
	raw, _ := os.ReadFile(path)
	if string(raw) != "run_id: first\n" {
		t.Fatalf("body = %q", raw)
	}
}
