package kindreg_test

import (
	"os"
	"strings"
	"testing"

	"github.com/idev/internal/adapters/kindreg"
)

func TestTheEmbeddedRegistryLoads(t *testing.T) {
	r, err := kindreg.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if got := len(r.Kinds()); got != 29 {
		t.Errorf("%d kinds, want 29", got)
	}
	if got := len(r.Agents()); got != 5 {
		t.Errorf("%d agents, want 5", got)
	}
}

// The Go copy exists only because go:embed cannot reach a parent directory.
// If it drifts from registry/kinds.yaml, the Go side is validating against a
// table nobody else uses — which is the five-way duplication this whole
// mechanism removed, reintroduced quietly.
func TestTheEmbeddedCopyMatchesTheRegistry(t *testing.T) {
	source, err := os.ReadFile("../../../registry/kinds.yaml")
	if err != nil {
		t.Fatalf("read the registry: %v", err)
	}
	copied, err := os.ReadFile("kinds.yaml")
	if err != nil {
		t.Fatalf("read the embedded copy: %v", err)
	}
	// The copy carries a generated header; the body must be identical.
	body := string(copied)
	if i := strings.Index(body, "# The kind table."); i >= 0 {
		body = body[i:]
	}
	if body != string(source) {
		t.Error("internal/domain/kindreg/kinds.yaml is stale; run python3 scripts/gen-kinds.py")
	}
}

func TestLookups(t *testing.T) {
	r := kindreg.MustLoad()

	if got := r.AgentFor("deliver.code_pass"); got != "idev-coder" {
		t.Errorf("AgentFor(deliver.code_pass) = %q", got)
	}
	// The five the conductor keeps.
	for _, kind := range []string{
		"preflight.inputs", "human.gate", "shell.confirmed",
		"ui.clean_pass_loop", "ui.product_batch",
	} {
		if got := r.AgentFor(kind); got != kindreg.Conductor {
			t.Errorf("AgentFor(%s) = %q, want the conductor", kind, got)
		}
	}
	if got := r.AgentFor("no.such.kind"); got != kindreg.Conductor {
		t.Errorf("an unknown kind must fall back to the conductor, got %q", got)
	}
}

func TestIndependentVerificationIsDeclared(t *testing.T) {
	r := kindreg.MustLoad()
	// Invariant I-2: these kinds' PASS is not the writer's to declare.
	for _, kind := range []string{
		"deliver.code_pass", "review.fix", "frontend.lint_fix",
		"ui.playbook_sync", "git.replace_check",
	} {
		verifier, ok := r.NeedsIndependentVerification(kind)
		if !ok {
			t.Errorf("%s should need independent verification", kind)
			continue
		}
		if verifier == r.AgentFor(kind) {
			t.Errorf("%s is verified by its own writer %q", kind, verifier)
		}
	}
	// deliver.advance is signed off by a person, which is its independent
	// verification.
	if _, ok := r.NeedsIndependentVerification("deliver.advance"); ok {
		t.Error("deliver.advance should rely on the human gate, not a second agent")
	}
}

func TestAgentTraits(t *testing.T) {
	r := kindreg.MustLoad()

	if r.S0Agent() != "idev-coder" {
		t.Errorf("S0Agent = %q, want idev-coder", r.S0Agent())
	}
	// idev-deliver is out of FACTS: its output *is* the document, so "the
	// document says" would be circular.
	if r.IsFacts("idev-deliver") {
		t.Error("idev-deliver should not be a facts agent")
	}
	for _, a := range []string{"idev-coder", "idev-reviewer", "idev-verifier", "idev-ops"} {
		if !r.IsFacts(a) {
			t.Errorf("%s should be a facts agent", a)
		}
	}
	for _, a := range []string{"idev-coder", "idev-verifier", "idev-ops"} {
		if !r.IsBoost(a) {
			t.Errorf("%s should be a boost agent", a)
		}
	}
	if r.IsFacts("nobody") || r.IsBoost("nobody") {
		t.Error("an unknown agent has no traits")
	}
}

func TestForbiddenKinds(t *testing.T) {
	r := kindreg.MustLoad()
	for _, k := range []string{"auto.seal", "auto.accepted", "skip.signoff", "multi.module.load"} {
		if !r.Forbidden(k) {
			t.Errorf("%s should be forbidden", k)
		}
	}
	if r.Forbidden("deliver.code_pass") {
		t.Error("a normal kind was reported as forbidden")
	}
}

func TestLeaseAndGateLookups(t *testing.T) {
	r := kindreg.MustLoad()
	if got := r.LeaseFor("deliver.code_pass"); got != "write" {
		t.Errorf("LeaseFor(deliver.code_pass) = %q, want write", got)
	}
	if got := r.LeaseFor("verify.plan"); got != "verify" {
		t.Errorf("LeaseFor(verify.plan) = %q, want verify", got)
	}
	if got := r.LeaseFor("human.gate"); got != "none" {
		t.Errorf("LeaseFor(human.gate) = %q, want none", got)
	}
	if got := r.LeaseFor("no.such.kind"); got != "none" {
		t.Errorf("an unknown kind must take no lease, got %q", got)
	}
	if !r.IsGate("human.gate") {
		t.Error("human.gate should be a gate")
	}
	if r.IsGate("deliver.code_pass") {
		t.Error("a delegated kind is not a gate")
	}
}

// --- what Parse refuses ---------------------------------------------------

func TestParseRefusesAnIncoherentRegistry(t *testing.T) {
	cases := map[string]string{
		"wrong schema version": `
schema_version: 2
agents: {a: {role: x, readonly_breaks: y}}
kinds: {k: {page: p, agent: a}}
`,
		"an unknown key": `
schema_version: 1
agents: {a: {role: x, readonly_breaks: y}}
kinds: {k: {page: p, agent: a}}
surprise: true
`,
		"a kind naming an unknown agent": `
schema_version: 1
agents: {a: {role: x, readonly_breaks: y}}
kinds: {k: {page: p, agent: nobody}}
`,
		"a kind with no agent and no conductor": `
schema_version: 1
agents: {a: {role: x, readonly_breaks: y}}
kinds: {k: {page: p}}
`,
		"independent verification with no verifier": `
schema_version: 1
agents: {a: {role: x, readonly_breaks: y}}
kinds: {k: {page: p, agent: a, verify: independent}}
`,
		"a writer verifying itself": `
schema_version: 1
agents: {a: {role: x, readonly_breaks: y}}
kinds: {k: {page: p, agent: a, verify: independent, verifier: a}}
`,
		"two agents claiming s0": `
schema_version: 1
agents:
  a: {role: x, readonly_breaks: y, s0: true}
  b: {role: x, readonly_breaks: y, s0: true}
kinds: {k: {page: p, agent: a}}
`,
		"no kinds": `
schema_version: 1
agents: {a: {role: x, readonly_breaks: y}}
kinds: {}
`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := kindreg.Parse([]byte(body)); err == nil {
				t.Errorf("Parse accepted %s", name)
			}
		})
	}
}

func TestParseAcceptsAMinimalRegistry(t *testing.T) {
	r, err := kindreg.Parse([]byte(`
schema_version: 1
agents:
  idev-coder: {role: deliver, facts: true, boost: true, s0: true, readonly_breaks: 改代码}
forbidden: [auto.seal]
kinds:
  deliver.code_pass:
    page: deliver/SKILL.md
    agent: idev-coder
    lease: write
  human.gate:
    page: references/chat-confirm-signoff.md
    executor: conductor
    lease: none
    gate: true
`))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}
	if r.S0Agent() != "idev-coder" {
		t.Errorf("S0Agent = %q", r.S0Agent())
	}
	if !r.IsGate("human.gate") || r.AgentFor("human.gate") != kindreg.Conductor {
		t.Error("the gate kind was not read correctly")
	}
	if !r.Forbidden("auto.seal") {
		t.Error("the forbidden list was not read")
	}
}
