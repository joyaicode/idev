package runyaml_test

import (
	"testing"

	"github.com/idev/internal/adapters/runyaml"
	"github.com/idev/internal/domain/run"
	"go.yaml.in/yaml/v3"
)

func TestExportKeepsVerifyingDistinctFromDelegated(t *testing.T) {
	body, err := runyaml.Export(nil, run.Run{
		ID: "R1", WorkflowID: "lite-change", Feature: "demo",
		Steps: []run.Step{
			{ID: "code", Kind: "deliver.code_pass", State: run.StepVerifying, Writer: "idev-coder"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(body, &doc); err != nil {
		t.Fatal(err)
	}
	step := doc["steps"].([]any)[0].(map[string]any)
	if step["status"] != "verifying" {
		t.Fatalf("status = %v, want verifying", step["status"])
	}
	del := step["delegated"].(map[string]any)
	if del["agent"] != "idev-coder" {
		t.Fatalf("delegated = %v", del)
	}
}

func TestExportOverlaysDomainOntoExistingYAML(t *testing.T) {
	existing := []byte(`schema_version: 1
run_id: R1
workflow_id: lite-change
feature: demo
status: running
params:
  feature: demo
steps:
  - id: preflight
    kind: preflight.inputs
  - id: plan
    kind: verify.plan
    writes: [verify/plan.yaml]
`)
	body, err := runyaml.Export(existing, run.Run{
		ID: "R1", WorkflowID: "lite-change", Feature: "demo",
		Steps: []run.Step{
			{ID: "preflight", Kind: "preflight.inputs", State: run.StepPASS, Evidence: "docs/p.md"},
			{ID: "plan", Kind: "verify.plan", State: run.StepReady, Writes: []string{"verify/plan.yaml"}},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(body, &doc); err != nil {
		t.Fatal(err)
	}
	if doc["params"].(map[string]any)["feature"] != "demo" {
		t.Fatalf("params lost: %v", doc["params"])
	}
	steps := doc["steps"].([]any)
	pre := steps[0].(map[string]any)
	if pre["status"] != "PASS" || pre["evidence"] != "docs/p.md" {
		t.Fatalf("preflight = %v", pre)
	}
	plan := steps[1].(map[string]any)
	if _, ok := plan["status"]; ok {
		t.Fatalf("open plan should omit status, got %v", plan)
	}
}
