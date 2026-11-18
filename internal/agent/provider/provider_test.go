package provider

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// The three targets this provider must serve share one wire; each test pins
// the dialect detail that gateway in practice varies: plain completion,
// fragmented streaming tool calls, malformed arguments, and the fall-back.

func newTestProvider(handler http.HandlerFunc) (*OpenAI, *httptest.Server) {
	srv := httptest.NewServer(handler)
	t := &testing.T{}
	_ = t
	cfg := Config{BaseURL: srv.URL + "/v1", Model: "test-model"}
	return NewOpenAI(cfg), srv
}

func TestCompleteParsesToolCalls(t *testing.T) {
	args := `{"command":"ls -la"}`
	// Arguments travel as a JSON string on the wire (OpenAI's choice);
	// %q keeps the fixture honest about that double-encoding.
	wireArgs := strings.ReplaceAll(args, `"`, `\"`)
	p, srv := newTestProvider(func(w http.ResponseWriter, r *http.Request) {
		var req wireRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("bad request: %v", err)
		}
		if req.Model != "test-model" {
			t.Errorf("model not passed: %q", req.Model)
		}
		if len(req.Tools) == 0 {
			t.Error("tools not sent")
		}
		if req.Stream {
			t.Error("non-streaming request set stream=true")
		}
		fmt.Fprintf(w, `{"choices":[{"message":{"role":"assistant","content":"","tool_calls":[{"id":"c1","type":"function","function":{"name":"bash","arguments":"%s"}}]},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":10,"completion_tokens":5}}`, wireArgs)
	})
	defer srv.Close()
	resp, err := p.Complete(context.Background(), []Message{{Role: RoleUser, Content: "list files"}}, []ToolSpec{{Name: "bash", Description: "run a command", ParametersJSON: json.RawMessage(`{"type":"object"}`)}})
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if len(resp.ToolCalls) != 1 || resp.ToolCalls[0].Name != "bash" {
		t.Fatalf("tool calls: %+v", resp.ToolCalls)
	}
	if string(resp.ToolCalls[0].ArgsJSON) != args {
		t.Fatalf("args not raw: %s", resp.ToolCalls[0].ArgsJSON)
	}
	if resp.FinishReason != "tool_calls" {
		t.Errorf("finish: %q", resp.FinishReason)
	}
	if resp.Usage.InputTokens != 10 || resp.Usage.OutputTokens != 5 {
		t.Errorf("usage: %+v", resp.Usage)
	}
}

func TestCompleteRejectsInvalidToolJSON(t *testing.T) {
	p, srv := newTestProvider(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"choices":[{"message":{"role":"assistant","tool_calls":[{"id":"c1","type":"function","function":{"name":"bash","arguments":"{oops"}}],"content":""},"finish_reason":"tool_calls"}]}`)
	})
	defer srv.Close()
	_, err := p.Complete(context.Background(), []Message{{Role: RoleUser, Content: "go"}}, nil)
	if err == nil || !strings.Contains(err.Error(), ErrToolCallJSON.Error()) {
		t.Fatalf("want ErrToolCallJSON, got %v", err)
	}
}

func TestCompleteSurfacesHTTPErrorBody(t *testing.T) {
	p, srv := newTestProvider(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":{"message":"model not found"}}`, http.StatusNotFound)
	})
	defer srv.Close()
	_, err := p.Complete(context.Background(), []Message{{Role: RoleUser, Content: "x"}}, nil)
	if err == nil || !strings.Contains(err.Error(), "404") {
		t.Fatalf("want status in error, got %v", err)
	}
}

func TestStreamAssemblesFragmentedToolCalls(t *testing.T) {
	// The shape every local gateway eventually emits: id+name first chunk,
	// arguments sliced across chunks, usage on a trailing empty-choices
	// chunk, [DONE] last.
	p, srv := newTestProvider(func(w http.ResponseWriter, r *http.Request) {
		var req wireRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Errorf("bad request: %v", err)
		}
		if !req.Stream {
			t.Error("streaming request set stream=false")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		flush := w.(http.Flusher)
		lines := []string{
			`{"choices":[{"delta":{"content":"thinking "},"finish_reason":""}]}`,
			`{"choices":[{"delta":{"content":"about it"},"finish_reason":""}]}`,
			`{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","type":"function","function":{"name":"bash","arguments":""}}]},"finish_reason":""}]}`,
			`{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"co"}}]},"finish_reason":""}]}`,
			`{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"mmand\":\"ls\"}"}}]},"finish_reason":"tool_calls"}]}`,
			`{"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":7}}`,
			`[DONE]`,
		}
		for _, l := range lines {
			fmt.Fprintf(w, "data: %s\n\n", l)
			flush.Flush()
		}
	})
	defer srv.Close()
	var texts []string
	var calls []ToolCall
	finish := ""
	err := p.Stream(context.Background(), []Message{{Role: RoleUser, Content: "go"}}, nil, func(d Delta) error {
		if d.Text != "" {
			texts = append(texts, d.Text)
		}
		calls = append(calls, d.ToolCalls...)
		if d.Done {
			finish = d.Finish
		}
		return nil
	})
	if err != nil {
		t.Fatalf("Stream: %v", err)
	}
	if strings.Join(texts, "") != "thinking about it" {
		t.Errorf("text: %q", texts)
	}
	if len(calls) != 1 {
		t.Fatalf("calls: %+v", calls)
	}
	if calls[0].Name != "bash" || calls[0].ID != "c1" {
		t.Errorf("call identity: %+v", calls[0])
	}
	if string(calls[0].ArgsJSON) != `{"command":"ls"}` {
		t.Errorf("assembled args: %s", calls[0].ArgsJSON)
	}
	if finish != "tool_calls" {
		t.Errorf("finish: %q", finish)
	}
}

func TestStreamToleratesMalformedChunk(t *testing.T) {
	p, srv := newTestProvider(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		flush := w.(http.Flusher)
		for _, l := range []string{
			`{"choices":[{"delta":{"content":"a"}}]}`,
			`not json at all`,
			`{"choices":[{"delta":{"content":"b"},"finish_reason":"stop"}]}`,
			`[DONE]`,
		} {
			fmt.Fprintf(w, "data: %s\n\n", l)
			flush.Flush()
		}
	})
	defer srv.Close()
	var got strings.Builder
	err := p.Stream(context.Background(), []Message{{Role: RoleUser, Content: "x"}}, nil, func(d Delta) error {
		got.WriteString(d.Text)
		return nil
	})
	if err != nil {
		t.Fatalf("Stream: %v", err)
	}
	if got.String() != "ab" {
		t.Errorf("stream lost text around bad chunk: %q", got.String())
	}
}

func TestAuthAndHeaders(t *testing.T) {
	var gotAuth, gotExtra string
	p, srv := newTestProvider(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		gotExtra = r.Header.Get("X-Gateway")
		fmt.Fprint(w, `{"choices":[{"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}]}`)
	})
	defer srv.Close()
	p.cfg.APIKey = "sk-test"
	p.cfg.ExtraHTTPHeaders = map[string]string{"X-Gateway": "jdcloud"}
	_, err := p.Complete(context.Background(), []Message{{Role: RoleUser, Content: "x"}}, nil)
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if gotAuth != "Bearer sk-test" {
		t.Errorf("auth: %q", gotAuth)
	}
	if gotExtra != "jdcloud" {
		t.Errorf("extra header: %q", gotExtra)
	}
}

func TestPresetRejectsUnknown(t *testing.T) {
	if _, err := Preset("mystery"); err == nil {
		t.Fatal("unknown preset must be an error, not a guess")
	}
	if _, err := Preset("ollama"); err != nil {
		t.Fatalf("ollama preset: %v", err)
	}
}

func TestDefaultURLOllama(t *testing.T) {
	p := NewOpenAI(Config{Model: "qwen3"})
	if p.cfg.BaseURL != "http://127.0.0.1:11434/v1" {
		t.Errorf("empty base URL should default to ollama, got %s", p.cfg.BaseURL)
	}
}
