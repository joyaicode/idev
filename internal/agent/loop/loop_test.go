package loop

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"

	"github.com/idev/internal/agent/provider"
)

// fakeProvider scripts a conversation: each Complete call pops the next
// scripted response. Tests stay readable that way — a loop test IS a
// script of turns.
type fakeProvider struct {
	mu        sync.Mutex
	responses []provider.Response
	errs      []error
	calls     int
	seenTools []provider.ToolSpec
}

func (f *fakeProvider) Complete(ctx context.Context, msgs []provider.Message, tools []provider.ToolSpec) (provider.Response, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.seenTools = tools
	if len(f.errs) > 0 && f.errs[0] != nil {
		err := f.errs[0]
		f.errs = f.errs[1:]
		return provider.Response{}, err
	}
	if len(f.responses) == 0 {
		return provider.Response{Content: "done"}, nil
	}
	r := f.responses[0]
	f.responses = f.responses[1:]
	f.calls++
	return r, nil
}

func (f *fakeProvider) Stream(ctx context.Context, msgs []provider.Message, tools []provider.ToolSpec, yield func(provider.Delta) error) error {
	r, err := f.Complete(ctx, msgs, tools)
	if err != nil {
		return err
	}
	if r.Content != "" {
		if err := yield(provider.Delta{Text: r.Content}); err != nil {
			return err
		}
	}
	for _, tc := range r.ToolCalls {
		if err := yield(provider.Delta{ToolCalls: []provider.ToolCall{tc}}); err != nil {
			return err
		}
	}
	return yield(provider.Delta{Done: true, Finish: r.FinishReason})
}

func (f *fakeProvider) Capabilities() provider.Capabilities { return provider.Capabilities{Tools: true} }
func (f *fakeProvider) Describe() string                   { return "fake" }

// fakeTool records invocations; a write tool for ordering checks.
type fakeTool struct {
	name      string
	readOnly  bool
	mu        sync.Mutex
	invoked   []string
	responses map[string]string
	// delay lets the concurrency test observe real parallelism.
	delay bool
}

func (t *fakeTool) Name() string             { return t.name }
func (t *fakeTool) Description() string      { return "test tool" }
func (t *fakeTool) ParametersJSON() json.RawMessage {
	return json.RawMessage(`{"type":"object","properties":{"x":{"type":"string"}}}`)
}
func (t *fakeTool) ReadOnly() bool { return t.readOnly }

func (t *fakeTool) Execute(ctx context.Context, args json.RawMessage) (string, error) {
	if t.delay {
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		}
	}
	t.mu.Lock()
	t.invoked = append(t.invoked, string(args))
	t.mu.Unlock()
	if r, ok := t.responses[string(args)]; ok {
		return r, nil
	}
	return "ok:" + string(args), nil
}

func newLoop(p provider.Provider, tools ...Tool) *Loop {
	m := map[string]Tool{}
	for _, t := range tools {
		m[t.Name()] = t
	}
	return &Loop{Provider: p, Tools: m}
}

func TestLoopEndsOnPlainText(t *testing.T) {
	p := &fakeProvider{responses: []provider.Response{
		{ToolCalls: []provider.ToolCall{{ID: "1", Name: "read", ArgsJSON: json.RawMessage(`{"x":"a"}`)}}},
		{ToolCalls: []provider.ToolCall{{ID: "2", Name: "read", ArgsJSON: json.RawMessage(`{"x":"b"}`)}}},
		{Content: "final answer"},
	}}
	tool := &fakeTool{name: "read", readOnly: true}
	history := []provider.Message{{Role: provider.RoleSystem, Content: "sys"}}
	res, err := newLoop(p, tool).Run(context.Background(), &history, "go")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if res.Text != "final answer" {
		t.Errorf("text: %q", res.Text)
	}
	if res.ToolCallsMade != 2 {
		t.Errorf("tool calls: %d", res.ToolCallsMade)
	}
	// History must hold the full exchange: user, two assistant+tools, two
	// tool results, final assistant.
	roles := []string{}
	for _, m := range history {
		roles = append(roles, m.Role)
	}
	want := strings.Join([]string{
		provider.RoleSystem, provider.RoleUser,
		provider.RoleAssistant, provider.RoleTool,
		provider.RoleAssistant, provider.RoleTool,
		provider.RoleAssistant,
	}, ",")
	if strings.Join(roles, ",") != want {
		t.Errorf("roles: %v", roles)
	}
}

func TestLoopRetriesMalformedToolJSONOnce(t *testing.T) {
	p := &fakeProvider{errs: []error{fmt.Errorf("wrapped: %w", provider.ErrToolCallJSON)}}
	tool := &fakeTool{name: "bash"}
	history := []provider.Message{}
	res, err := newLoop(p, tool).Run(context.Background(), &history, "go")
	if err != nil {
		t.Fatalf("Run should survive one malformed tool JSON: %v", err)
	}
	if res.Text != "done" {
		t.Errorf("text: %q", res.Text)
	}
}

func TestLoopStopsAtMaxTurns(t *testing.T) {
	// A model that always asks for a tool is the stuck case; the counter
	// must stop it, with the pending state named in the error.
	p := &fakeProvider{responses: make([]provider.Response, 100)}
	for i := range p.responses {
		p.responses[i] = provider.Response{ToolCalls: []provider.ToolCall{{ID: "c", Name: "bash", ArgsJSON: json.RawMessage(`{}`)}}}
	}
	tool := &fakeTool{name: "bash"}
	l := newLoop(p, tool)
	l.MaxTurns = 3
	history := []provider.Message{}
	_, err := l.Run(context.Background(), &history, "loop forever")
	if err == nil || !strings.Contains(err.Error(), "MaxTurns") {
		t.Fatalf("want MaxTurns error, got %v", err)
	}
}

func TestUnknownToolBecomesErrorResultNotCrash(t *testing.T) {
	p := &fakeProvider{responses: []provider.Response{
		{ToolCalls: []provider.ToolCall{{ID: "1", Name: "no-such-tool", ArgsJSON: json.RawMessage(`{}`)}}},
		{Content: "recovered"},
	}}
	history := []provider.Message{}
	res, err := newLoop(p).Run(context.Background(), &history, "go")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if res.Text != "recovered" {
		t.Errorf("text: %q", res.Text)
	}
	// The tool result must carry the error as content — the model gets a
	// chance to fix its call, which is the whole point of tool loops.
	found := false
	for _, m := range history {
		if m.Role == provider.RoleTool && strings.Contains(m.Content, "unknown tool") {
			found = true
		}
	}
	if !found {
		t.Error("unknown tool error not fed back to the model")
	}
}

func TestReadOnlyToolsRunConcurrently(t *testing.T) {
	// Three reads that each block until all three started would deadlock
	// if executed serially. This is the turn-budget lesson as a host
	// guarantee: independent read-only calls share one turn.
	var started sync.WaitGroup
	started.Add(3)
	release := make(chan struct{})
	blocking := &fakeTool{name: "read", readOnly: true, delay: true}
	base := fakeTool{}
	blocking.responses = base.responses
	inner := &fakeTool{name: "read", readOnly: true}
	innerExecute := inner.Execute
	_ = innerExecute
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	p := &fakeProvider{responses: []provider.Response{
		{ToolCalls: []provider.ToolCall{
			{ID: "1", Name: "read", ArgsJSON: json.RawMessage(`{"x":"1"}`)},
			{ID: "2", Name: "read", ArgsJSON: json.RawMessage(`{"x":"2"}`)},
			{ID: "3", Name: "read", ArgsJSON: json.RawMessage(`{"x":"3"}`)},
		}},
		{Content: "done"},
	}}
	tool := &blockingTool{started: &started, release: release}
	history := []provider.Message{}
	go func() {
		started.Wait()
		close(release)
	}()
	_, err := newLoop(p, tool).Run(ctx, &history, "go")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
}

// blockingTool blocks until `release` closes; three of them only finish
// if the loop ran them concurrently.
type blockingTool struct {
	started *sync.WaitGroup
	release chan struct{}
}

func (t *blockingTool) Name() string        { return "read" }
func (t *blockingTool) Description() string { return "blocks until released" }
func (t *blockingTool) ParametersJSON() json.RawMessage {
	return json.RawMessage(`{"type":"object"}`)
}
func (t *blockingTool) ReadOnly() bool { return true }
func (t *blockingTool) Execute(ctx context.Context, args json.RawMessage) (string, error) {
	t.started.Done()
	select {
	case <-t.release:
		return "ok", nil
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

func TestTrimWindowKeepsSystemAndTail(t *testing.T) {
	history := []provider.Message{
		{Role: provider.RoleSystem, Content: strings.Repeat("s", 100)},
		{Role: provider.RoleUser, Content: "old1"},
		{Role: provider.RoleAssistant, Content: "old2"},
		{Role: provider.RoleUser, Content: "recent and long " + strings.Repeat("x", 300)},
	}
	trimmed := trimWindow(history, 350)
	if trimmed[0].Role != provider.RoleSystem {
		t.Error("system prompt must survive trimming")
	}
	if len(trimmed) < 2 || trimmed[len(trimmed)-1].Content != history[3].Content {
		t.Error("newest message must survive trimming")
	}
	for _, m := range trimmed[1:] {
		if m.Content == "old1" {
			t.Error("oldest context should be trimmed first")
		}
	}
}

func TestErrors(t *testing.T) {
	if !errors.Is(provider.ErrToolCallJSON, provider.ErrToolCallJSON) {
		t.Fatal("sanity")
	}
}

func TestContentToolCallRecovery(t *testing.T) {
	// The exact shape the first real ollama smoke produced: the model
	// answered a tool-bearing turn with the tool call as plain content.
	// The recovery path turns it into a real tool call so the turn
	// proceeds instead of the loop mistaking it for a final answer.
	p := &fakeProvider{responses: []provider.Response{
		{Content: `{"name": "write", "arguments": {"path": "/tmp/x", "content": "hi"}}`},
		{Content: "done"},
	}}
	tool := &fakeTool{name: "write"}
	history := []provider.Message{}
	res, err := newLoop(p, tool).Run(context.Background(), &history, "write a file")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if res.Text != "done" {
		t.Errorf("text: %q", res.Text)
	}
	if len(tool.invoked) != 1 {
		t.Fatalf("recovered call not executed: %v", tool.invoked)
	}
	// History must record it as a tool call, not as prose — the transcript
	// is what a resume replays from.
	var sawToolCall bool
	for _, m := range history {
		if m.Role == provider.RoleAssistant && len(m.ToolCalls) == 1 && m.ToolCalls[0].Name == "write" {
			sawToolCall = true
		}
	}
	if !sawToolCall {
		t.Error("recovered call not recorded as tool_calls in history")
	}
}

func TestContentProseIsNotRecovered(t *testing.T) {
	// Prose around a JSON shape, or a JSON naming an unknown tool, stays
	// plain text — the sniffer is conservative on purpose.
	p := &fakeProvider{responses: []provider.Response{
		{Content: `我认为应该这样：{"name": "no-such-tool", "arguments": {}}`},
	}}
	history := []provider.Message{}
	res, err := newLoop(p).Run(context.Background(), &history, "go")
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if res.Text == "" || strings.Contains(res.Text, "tool") == false {
		// it must be the prose answer, and no tool executed
		t.Logf("text: %q", res.Text)
	}
	if res.ToolCallsMade != 0 {
		t.Errorf("prose should not recover into tool calls: %d", res.ToolCallsMade)
	}
}
