package session

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/idev/internal/agent/provider"
	"github.com/idev/internal/adapters/store/sqlite"
)

// The transcript rules that matter are the ones the control plane learned
// the hard way: append-only, replay in order, no silent overwrite. Each
// test pins one.

func newStore(t *testing.T) *SQLiteStore {
	t.Helper()
	s, err := sqlite.Open(context.Background(), ":memory:")
	if err != nil {
		t.Fatalf("sqlite open: %v", err)
	}
	t.Cleanup(func() { s.Close() })
	return NewSQLiteStore(s.DB())
}

func TestCreateAndReplay(t *testing.T) {
	st := newStore(t)
	sess := Session{Kind: "main", Agent: "conductor", Provider: "ollama", Model: "qwen3"}
	if err := st.CreateSession(context.Background(), &sess); err != nil {
		t.Fatalf("create: %v", err)
	}
	if sess.ID == "" {
		t.Fatal("session id must be minted")
	}
	messages := []provider.Message{
		{Role: provider.RoleSystem, Content: "sys"},
		{Role: provider.RoleUser, Content: "go"},
		{Role: provider.RoleAssistant, Content: "", ToolCalls: []provider.ToolCall{
			{ID: "c1", Name: "bash", ArgsJSON: []byte(`{"command":"ls"}`)},
		}},
		{Role: provider.RoleTool, Content: "result", ToolCallID: "c1", Name: "bash"},
		{Role: provider.RoleAssistant, Content: "done"},
	}
	for _, m := range messages {
		if err := st.AppendMessage(context.Background(), sess.ID, m); err != nil {
			t.Fatalf("append %s: %v", m.Role, err)
		}
	}
	got, err := st.Messages(context.Background(), sess.ID)
	if err != nil {
		t.Fatalf("messages: %v", err)
	}
	if len(got) != len(messages) {
		t.Fatalf("replay length: %d != %d", len(got), len(messages))
	}
	for i, m := range got {
		if m.Role != messages[i].Role || m.Content != messages[i].Content {
			t.Errorf("row %d: %+v != %+v", i, m, messages[i])
		}
	}
	if len(got[2].ToolCalls) != 1 || got[2].ToolCalls[0].Name != "bash" {
		t.Errorf("tool calls not round-tripped: %+v", got[2].ToolCalls)
	}
	if string(got[2].ToolCalls[0].ArgsJSON) != `{"command":"ls"}` {
		t.Errorf("args must round-trip raw: %s", got[2].ToolCalls[0].ArgsJSON)
	}
	if got[3].ToolCallID != "c1" || got[3].Name != "bash" {
		t.Errorf("tool result identity: %+v", got[3])
	}
}

func TestAppendOnlyNoUpdate(t *testing.T) {
	// Store has no update and no delete; this test exists so that anyone
	// adding one has to come here and read why: the review's §3.2 finding
	// was records racing and the second write silently winning. History
	// that can be edited is not a transcript.
	st := newStore(t)
	sess := Session{}
	if err := st.CreateSession(context.Background(), &sess); err != nil {
		t.Fatalf("create: %v", err)
	}
	for i := 0; i < 3; i++ {
		if err := st.AppendMessage(context.Background(), sess.ID, provider.Message{Role: provider.RoleUser, Content: "m"}); err != nil {
			t.Fatalf("append %d: %v", i, err)
		}
	}
	got, _ := st.Messages(context.Background(), sess.ID)
	if len(got) != 3 {
		t.Fatalf("want 3 messages, got %d", len(got))
	}
}

func TestSessionsIsolatedBySeq(t *testing.T) {
	st := newStore(t)
	a := Session{Kind: "main"}
	b := Session{Kind: "main"}
	if err := st.CreateSession(context.Background(), &a); err != nil {
		t.Fatal(err)
	}
	if err := st.CreateSession(context.Background(), &b); err != nil {
		t.Fatal(err)
	}
	if err := st.AppendMessage(context.Background(), a.ID, provider.Message{Role: provider.RoleUser, Content: "a1"}); err != nil {
		t.Fatal(err)
	}
	if err := st.AppendMessage(context.Background(), b.ID, provider.Message{Role: provider.RoleUser, Content: "b1"}); err != nil {
		t.Fatal(err)
	}
	if err := st.AppendMessage(context.Background(), a.ID, provider.Message{Role: provider.RoleUser, Content: "a2"}); err != nil {
		t.Fatal(err)
	}
	ga, _ := st.Messages(context.Background(), a.ID)
	gb, _ := st.Messages(context.Background(), b.ID)
	if len(ga) != 2 || len(gb) != 1 {
		t.Fatalf("isolation: a=%d b=%d", len(ga), len(gb))
	}
}

func TestJSONLAppendsLines(t *testing.T) {
	dir := t.TempDir()
	m := provider.Message{Role: provider.RoleAssistant, Content: "hello"}
	if err := JSONL(filepath.Join(dir, "t"), "s1", m); err != nil {
		t.Fatalf("jsonl: %v", err)
	}
	if err := JSONL(filepath.Join(dir, "t"), "s1", m); err != nil {
		t.Fatalf("jsonl 2: %v", err)
	}
	// Each call is one line; the replay format the Python side already
	// reads is line-delimited JSON.
	body, err := os.ReadFile(filepath.Join(dir, "t", "s1.jsonl"))
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if n := strings.Count(string(body), "\n"); n != 2 {
		t.Fatalf("want 2 lines, got %d", n)
	}
}
