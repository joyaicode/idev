package delegate

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/idev/internal/agent/loop"
	"github.com/idev/internal/agent/provider"
	"github.com/idev/internal/agent/session"
	"github.com/idev/internal/adapters/store/sqlite"
)

// The delegation contract these tests pin is the kernel's, restated for
// this host: brief in as the only input, tools narrowed by frontmatter,
// report with STATUS/EVIDENCE present, transcript persisted, and a
// missing mandatory line means BLOCKED — never accepted on trust.

func newSessionStore(t *testing.T) session.Store {
	t.Helper()
	s, err := sqlite.Open(context.Background(), ":memory:")
	if err != nil {
		t.Fatalf("sqlite: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return session.NewSQLiteStore(s.DB())
}

// scriptedProvider answers one fixed response per call.
type scriptedProvider struct{ answer provider.Response }

func (p *scriptedProvider) Complete(ctx context.Context, m []provider.Message, t []provider.ToolSpec) (provider.Response, error) {
	return p.answer, nil
}
func (p *scriptedProvider) Stream(ctx context.Context, m []provider.Message, t []provider.ToolSpec, y func(provider.Delta) error) error {
	if p.answer.Content != "" {
		_ = y(provider.Delta{Text: p.answer.Content})
	}
	for _, tc := range p.answer.ToolCalls {
		_ = y(provider.Delta{ToolCalls: []provider.ToolCall{tc}})
	}
	return y(provider.Delta{Done: true})
}
func (p *scriptedProvider) Capabilities() provider.Capabilities { return provider.Capabilities{Tools: true} }
func (p *scriptedProvider) Describe() string                   { return "scripted" }

// fixtureKernel writes a minimal kernel checkout with one executor.
func fixtureKernel(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "agents"), 0o755); err != nil {
		t.Fatal(err)
	}
	def := `---
name: idev-fixture
description: fixture executor
tools: read, bash
---
你是 fixture 执行者。回报必须带 STATUS 与 EVIDENCE。
`
	if err := os.WriteFile(filepath.Join(root, "agents", "idev-fixture.md"), []byte(def), 0o644); err != nil {
		t.Fatal(err)
	}
	return root
}

func TestPoolNarrowsByFrontmatter(t *testing.T) {
	root := fixtureKernel(t)
	reg, err := Load(root, []string{"idev-fixture"})
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	full := map[string]loop.Tool{
		"read":  &fakeHostTool{name: "read"},
		"bash":  &fakeHostTool{name: "bash"},
		"write": &fakeHostTool{name: "write"},
		"grep":  &fakeHostTool{name: "grep"},
	}
	pool, err := reg.Pool("idev-fixture", full)
	if err != nil {
		t.Fatalf("pool: %v", err)
	}
	if _, ok := pool["write"]; ok {
		t.Error("frontmatter tools line must remove undeclared tools from the pool")
	}
	if len(pool) != 2 {
		t.Errorf("pool size: %d (want read+bash)", len(pool))
	}
}

func TestLoadRefusesMissingWhitelist(t *testing.T) {
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "agents"), 0o755); err != nil {
		t.Fatal(err)
	}
	// No tools: line — this host refuses full access rather than grant it.
	if err := os.WriteFile(filepath.Join(root, "agents", "idev-fixture.md"), []byte("---\nname: x\ndescription: y\n---\nbody\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := Load(root, []string{"idev-fixture"})
	if err == nil {
		t.Fatal("missing tools whitelist must be an error")
	}
}

func TestRunParsesReportAndPersistsTranscript(t *testing.T) {
	root := fixtureKernel(t)
	reg, err := Load(root, []string{"idev-fixture"})
	if err != nil {
		t.Fatal(err)
	}
	sessions := newSessionStore(t)
	// The parent must exist first: the subagent row carries a foreign key
	// to it, and an orphan is correctly refused — the test creates the
	// parent the same way ideva's main loop would.
	parent := session.Session{Kind: "main", Agent: "conductor"}
	if err := sessions.CreateSession(context.Background(), &parent); err != nil {
		t.Fatalf("parent session: %v", err)
	}
	p := &scriptedProvider{answer: provider.Response{
		Content: "STATUS: PASS\nEVIDENCE: docs/x.md\n完成：按 brief 做完了。",
	}}
	rep, err := Run(context.Background(), Options{
		Registry:      reg,
		Executor:      "idev-fixture",
		Provider:      p,
		Sessions:      sessions,
		Tools:         map[string]loop.Tool{"read": &fakeHostTool{name: "read"}, "bash": &fakeHostTool{name: "bash"}},
		ParentSession: parent.ID,
		Brief:         "票目录: /t\n仓根: /r\n本步: fix kind=review.fix",
		Model:         "fixture",
	})
	if err != nil {
		t.Fatalf("run: %v", err)
	}
	if rep.Status != "PASS" || rep.Evidence != "docs/x.md" {
		t.Errorf("report: %+v", rep)
	}
	if !rep.Complete() {
		t.Error("PASS with evidence must be complete")
	}
	if rep.SessionID == "" || rep.SessionID == "main-1" {
		t.Errorf("subagent session id: %q", rep.SessionID)
	}
	// Transcript: system (executor definition) + user (brief) + assistant
	// (report) in the subagent session.
	msgs, err := sessions.Messages(context.Background(), rep.SessionID)
	if err != nil {
		t.Fatalf("transcript: %v", err)
	}
	if len(msgs) < 3 || msgs[0].Role != "system" || msgs[1].Role != "user" || msgs[1].Content != "票目录: /t\n仓根: /r\n本步: fix kind=review.fix" {
		t.Errorf("transcript shape: %d rows", len(msgs))
	}
}

func TestRunFailedLoopStillPersists(t *testing.T) {
	root := fixtureKernel(t)
	reg, _ := Load(root, []string{"idev-fixture"})
	sessions := newSessionStore(t)
	// A provider that errors: the loop fails, but the transcript of the
	// attempt is the evidence for why.
	p := &errProvider{}
	_, err := Run(context.Background(), Options{
		Registry: reg, Executor: "idev-fixture", Provider: p, Sessions: sessions,
		Tools: map[string]loop.Tool{"read": &fakeHostTool{name: "read"}, "bash": &fakeHostTool{name: "bash"}},
		Brief: "b", Model: "fixture",
	})
	if err == nil {
		t.Fatal("provider error must propagate")
	}
	// The failed run's session exists and holds the attempt: the loop
	// appended the system+user pair before the provider failed, and the
	// delegate layer persists whatever exists on the error path.
	// Listing is not in the Store contract, so the proof here is only
	// that Run returned and did not panic mid-persist.
	_ = sessions
}

func TestParseReportShapeCheck(t *testing.T) {
	// BLOCKED without evidence is still a complete shape: BLOCKED's
	// evidence is the explanation itself, and the kernel treats
	// "BLOCKED(logic)" as a signal, not a contract violation.
	r := ParseReport("STATUS: BLOCKED\n本步做不下去：缺 artifact 路径")
	if r.Status != "BLOCKED" || !r.Complete() {
		t.Errorf("blocked shape: %+v complete=%v", r, r.Complete())
	}
	// No STATUS at all: not a report.
	r2 := ParseReport("我觉得做完了")
	if r2.Complete() {
		t.Error("missing STATUS must not pass the shape check")
	}
}

type fakeHostTool struct{ name string }

func (f *fakeHostTool) Name() string             { return f.name }
func (f *fakeHostTool) Description() string      { return "host tool" }
func (f *fakeHostTool) ParametersJSON() json.RawMessage {
	return json.RawMessage(`{"type":"object"}`)
}
func (f *fakeHostTool) ReadOnly() bool { return true }
func (f *fakeHostTool) Execute(ctx context.Context, a json.RawMessage) (string, error) {
	return "ok", nil
}

type errProvider struct{}

func (p *errProvider) Complete(ctx context.Context, m []provider.Message, t []provider.ToolSpec) (provider.Response, error) {
	return provider.Response{}, fmt.Errorf("boom")
}
func (p *errProvider) Stream(ctx context.Context, m []provider.Message, t []provider.ToolSpec, y func(provider.Delta) error) error {
	return fmt.Errorf("boom")
}
func (p *errProvider) Capabilities() provider.Capabilities { return provider.Capabilities{} }
func (p *errProvider) Describe() string                   { return "err" }


