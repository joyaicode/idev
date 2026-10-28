package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestBaselineSealConflictAndVerifyDrift(t *testing.T) {
	f := newFixture(t, "alice")
	ticket := f.ticket
	must(t, os.WriteFile(filepath.Join(ticket, "baseline.yaml"), []byte(""+
		"revision: 1\n"+
		"goal: ship the fingerprint\n"+
		"non_goal: rewrite the world\n"+
		"items:\n"+
		"  - id: I1\n"+
		"    must: digests hold\n"+
		"boundaries: []\n"+
		"details: {}\n"+
		"sealed: false\n"), 0o644))

	r := f.ask("--type", "sealed", "--risk", "P1", "--revision", "1", "--root", ticket,
		"--subject", "baseline.yaml",
		"--will-write", "baseline sealed", "--proof", "grill frontier empty")
	code, _, errOut := f.do(true, r.Short+"\n", "gate", "approve", r.GateID, "--quote", "确认")
	if code != exitOK {
		t.Fatalf("approve: %s", errOut)
	}

	code, out, errOut := f.do(false, "", "baseline", "seal",
		"--feature", "demo", "--gate", r.GateID, "--ticket", ticket, "--by", "alice")
	if code != exitOK {
		t.Fatalf("seal: code=%d out=%s err=%s", code, out, errOut)
	}
	var sealed map[string]any
	must(t, json.Unmarshal([]byte(out), &sealed))
	if sealed["status"] != "sealed" {
		t.Fatalf("seal out = %v", sealed)
	}

	must(t, os.WriteFile(filepath.Join(ticket, "baseline.yaml"), []byte(""+
		"revision: 2\n"+
		"goal: changed meaning\n"+
		"non_goal: rewrite the world\n"+
		"items:\n"+
		"  - id: I1\n"+
		"    must: digests hold\n"+
		"boundaries: []\n"+
		"details: {}\n"+
		"sealed: false\n"), 0o644))
	r2 := f.ask("--type", "sealed", "--risk", "P1", "--revision", "2", "--root", ticket,
		"--subject", "baseline.yaml",
		"--will-write", "baseline sealed", "--proof", "grill frontier empty")
	code, _, errOut = f.do(true, r2.Short+"\n", "gate", "approve", r2.GateID, "--quote", "确认")
	if code != exitOK {
		t.Fatalf("approve2: %s", errOut)
	}
	code, _, errOut = f.do(false, "", "baseline", "seal",
		"--feature", "demo", "--gate", r2.GateID, "--ticket", ticket, "--by", "alice",
		"--project-yaml=false")
	if code == exitOK {
		t.Fatal("second seal should conflict")
	}
	if !strings.Contains(errOut, "sealed") && !strings.Contains(errOut, "conflict") {
		t.Fatalf("want sealed conflict, got %s", errOut)
	}

	// Restore sealed content then tamper for drift.
	intact := "" +
		"revision: 1\n" +
		"goal: ship the fingerprint\n" +
		"non_goal: rewrite the world\n" +
		"items:\n" +
		"  - id: I1\n" +
		"    must: digests hold\n" +
		"boundaries: []\n" +
		"details: {}\n" +
		"sealed: true\n"
	must(t, os.WriteFile(filepath.Join(ticket, "baseline.yaml"), []byte(intact), 0o644))
	code, out, errOut = f.do(false, "", "baseline", "verify",
		"--feature", "demo", "--ticket", ticket, "--block-run=false")
	if code != exitOK {
		t.Fatalf("intact verify: %s %s", out, errOut)
	}

	drifted := strings.Replace(intact, "goal: ship the fingerprint", "goal: tampered", 1)
	must(t, os.WriteFile(filepath.Join(ticket, "baseline.yaml"), []byte(drifted), 0o644))
	code, out, errOut = f.do(false, "", "baseline", "verify",
		"--feature", "demo", "--ticket", ticket, "--block-run=false")
	if code == exitOK {
		t.Fatal("verify should refuse on drift")
	}
	joined := out + errOut
	if !strings.Contains(joined, "baseline-drift") {
		t.Fatalf("want baseline-drift, got %s", joined)
	}
}
