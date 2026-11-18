package loop

import (
	"encoding/json"
	"strings"

	"github.com/idev/internal/agent/provider"
)

// recoverContentToolCall is the documented degradation path for local
// models that answer a tool-bearing turn with the tool call as plain text
// (qwen2.5 over ollama was caught doing exactly this on the first real
// smoke: `{"name": "write", "arguments": {...}}` in content, no
// tool_calls structure). The provider's capabilities flag says "tools
// supported"; the model's behavior says otherwise.
//
// The sniff is deliberately conservative — both shapes, whole-message
// only, no markdown stripping. A model that wraps its JSON in prose or a
// code fence is notRecovered: the nudge path (completeWithRetry) is the
// next resort, and after that the caller sees plain text. False positives
// (a tool call recovered where none was meant) are possible only when the
// model emits a bare JSON object naming a registered tool with an
// `arguments`/`input` key — which is indistinguishable from intent.
type contentToolCall struct {
	Name      string          `json:"name"`
	Tool      string          `json:"tool"`
	Arguments json.RawMessage `json:"arguments"`
	Input     json.RawMessage `json:"input"`
}

// recoverContentToolCall returns a ToolCall when the content is, whole and
// alone, a JSON object naming a tool this loop knows. Empty string
// otherwise. It never runs on multi-line prose with JSON buried inside.
func (l *Loop) recoverContentToolCall(content string) (provider.ToolCall, bool) {
	trimmed := strings.TrimSpace(content)
	if trimmed == "" || trimmed[0] != '{' || trimmed[len(trimmed)-1] != '}' {
		return provider.ToolCall{}, false
	}
	var parsed contentToolCall
	if err := json.Unmarshal([]byte(trimmed), &parsed); err != nil {
		return provider.ToolCall{}, false
	}
	name := parsed.Name
	if name == "" {
		name = parsed.Tool
	}
	if name == "" {
		return provider.ToolCall{}, false
	}
	if _, ok := l.Tools[name]; !ok {
		return provider.ToolCall{}, false
	}
	args := parsed.Arguments
	if len(args) == 0 {
		args = parsed.Input
	}
	if len(args) == 0 {
		args = json.RawMessage("{}")
	}
	if !json.Valid(args) {
		return provider.ToolCall{}, false
	}
	return provider.ToolCall{ID: "content-recovered", Name: name, ArgsJSON: args}, true
}
