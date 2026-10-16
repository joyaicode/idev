// Package kindreg answers questions about kinds and agents from
// registry/kinds.yaml.
//
// The registry is the one source (invariant I-7); this is the Go side's
// reader for it. Embedded rather than read from disk so a binary cannot
// disagree with the registry it was built from — the same reason the JSON
// Schemas are embedded.
package kindreg

import (
	"bytes"
	_ "embed"
	"fmt"
	"sort"

	"go.yaml.in/yaml/v3"
)

// registryYAML is registry/kinds.yaml, copied here by scripts/gen-kinds.py
// because an embed directive cannot reach a parent directory. The copy is
// generated and `gen-kinds.py --check` keeps it in step, so it is not a
// second source of truth.
//
//go:embed kinds.yaml
var registryYAML []byte

// Agent describes one subagent.
type Agent struct {
	Name           string
	Role           string `yaml:"role"`
	Facts          bool   `yaml:"facts"`
	Boost          bool   `yaml:"boost"`
	S0             bool   `yaml:"s0"`
	ReadonlyBreaks string `yaml:"readonly_breaks"`
	Stage          string `yaml:"stage"`
	RoleLabel      string `yaml:"role_label"`
}

// Kind describes one step kind.
type Kind struct {
	Name               string
	Page               string   `yaml:"page"`
	Lands              string   `yaml:"lands"`
	Note               string   `yaml:"note"`
	Executor           string   `yaml:"executor"`
	Agent              string   `yaml:"agent"`
	Lease              string   `yaml:"lease"`
	Verify             string   `yaml:"verify"`
	Verifier           string   `yaml:"verifier"`
	CommandKey         string   `yaml:"command_key"`
	Requires           []string `yaml:"requires"`
	RequiresWith       []string `yaml:"requires_with"`
	RequiresGateBefore bool     `yaml:"requires_gate_before"`
	Gate               bool     `yaml:"gate"`
	Legacy             bool     `yaml:"legacy"`
	// WhyKept records why a kind stays with the conductor. Prose for a
	// reader; decoded rather than ignored because the decoder is strict,
	// and a field that exists in the registry and not here would otherwise
	// mean the Go side silently reads a different table.
	WhyKept string `yaml:"why_kept"`
}

// conductorLabels are the stage and role columns for the conductor's own
// rows in the generated prose table. Decoded so strict parsing accepts the
// registry; not otherwise used on this side.
type conductorLabels struct {
	Stage     string `yaml:"stage"`
	RoleLabel string `yaml:"role_label"`
}

// Conductor is the executor value for steps the conductor keeps.
const Conductor = "-"

type file struct {
	SchemaVersion int              `yaml:"schema_version"`
	Agents        map[string]Agent `yaml:"agents"`
	Conductor     conductorLabels  `yaml:"conductor"`
	Forbidden     []string         `yaml:"forbidden"`
	Kinds         map[string]Kind  `yaml:"kinds"`
}

// Registry is the parsed table.
type Registry struct {
	agents    map[string]Agent
	kinds     map[string]Kind
	forbidden map[string]bool
	s0Agent   string
}

var embedded *Registry

// Load parses the embedded registry. The result is cached: it cannot change
// at runtime.
func Load() (*Registry, error) {
	if embedded != nil {
		return embedded, nil
	}
	r, err := Parse(registryYAML)
	if err != nil {
		return nil, err
	}
	embedded = r
	return r, nil
}

// MustLoad is Load for callers that cannot proceed without it. A registry
// that does not parse is a broken build, not a runtime condition.
func MustLoad() *Registry {
	r, err := Load()
	if err != nil {
		panic(err)
	}
	return r
}

// Parse reads a registry from bytes, for tests and for `idev assets`.
func Parse(raw []byte) (*Registry, error) {
	var f file
	dec := yaml.NewDecoder(bytes.NewReader(raw))
	// Strict: an unknown key in the one source of truth is a mistake worth
	// failing on, not a field to ignore.
	dec.KnownFields(true)
	if err := dec.Decode(&f); err != nil {
		return nil, fmt.Errorf("kindreg: %w", err)
	}
	if f.SchemaVersion != 1 {
		return nil, fmt.Errorf("kindreg: schema_version %d, want 1", f.SchemaVersion)
	}
	if len(f.Kinds) == 0 || len(f.Agents) == 0 {
		return nil, fmt.Errorf("kindreg: registry has no kinds or no agents")
	}

	r := &Registry{
		agents:    make(map[string]Agent, len(f.Agents)),
		kinds:     make(map[string]Kind, len(f.Kinds)),
		forbidden: make(map[string]bool, len(f.Forbidden)),
	}
	for name, a := range f.Agents {
		a.Name = name
		r.agents[name] = a
		if a.S0 {
			if r.s0Agent != "" {
				return nil, fmt.Errorf("kindreg: two agents claim s0: %s and %s", r.s0Agent, name)
			}
			r.s0Agent = name
		}
	}
	for _, k := range f.Forbidden {
		r.forbidden[k] = true
	}
	for name, k := range f.Kinds {
		k.Name = name
		if k.Executor != "conductor" && k.Agent == "" {
			return nil, fmt.Errorf("kindreg: kind %q has no agent and is not kept by the conductor", name)
		}
		if k.Agent != "" {
			if _, ok := r.agents[k.Agent]; !ok {
				return nil, fmt.Errorf("kindreg: kind %q names unknown agent %q", name, k.Agent)
			}
		}
		if k.Verify == "independent" {
			if k.Verifier == "" {
				return nil, fmt.Errorf("kindreg: kind %q needs independent verification but names no verifier", name)
			}
			if k.Verifier == k.Agent {
				return nil, fmt.Errorf(
					"kindreg: kind %q lists %q as both writer and verifier; that is not independent",
					name, k.Agent)
			}
		}
		r.kinds[name] = k
	}
	return r, nil
}

// Kind returns one kind.
func (r *Registry) Kind(name string) (Kind, bool) {
	k, ok := r.kinds[name]
	return k, ok
}

// Agent returns one agent.
func (r *Registry) Agent(name string) (Agent, bool) {
	a, ok := r.agents[name]
	return a, ok
}

// AgentFor returns the executor of a kind: an agent handle, or Conductor.
func (r *Registry) AgentFor(kind string) string {
	k, ok := r.kinds[kind]
	if !ok || k.Executor == "conductor" {
		return Conductor
	}
	return k.Agent
}

// IsFacts reports whether an agent must declare where its facts came from.
func (r *Registry) IsFacts(agent string) bool {
	a, ok := r.agents[agent]
	return ok && a.Facts
}

// IsBoost reports whether an agent reads convention pages from the kernel,
// and therefore needs idev_root in its brief.
func (r *Registry) IsBoost(agent string) bool {
	a, ok := r.agents[agent]
	return ok && a.Boost
}

// S0Agent is the agent coding.md §0 applies to.
func (r *Registry) S0Agent() string { return r.s0Agent }

// Forbidden reports whether a kind is one of the refused shapes.
func (r *Registry) Forbidden(kind string) bool { return r.forbidden[kind] }

// NeedsIndependentVerification reports whether a kind's PASS requires a
// second agent, and who that is.
func (r *Registry) NeedsIndependentVerification(kind string) (string, bool) {
	k, ok := r.kinds[kind]
	if !ok || k.Verify != "independent" {
		return "", false
	}
	return k.Verifier, true
}

// LeaseFor returns the lease purpose a kind needs.
func (r *Registry) LeaseFor(kind string) string {
	k, ok := r.kinds[kind]
	if !ok || k.Lease == "" {
		return "none"
	}
	return k.Lease
}

// IsGate reports whether a kind is the human gate.
func (r *Registry) IsGate(kind string) bool {
	k, ok := r.kinds[kind]
	return ok && k.Gate
}

// Kinds lists every registered kind, sorted.
func (r *Registry) Kinds() []string {
	out := make([]string, 0, len(r.kinds))
	for k := range r.kinds {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// Agents lists every registered agent, sorted.
func (r *Registry) Agents() []string {
	out := make([]string, 0, len(r.agents))
	for a := range r.agents {
		out = append(out, a)
	}
	sort.Strings(out)
	return out
}
