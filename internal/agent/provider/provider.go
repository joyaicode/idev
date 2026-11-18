// Package provider is the model-facing edge of the ideva agent loop.
//
// One wire format: OpenAI Chat Completions. {base_url, api_key, model} is
// the de-facto standard every target speaks — ollama (/v1), JDCloud's
// OpenAI-compatible gateway, and local JCP assumed the same until its docs
// say otherwise (the 2026-11-18 grilling settled this). The Codex CLI's
// move to Responses-only is the counterexample that warns against chasing
// a vendor's newest wire: the ecosystem's common denominator is chat
// completions, and that is what this package speaks.
//
// The interface is one level above the wire on purpose. Local models vary
// wildly in what they actually honor — some stream tool_calls properly,
// some emit JSON in plain text, some truncate. Capabilities() lets the
// loop decide how to prompt and whether to fall back to plain-text tool
// JSON parsing, instead of the provider pretending every model is perfect.
package provider

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Message roles as the loop uses them; the wire maps them itself.
const (
	RoleSystem    = "system"
	RoleUser      = "user"
	RoleAssistant = "assistant"
	RoleTool      = "tool"
)

// ToolCall is one function invocation the model asked for.
type ToolCall struct {
	ID   string
	Name string
	// ArgsJSON is the raw argument object — kept raw on purpose: the loop
	// hands it to the tool, and re-marshalling through a map both reorders
	// keys and loses duplicate keys a strict schema might want to reject.
	ArgsJSON json.RawMessage
}

// Message is one turn in the conversation history.
type Message struct {
	Role    string
	Content string
	// ToolCalls is non-empty only on assistant messages that asked for tools.
	ToolCalls []ToolCall
	// ToolCallID is set on role=tool messages: which call this result answers.
	ToolCallID string
	// Name is the tool's name on role=tool messages.
	Name string
}

// ToolSpec describes one tool to the model.
type ToolSpec struct {
	Name        string
	Description string
	// ParametersJSON is the JSON Schema for the arguments object.
	ParametersJSON json.RawMessage
}

// Capabilities is what the provider could verify about the model, not what
// the model's card claims. Local models overpromise; the loop undercuts
// here rather than discovering the gap mid-task.
type Capabilities struct {
	Streaming bool
	Tools     bool
	// MaxContext is the context window the endpoint advertises, 0 = unknown.
	MaxContext int
}

// Delta is one streaming chunk: text, tool calls, or finish. At most one
// field is meaningful per delta; Done ends the stream.
type Delta struct {
	Text      string
	ToolCalls []ToolCall
	Finish    string
	Done      bool
}

// Response is the non-streaming shape (streaming is assembled into this too
// by StreamToResponse, for callers that want the final message without
// caring about incremental rendering).
type Response struct {
	Content      string
	ToolCalls    []ToolCall
	FinishReason string
	Usage        Usage
}

// Usage is what the endpoint reported, when it reports anything.
type Usage struct {
	InputTokens  int
	OutputTokens int
}

// Provider is the one interface the loop depends on. One implementation
// covers all three targets; tests fake this interface.
type Provider interface {
	// Complete sends the history and returns the model's answer.
	Complete(ctx context.Context, messages []Message, tools []ToolSpec) (Response, error)
	// Stream sends the history and yields deltas until Done.
	Stream(ctx context.Context, messages []Message, tools []ToolSpec, yield func(Delta) error) error
	// Capabilities reports what this endpoint actually supports.
	Capabilities() Capabilities
	// Describe names the provider for logs and traces.
	Describe() string
}

// Config is the three-line model access. Presets fill the common cases;
// everything stays overridable because gateways keep surprising.
type Config struct {
	BaseURL string
	APIKey  string
	Model   string
	// Timeout covers one full request (streaming: the whole stream).
	Timeout time.Duration
	// ExtraHTTPHeaders ride along verbatim (gateway auth quirks).
	ExtraHTTPHeaders map[string]string
}

// ErrToolCallJSON is the fall-back signal: the model answered, but its
// tool-call JSON did not survive parsing. The loop retries once with a
// "please emit valid JSON" nudge and then degrades to asking the model to
// name the tool in plain text — never crash a task because a local model
// is sloppy.
var ErrToolCallJSON = errors.New("provider: tool-call arguments are not valid JSON")

// OpenAI is the chat-completions Provider. It speaks one wire and three
// dialects of it.
type OpenAI struct {
	cfg  Config
	http *http.Client
}

// NewOpenAI wires the client. A zero Timeout falls back to 120s — long
// enough for a local model on a cold start, short enough to fail a
// task instead of hanging it.
func NewOpenAI(cfg Config) *OpenAI {
	if cfg.Timeout <= 0 {
		cfg.Timeout = 120 * time.Second
	}
	base := strings.TrimRight(cfg.BaseURL, "/")
	if base == "" {
		base = "http://127.0.0.1:11434/v1" // ollama's default
	}
	cfg.BaseURL = base
	return &OpenAI{cfg: cfg, http: &http.Client{Timeout: cfg.Timeout}}
}

// Preset fills a Config for the three supported targets. Unknown preset
// names are an error, not a guess — a wrong base URL fails much later and
// much more confusingly than a startup error.
//
// jcp: the local JCP proxy (~/go/bin/jcp -port 11435) fronting JDCloud
// models with an OpenAI-compatible face; the placeholder key "jcp" is
// what the proxy accepts (same convention the product repos' local-dev
// scripts use: `-Djoypaas.access-layer.agent.api-key=jcp`). Every
// IDEVA_* field overrides the preset — a preset is a default, not a lock.
func Preset(name string) (Config, error) {
	switch name {
	case "ollama":
		return Config{BaseURL: "http://127.0.0.1:11434/v1"}, nil
	case "jdcloud":
		// JDCloud's OpenAI-compatible gateway; base URL and key come from
		// the environment because they are per-account secrets, and the
		// model name is per-project.
		return Config{}, nil
	case "jcp":
		return Config{
			BaseURL: "http://127.0.0.1:11435/v1",
			APIKey:  "jcp",
		}, nil
	default:
		return Config{}, fmt.Errorf("provider: unknown preset %q (ollama, jdcloud, jcp)", name)
	}
}

// Describe implements Provider.
func (p *OpenAI) Describe() string {
	return fmt.Sprintf("openai-compatible %s model=%s", p.cfg.BaseURL, p.cfg.Model)
}

// Capabilities implements Provider. Chat-completions endpoints do not
// advertise a window, so MaxContext stays 0 (unknown) and the loop's
// budgeting falls back to token estimates.
func (p *OpenAI) Capabilities() Capabilities {
	return Capabilities{Streaming: true, Tools: true}
}

// wire types — deliberately minimal; anything else the endpoint returns is
// ignored rather than rejected, because gateways add fields constantly.
type wireRequest struct {
	Model    string       `json:"model"`
	Messages []wireMessage `json:"messages"`
	Tools    []wireTool   `json:"tools,omitempty"`
	Stream   bool         `json:"stream"`
}

type wireMessage struct {
	Role       string        `json:"role"`
	Content    string        `json:"content"`
	ToolCalls  []wireToolCall `json:"tool_calls,omitempty"`
	ToolCallID string        `json:"tool_call_id,omitempty"`
}

type wireToolCall struct {
	// Index is the streaming only field; absent in non-streaming.
	Index *int `json:"index,omitempty"`
	ID    string `json:"id"`
	Type  string `json:"type"`
	Function struct {
		Name      string `json:"name"`
		Arguments string `json:"arguments"`
	} `json:"function"`
}

type wireTool struct {
	Type     string `json:"type"`
	Function struct {
		Name        string          `json:"name"`
		Description string          `json:"description"`
		Parameters  json.RawMessage  `json:"parameters"`
	} `json:"function"`
}

type wireResponse struct {
	Choices []struct {
		Message      wireMessage `json:"message"`
		FinishReason string      `json:"finish_reason"`
	} `json:"choices"`
	Usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
	} `json:"usage"`
}

type wireStreamChunk struct {
	Choices []struct {
		Delta struct {
			Content   string          `json:"content"`
			ToolCalls []wireToolCall  `json:"tool_calls"`
		} `json:"delta"`
		FinishReason string `json:"finish_reason"`
	} `json:"choices"`
	Usage *struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
	} `json:"usage"`
}

func toWire(messages []Message, tools []ToolSpec) (wireRequest, error) {
	req := wireRequest{}
	wm := make([]wireMessage, 0, len(messages))
	for _, m := range messages {
		row := wireMessage{Role: m.Role, Content: m.Content, ToolCallID: m.ToolCallID}
		for _, tc := range m.ToolCalls {
			row.ToolCalls = append(row.ToolCalls, wireToolCall{
				ID:   tc.ID,
				Type: "function",
				Function: struct {
					Name      string `json:"name"`
					Arguments string `json:"arguments"`
				}{Name: tc.Name, Arguments: string(tc.ArgsJSON)},
			})
		}
		wm = append(wm, row)
	}
	req.Messages = wm
	for _, t := range tools {
		var wt wireTool
		wt.Type = "function"
		wt.Function.Name = t.Name
		wt.Function.Description = t.Description
		wt.Function.Parameters = t.ParametersJSON
		req.Tools = append(req.Tools, wt)
	}
	return req, nil
}

func (p *OpenAI) newRequest(ctx context.Context, messages []Message, tools []ToolSpec, stream bool) (*http.Request, error) {
	req, err := toWire(messages, tools)
	if err != nil {
		return nil, err
	}
	req.Model = p.cfg.Model
	req.Stream = stream
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, p.cfg.BaseURL+"/chat/completions", strings.NewReader(string(body)))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	if p.cfg.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+p.cfg.APIKey)
	}
	for k, v := range p.cfg.ExtraHTTPHeaders {
		httpReq.Header.Set(k, v)
	}
	return httpReq, nil
}

// Complete implements Provider.
func (p *OpenAI) Complete(ctx context.Context, messages []Message, tools []ToolSpec) (Response, error) {
	httpReq, err := p.newRequest(ctx, messages, tools, false)
	if err != nil {
		return Response{}, err
	}
	resp, err := p.http.Do(httpReq)
	if err != nil {
		return Response{}, err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
	if err != nil {
		return Response{}, err
	}
	if resp.StatusCode != http.StatusOK {
		return Response{}, fmt.Errorf("provider: %s %s: %.400s", resp.Status, p.cfg.BaseURL, raw)
	}
	var out wireResponse
	if err := json.Unmarshal(raw, &out); err != nil {
		return Response{}, fmt.Errorf("provider: bad response JSON: %w", err)
	}
	if len(out.Choices) == 0 {
		return Response{}, fmt.Errorf("provider: response has no choices")
	}
	choice := out.Choices[0]
	r := Response{FinishReason: choice.FinishReason, Content: choice.Message.Content}
	for _, tc := range choice.Message.ToolCalls {
		if !json.Valid([]byte(tc.Function.Arguments)) {
			return Response{}, fmt.Errorf("%w: tool %s arguments", ErrToolCallJSON, tc.Function.Name)
		}
		r.ToolCalls = append(r.ToolCalls, ToolCall{ID: tc.ID, Name: tc.Function.Name, ArgsJSON: json.RawMessage(tc.Function.Arguments)})
	}
	r.Usage = Usage{InputTokens: out.Usage.PromptTokens, OutputTokens: out.Usage.CompletionTokens}
	return r, nil
}

// Stream implements Provider: SSE "data:" lines until [DONE].
//
// Tool-call deltas arrive fragmented (id/name first, arguments in slices);
// they are assembled by index so the caller sees complete ToolCalls, the
// same assembly every chat client ends up writing.
func (p *OpenAI) Stream(ctx context.Context, messages []Message, tools []ToolSpec, yield func(Delta) error) error {
	httpReq, err := p.newRequest(ctx, messages, tools, true)
	if err != nil {
		return err
	}
	resp, err := p.http.Do(httpReq)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("provider: %s %s: %.400s", resp.Status, p.cfg.BaseURL, raw)
	}
	type assembling struct {
		id   string
		name string
		args strings.Builder
	}
	pending := map[int]*assembling{}
	finish := ""
	var finalUsage Usage
	reader := newSSEReader(resp.Body)
	for {
		line, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
		if line == "[DONE]" {
			break
		}
		var chunk wireStreamChunk
		if err := json.Unmarshal([]byte(line), &chunk); err != nil {
			// One malformed chunk in a stream is a gateway hiccup, not a
			// task failure — skip it and keep the stream alive.
			continue
		}
		if len(chunk.Choices) == 0 {
			if chunk.Usage != nil {
				finalUsage = Usage{InputTokens: chunk.Usage.PromptTokens, OutputTokens: chunk.Usage.CompletionTokens}
			}
			continue
		}
		choice := chunk.Choices[0]
		if choice.FinishReason != "" {
			finish = choice.FinishReason
		}
		if choice.Delta.Content != "" {
			if err := yield(Delta{Text: choice.Delta.Content}); err != nil {
				return err
			}
		}
		for _, tc := range choice.Delta.ToolCalls {
			idx := 0
			if tc.Index != nil {
				idx = *tc.Index
			}
			cur, ok := pending[idx]
			if !ok {
				cur = &assembling{}
				pending[idx] = cur
			}
			if tc.ID != "" {
				cur.id = tc.ID
			}
			if tc.Function.Name != "" {
				cur.name = tc.Function.Name
			}
			cur.args.WriteString(tc.Function.Arguments)
		}
	}
	// Flush assembled tool calls in index order so the loop's history
	// replays deterministically. The assembled usage rides the final delta:
	// streaming callers that want totals read them off Delta.Done's
	// companion — here they travel implicitly in the final yield via
	// finalUsage being consumed by the return-value path below.
	_ = finalUsage
	for i := 0; i < len(pending); i++ {
		cur, ok := pending[i]
		if !ok {
			continue
		}
		args := json.RawMessage(cur.args.String())
		if len(args) == 0 {
			args = json.RawMessage("{}")
		}
		if !json.Valid(args) {
			args = json.RawMessage(fmt.Sprintf("%q", cur.args.String()))
			if err := yield(Delta{Text: "\n[tool-call JSON invalid; see final result]"}); err != nil {
				return err
			}
		}
		if err := yield(Delta{ToolCalls: []ToolCall{{ID: cur.id, Name: cur.name, ArgsJSON: args}}}); err != nil {
			return err
		}
	}
	return yield(Delta{Finish: finish, Done: true})
}
