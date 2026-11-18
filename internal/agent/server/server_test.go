package server

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/idev/internal/agent/delegate"
	"github.com/idev/internal/agent/loop"
	"github.com/idev/internal/agent/provider"
	"github.com/idev/internal/agent/session"
	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// These tests drive the server through the SDK's in-memory transports —
// the same wire path an external host takes, without a subprocess.

func fixtureDeps(t *testing.T) Deps {
	t.Helper()
	root := t.TempDir()
	agentDef := `---
name: idev-fixture
description: fixture executor
tools: read, bash
---
你是 fixture 执行者。
`
	if err := writeAgent(root, agentDef); err != nil {
		t.Fatal(err)
	}
	reg, err := delegate.Load(root, []string{"idev-fixture"})
	if err != nil {
		t.Fatal(err)
	}
	store, err := sqlite.Open(context.Background(), ":memory:")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { store.Close() })
	return Deps{
		Registry: reg,
		Provider: &fixtureProvider{},
		Sessions: session.NewSQLiteStore(store.DB()),
		Tools: map[string]loop.Tool{
			"read": stubTool{name: "read"},
			"bash": stubTool{name: "bash"},
		},
		Model: "fixture",
	}
}

func writeAgent(root, def string) error {
	if err := os.MkdirAll(filepath.Join(root, "agents"), 0o755); err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(root, "agents", "idev-fixture.md"), []byte(def), 0o644)
}

func TestExecutorsToolListsMounted(t *testing.T) {
	deps := fixtureDeps(t)
	srv := NewServer(deps)
	client := mcp.NewClient(&mcp.Implementation{Name: "test-host", Version: "0"}, nil)
	ctrans, strans := mcp.NewInMemoryTransports()
	// Server first, synchronously: net.Pipe is unbuffered, so a client
	// whose initialize has no reader on the other end blocks forever —
	// the SDK's own tests connect the server side before the client.
	ss, err := srv.Connect(context.Background(), strans, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer ss.Close()
	sess, err := client.Connect(context.Background(), ctrans, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer sess.Close()

	result, err := sess.CallTool(context.Background(), &mcp.CallToolParams{Name: "executors"})
	if err != nil {
		t.Fatalf("call: %v", err)
	}
	if result.IsError {
		t.Fatalf("executors errored: %+v", result.Content)
	}
	var payload struct {
		Executors []struct {
			Name  string   `json:"name"`
			Tools []string `json:"tools"`
		} `json:"executors"`
	}
	if err := decodeStructured(result, &payload); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(payload.Executors) != 1 || payload.Executors[0].Name != "idev-fixture" {
		t.Fatalf("executors: %+v", payload.Executors)
	}
	if len(payload.Executors[0].Tools) != 2 {
		t.Errorf("whitelist not reported: %+v", payload.Executors[0].Tools)
	}
}

func TestDelegateRequiresBrief(t *testing.T) {
	deps := fixtureDeps(t)
	srv := NewServer(deps)
	client := mcp.NewClient(&mcp.Implementation{Name: "test-host", Version: "0"}, nil)
	ctrans, strans := mcp.NewInMemoryTransports()
	ss, err := srv.Connect(context.Background(), strans, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer ss.Close()
	sess, _ := client.Connect(context.Background(), ctrans, nil)
	defer sess.Close()

	result, err := sess.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      "delegate",
		Arguments: map[string]any{"executor": "idev-fixture", "brief": ""},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !result.IsError {
		t.Fatal("empty brief must be BLOCKED (IsError data, not a wire failure)")
	}
}

func TestDelegateUnknownExecutorBlocked(t *testing.T) {
	deps := fixtureDeps(t)
	srv := NewServer(deps)
	client := mcp.NewClient(&mcp.Implementation{Name: "test-host", Version: "0"}, nil)
	ctrans, strans := mcp.NewInMemoryTransports()
	ss, err := srv.Connect(context.Background(), strans, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer ss.Close()
	sess, _ := client.Connect(context.Background(), ctrans, nil)
	defer sess.Close()

	result, err := sess.CallTool(context.Background(), &mcp.CallToolParams{
		Name:      "delegate",
		Arguments: map[string]any{"executor": "no-such", "brief": "票目录: /t"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !result.IsError {
		t.Fatal("unknown executor must be BLOCKED")
	}
}

// --- fixtures -----------------------------------------------------------

type fixtureProvider struct{}

func (p *fixtureProvider) Complete(ctx context.Context, m []provider.Message, t []provider.ToolSpec) (provider.Response, error) {
	return provider.Response{Content: "STATUS: PASS\nEVIDENCE: docs/x.md\nok"}, nil
}
func (p *fixtureProvider) Stream(ctx context.Context, m []provider.Message, t []provider.ToolSpec, y func(provider.Delta) error) error {
	_ = y(provider.Delta{Text: "STATUS: PASS\nEVIDENCE: docs/x.md\nok"})
	return y(provider.Delta{Done: true})
}
func (p *fixtureProvider) Capabilities() provider.Capabilities { return provider.Capabilities{Tools: true} }
func (p *fixtureProvider) Describe() string                   { return "fixture" }

type stubTool struct{ name string }

func (s stubTool) Name() string                  { return s.name }
func (s stubTool) Description() string           { return "stub" }
func (s stubTool) ParametersJSON() json.RawMessage { return json.RawMessage(`{"type":"object"}`) }
func (s stubTool) ReadOnly() bool                 { return true }
func (s stubTool) Execute(ctx context.Context, a json.RawMessage) (string, error) {
	return "ok", nil
}

func decodeStructured(result *mcp.CallToolResult, into any) error {
	blob, err := json.Marshal(result.StructuredContent)
	if err != nil {
		return err
	}
	return json.Unmarshal(blob, into)
}
