package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// E2.4 + E2.5: fencing from lease acquire must travel into run apply; a
// superseded token is refused with no state change. Python golden stays on
// its own lane (IDEV_ENGINE=python in test/golden/record.sh).
func TestRunCLIStartApplyAndStaleFencing(t *testing.T) {
	f := newFixture(t, "")
	runFile := filepath.Join(f.ticket, "workflow", "run.yaml")
	must(t, os.MkdirAll(filepath.Dir(runFile), 0o755))

	code, out, err := f.do(false, "",
		"run", "start",
		"--file", runFile,
		"--workflow", "lite-change",
		"--feature", "demo",
		"--step", "preflight:preflight.inputs",
		"--step", "code:deliver.code_pass",
	)
	if code != exitOK {
		t.Fatalf("start exit %d: %s", code, err)
	}
	var started map[string]string
	must(t, json.Unmarshal([]byte(out), &started))
	runID := started["run_id"]
	if runID == "" || started["truth"] != "sqlite" {
		t.Fatalf("start out = %v", started)
	}

	apply := func(args ...string) (int, string, string) {
		base := []string{"run", "apply", "--run-id", runID, "--file", runFile}
		return f.do(false, "", append(base, args...)...)
	}
	mustOK := func(args ...string) {
		t.Helper()
		code, _, err := apply(args...)
		if code != exitOK {
			t.Fatalf("apply %v exit %d: %s", args, code, err)
		}
	}
	mustOK("--event", "ConductorStepStarted", "--step", "preflight")
	mustOK("--event", "ConductorStepRecorded", "--step", "preflight",
		"--outcome", "PASS", "--evidence", "docs/p.md")
	mustOK("--event", "StepActivated", "--step", "code")
	mustOK("--event", "DelegationIssued", "--step", "code", "--agent", "idev-coder")

	code, out, err = f.do(false, "",
		"lease", "acquire",
		"--run", runFile, "--step", "code",
		"--write-path", "src/**",
	)
	if code != exitOK {
		t.Fatalf("acquire exit %d: %s\n%s", code, err, out)
	}
	var first leaseOut
	must(t, json.Unmarshal([]byte(out), &first))
	if first.Fencing == 0 {
		t.Fatal("acquire returned no fencing")
	}

	code, _, err = f.do(false, "",
		"lease", "release", first.LeaseID, "--token", first.Token,
	)
	if code != exitOK {
		t.Fatalf("release exit %d: %s", code, err)
	}
	code, out, err = f.do(false, "",
		"lease", "acquire",
		"--run", runFile, "--step", "code",
		"--write-path", "src/**",
	)
	if code != exitOK {
		t.Fatalf("second acquire exit %d: %s", code, err)
	}
	var second leaseOut
	must(t, json.Unmarshal([]byte(out), &second))
	if second.Fencing <= first.Fencing {
		t.Fatalf("fencing %d → %d", first.Fencing, second.Fencing)
	}

	code, _, err = apply(
		"--event", "DelegationReturned", "--step", "code",
		"--agent", "idev-coder",
		"--fencing", strconv.FormatUint(first.Fencing, 10),
	)
	if code == exitOK {
		t.Fatal("stale fencing was accepted via CLI")
	}
	if !strings.Contains(err, "fencing") && !strings.Contains(err, "superseded") {
		t.Fatalf("refuse message = %q", err)
	}

	code, _, err = apply(
		"--event", "DelegationReturned", "--step", "code",
		"--agent", "idev-coder",
		"--fencing", strconv.FormatUint(second.Fencing, 10),
	)
	if code != exitOK {
		t.Fatalf("live fencing refused: %s", err)
	}
}

// E3.1: after Accept moves code to verifying, the projected YAML lets the
// registry verifier take a verify lease; the writer cannot.
func TestIndependentVerifyLeaseFromCLIProjection(t *testing.T) {
	f := newFixture(t, "")
	runFile := filepath.Join(f.ticket, "workflow", "run.yaml")
	must(t, os.MkdirAll(filepath.Dir(runFile), 0o755))
	ticketRel := "tickets/demo"

	code, out, err := f.do(false, "",
		"run", "start", "--file", runFile,
		"--workflow", "lite-change", "--feature", "demo",
		"--step", "preflight:preflight.inputs",
		"--step", "code:deliver.code_pass",
	)
	if code != exitOK {
		t.Fatalf("start: %s", err)
	}
	var started map[string]string
	must(t, json.Unmarshal([]byte(out), &started))
	runID := started["run_id"]
	apply := func(args ...string) {
		t.Helper()
		base := []string{"run", "apply", "--run-id", runID, "--file", runFile}
		code, _, e := f.do(false, "", append(base, args...)...)
		if code != exitOK {
			t.Fatalf("apply %v: %s", args, e)
		}
	}
	apply("--event", "ConductorStepStarted", "--step", "preflight")
	apply("--event", "ConductorStepRecorded", "--step", "preflight",
		"--outcome", "PASS", "--evidence", "docs/p.md")
	apply("--event", "StepActivated", "--step", "code")
	apply("--event", "DelegationIssued", "--step", "code", "--agent", "idev-coder")

	code, out, err = f.do(false, "",
		"lease", "acquire", "--run", runFile, "--step", "code",
		"--agent", "idev-coder", "--write-path", "src/**",
	)
	if code != exitOK {
		t.Fatalf("write acquire: %s", err)
	}
	var writer leaseOut
	must(t, json.Unmarshal([]byte(out), &writer))
	apply("--event", "DelegationReturned", "--step", "code",
		"--agent", "idev-coder", "--fencing", strconv.FormatUint(writer.Fencing, 10))
	apply("--event", "DelegationAccepted", "--step", "code",
		"--outcome", "PASS", "--evidence", "code/review.md")

	raw, readErr := os.ReadFile(runFile)
	must(t, readErr)
	if !strings.Contains(string(raw), "status: verifying") {
		t.Fatalf("export missing verifying:\n%s", raw)
	}

	code, _, err = f.do(false, "",
		"lease", "acquire", "--run", runFile, "--step", "code",
		"--agent", "idev-coder", "--purpose", "verify",
		"--ticket-dir", ticketRel, "--write-path", ticketRel+"/**",
	)
	if code == exitOK {
		t.Fatal("writer took the independent verify lease")
	}
	if !strings.Contains(err, "idev-reviewer verifies") && !strings.Contains(err, "not idev-coder") {
		t.Fatalf("writer refuse = %q", err)
	}

	code, out, err = f.do(false, "",
		"lease", "acquire", "--run", runFile, "--step", "code",
		"--agent", "idev-reviewer", "--purpose", "verify",
		"--ticket-dir", ticketRel, "--write-path", ticketRel+"/**",
	)
	if code != exitOK {
		t.Fatalf("verifier acquire: %s", err)
	}
	var vheld leaseOut
	must(t, json.Unmarshal([]byte(out), &vheld))
	if vheld.Agent != "idev-reviewer" || vheld.Fencing == 0 {
		t.Fatalf("verify lease %+v", vheld)
	}
}
