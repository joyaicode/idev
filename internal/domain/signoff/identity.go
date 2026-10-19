package signoff

import (
	"regexp"
	"strings"

	"golang.org/x/text/unicode/norm"
)

// Names that are never a person.
//
// In idevd this is a backstop rather than the mechanism: `by` is not supplied
// by the caller at all, it is the handle of the authenticated principal, and
// the domain invariant is that the principal's kind is human (design §10.2,
// threat T1). The list still matters for two things — importing historical
// run.yaml files, and keeping byte-parity with the Python implementation
// while both exist.
//
// The `idev-` prefix and the agent/assistant substrings cover the five kernel
// agents and any added later; the words below are for models that sign under
// their own product name.
var agentWords = map[string]bool{
	// the original four
	"agent": true, "ai": true, "cursor": true, "assistant": true,
	// models
	"claude": true, "gpt": true, "chatgpt": true, "codex": true,
	"gemini": true, "grok": true, "copilot": true, "composer": true,
	"sonnet": true, "opus": true, "deepseek": true, "glm": true,
	"qwen": true, "kimi": true,
	// roles, which are not people
	"llm": true, "bot": true, "model": true, "subagent": true,
	"conductor": true, "system": true, "root": true, "human": true,
}

var (
	idevPrefix = regexp.MustCompile(`^idev[-_]`)
	// nameTokens splits a name into [a-z0-9]+ runs, so "glm-4.6" and "Grok
	// Bot" hit the word set token by token rather than only whole.
	nameTokens = regexp.MustCompile(`[a-z0-9]+`)
)

// Identity is the signing policy for one workspace.
//
// Whitelist is the configured set of people (lowercased). An empty Whitelist
// means blacklist-only: valid, documented, and weaker — it stops agents and
// models from signing but not a plausible invented name. Callers that care
// report Warning alongside the verdict.
type Identity struct {
	Whitelist map[string]bool
	// Agents from registry/kinds.yaml, so a newly registered agent is
	// refused without editing this file.
	Agents []string
}

// BlacklistOnly is the policy when no people.yaml is configured.
func BlacklistOnly(agents ...string) Identity {
	return Identity{Agents: agents}
}

// Warning explains why the whitelist is not in force, or "" when it is.
func (id Identity) Warning() string {
	if len(id.Whitelist) == 0 {
		return "people.yaml missing; blacklist-only"
	}
	return ""
}

// IsHuman reports whether `by` may sign.
//
// Two gates, and the order matters: the blacklist always applies, so listing
// an agent in people.yaml does not make it a person.
func (id Identity) IsHuman(by string) bool {
	name := strings.TrimSpace(by)
	if name == "" {
		return false
	}
	low := strings.ToLower(strings.TrimSpace(norm.NFKC.String(name)))
	if namesAnAgent(low) {
		return false
	}
	if idevPrefix.MatchString(low) {
		return false
	}
	if strings.Contains(low, "agent") || strings.Contains(low, "assistant") {
		return false
	}
	for _, a := range id.Agents {
		if strings.EqualFold(a, low) {
			return false
		}
	}
	if len(id.Whitelist) > 0 {
		return id.Whitelist[low]
	}
	return true
}

// namesAnAgent reports whether the lowercased name names an agent or a
// model, whole or in any one of its word tokens — "glm-4.6" and "Grok Bot"
// hit the set token by token rather than only whole.
func namesAnAgent(low string) bool {
	if agentWords[low] {
		return true
	}
	for _, tok := range nameTokens.FindAllString(low, -1) {
		if agentWords[tok] {
			return true
		}
	}
	return false
}
