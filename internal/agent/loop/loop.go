// Package loop is the ideva agent loop: messages → provider → tool calls →
// tool results → messages, until the model answers with plain text.
//
// The shape is the one every mainstream CLI converged on (Claude Code's
// agent loop, Codex core, Gemini core): a turn is one model response plus
// the tool calls it asked for, executed and fed back; the loop ends on a
// response with no tool calls. Guardrails are turn-count and context
// budget — both counters, neither a score, which is the kernel's rule.
package loop

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/idev/internal/agent/provider"
)

// Tool is what the loop executes. One interface, JSON-schema shaped, the
// same three things every registry asks: a name, a schema for the model, a
// handler for the host. ReadOnlyHint lets the loop run independent
// read-only tools concurrently instead of serially — the turn-budget
// lesson from the Python side, in the host where it can actually be
// enforced.
type Tool interface {
	Name() string
	Description() string
	ParametersJSON() json.RawMessage
	ReadOnly() bool
	Execute(ctx context.Context, args json.RawMessage) (string, error)
}

// Loop binds a provider, a tool set, and a transcript sink.
type Loop struct {
	Provider provider.Provider
	Tools    map[string]Tool
	// OnDelta, when set, receives streaming text deltas for rendering.
	OnDelta func(provider.Delta)
	// MaxTurns is the hard stop. Zero means 40 — a number big enough for a
	// real task, small enough that a stuck model cannot run all night.
	MaxTurns int
	// MaxHistoryChars trims the oldest non-system messages before each
	// provider call; 0 disables trimming. A counter, not a token estimate:
	// chat-completions endpoints do not advertise their window and a
	// guess at tokens would be a guess.
	MaxHistoryChars int
}

// Result is the loop's terminal answer.
type Result struct {
	Text          string
	TurnsUsed     int
	ToolCallsMade int
}

// Run drives the conversation to its natural end: one assistant message
// with no tool calls. History is owned by the caller (the session layer);
// the loop appends every exchange to it so the transcript and the model
// context never diverge.
func (l *Loop) Run(ctx context.Context, history *[]provider.Message, input string) (Result, error) {
	if l.MaxTurns <= 0 {
		l.MaxTurns = 40
	}
	*history = append(*history, provider.Message{Role: provider.RoleUser, Content: input})
	tools := make([]provider.ToolSpec, 0, len(l.Tools))
	for _, t := range l.Tools {
		tools = append(tools, provider.ToolSpec{
			Name: t.Name(), Description: t.Description(), ParametersJSON: t.ParametersJSON(),
		})
	}

	res := Result{}
	for turn := 0; turn < l.MaxTurns; turn++ {
		res.TurnsUsed = turn + 1
		window := *history
		if l.MaxHistoryChars > 0 {
			window = trimWindow(*history, l.MaxHistoryChars)
		}
		answer, err := l.completeWithRetry(ctx, window, tools)
		if err != nil {
			return res, err
		}
		*history = append(*history, provider.Message{
			Role: provider.RoleAssistant, Content: answer.Content, ToolCalls: answer.ToolCalls,
		})
		if len(answer.ToolCalls) == 0 {
			// Degradation path: a local model may have put its one tool
			// call in plain content instead of the tool_calls structure.
			// recover.go says when that counts.
			if tc, ok := l.recoverContentToolCall(answer.Content); ok {
				answer.ToolCalls = []provider.ToolCall{tc}
				(*history)[len(*history)-1].ToolCalls = answer.ToolCalls
				(*history)[len(*history)-1].Content = ""
			} else {
				res.Text = answer.Content
				return res, nil
			}
		}
		// Execute the asked-for tools. Read-only tools with no data
		// dependency between them run concurrently; anything that writes
		// runs alone, in order — the single-writer rule, host-side.
		if err := l.runTurn(ctx, answer.ToolCalls, history); err != nil {
			return res, err
		}
		res.ToolCallsMade += len(answer.ToolCalls)
	}
	return res, fmt.Errorf("loop: stopped after %d turns with tools still pending (MaxTurns)", l.MaxTurns)
}

// runTurn executes one turn's tool calls and appends the results.
func (l *Loop) runTurn(ctx context.Context, calls []provider.ToolCall, history *[]provider.Message) error {
	results := make([]string, len(calls))
	errs := make([]error, len(calls))
	// Phase 1: concurrent read-only batch.
	idx := make([]int, 0, len(calls))
	for i, c := range calls {
		if t, ok := l.Tools[c.Name]; ok && t.ReadOnly() {
			idx = append(idx, i)
		}
	}
	if len(idx) > 1 {
		l.runConcurrent(ctx, calls, idx, results, errs)
	}
	// Phase 2: everything else, serially, in order. A write tool seeing
	// another write tool's outcome is correctness, not an optimization.
	for i, c := range calls {
		if results[i] != "" || errs[i] != nil {
			continue
		}
		results[i], errs[i] = l.callOne(ctx, c)
	}
	for i, c := range calls {
		if errs[i] != nil {
			results[i] = "ERROR: " + errs[i].Error()
		}
		*history = append(*history, provider.Message{
			Role: provider.RoleTool, Content: results[i], ToolCallID: c.ID, Name: c.Name,
		})
	}
	return nil
}

func (l *Loop) runConcurrent(ctx context.Context, calls []provider.ToolCall, idx []int, results []string, errs []error) {
	type slot struct{ i int }
	sem := make(chan slot, len(idx))
	done := make(chan struct{})
	for _, i := range idx {
		go func(i int) {
			var r string
			var e error
			if t, ok := l.Tools[calls[i].Name]; ok {
				r, e = t.Execute(ctx, calls[i].ArgsJSON)
			} else {
				e = fmt.Errorf("unknown tool %q", calls[i].Name)
			}
			results[i] = r
			errs[i] = e
			sem <- slot{i}
			done <- struct{}{}
		}(i)
	}
	for range idx {
		<-done
	}
}

func (l *Loop) callOne(ctx context.Context, c provider.ToolCall) (string, error) {
	t, ok := l.Tools[c.Name]
	if !ok {
		return "", fmt.Errorf("unknown tool %q", c.Name)
	}
	return t.Execute(ctx, c.ArgsJSON)
}

// completeWithRetry retries once on malformed tool-call JSON: local models
// are sloppy and a nudge fixes it more often than a failure would suggest.
// The second failure is returned for the caller to degrade — never an
// infinite retry loop.
func (l *Loop) completeWithRetry(ctx context.Context, window []provider.Message, tools []provider.ToolSpec) (provider.Response, error) {
	answer, err := l.complete(ctx, window, tools)
	if err == nil || !strings.Contains(err.Error(), provider.ErrToolCallJSON.Error()) {
		return answer, err
	}
	nudged := append(append([]provider.Message{}, window...), provider.Message{
		Role:    provider.RoleUser,
		Content: "上一次工具调用的 JSON 参数不合法。请只输出合法 JSON 的 tool_calls，不要把参数包在代码块或注释里。",
	})
	return l.complete(ctx, nudged, tools)
}

func (l *Loop) complete(ctx context.Context, window []provider.Message, tools []provider.ToolSpec) (provider.Response, error) {
	if l.OnDelta != nil {
		var assembled provider.Response
		err := l.Provider.Stream(ctx, window, tools, func(d provider.Delta) error {
			if d.Done {
				assembled.FinishReason = d.Finish
				return nil
			}
			assembled.Content += d.Text
			assembled.ToolCalls = append(assembled.ToolCalls, d.ToolCalls...)
			if l.OnDelta != nil {
				l.OnDelta(d)
			}
			return nil
		})
		if err == nil {
			return assembled, nil
		}
		// Streaming failed: fall back to one-shot. Some local gateways
		// accept stream=true and then break; the task must not.
	}
	return l.Provider.Complete(ctx, window, tools)
}

// trimWindow keeps the system prompt, the newest user message, and as
// much of the middle as fits. Oldest-first trimming is the compaction
// rule the Python side already follows (resume packs carry pointers, not
// bodies); here the trim is local and lossy, the transcript keeps all of
// it, and the caller that wants a smarter boundary owns MaxHistoryChars.
func trimWindow(history []provider.Message, maxChars int) []provider.Message {
	total := 0
	for _, m := range history {
		total += len(m.Content)
	}
	if total <= maxChars {
		return history
	}
	if len(history) == 0 {
		return history
	}
	var head []provider.Message
	budget := maxChars
	if history[0].Role == provider.RoleSystem {
		head = append(head, history[0])
		budget -= len(history[0].Content)
		history = history[1:]
	}
	// Keep from the tail backwards until the budget is spent; the most
	// recent context is what the answer depends on.
	kept := make([]provider.Message, 0, len(history))
	for i := len(history) - 1; i >= 0; i-- {
		cost := len(history[i].Content)
		if cost > budget && len(kept) > 0 {
			break
		}
		kept = append(kept, history[i])
		budget -= cost
	}
	// Reverse back to chronological order.
	for i, j := 0, len(kept)-1; i < j; i, j = i+1, j-1 {
		kept[i], kept[j] = kept[j], kept[i]
	}
	return append(head, kept...)
}
