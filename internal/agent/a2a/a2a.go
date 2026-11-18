// Package a2a is the agent-to-agent protocol surface: an Agent Card at
// /.well-known/agent-card.json and a JSON-RPC message/send endpoint, the
// two parts of the A2A spec an ideva deployment can honor today.
//
// Honest scope (the 2026-11-18 grilling put A2A on the list as a
// protocol surface, not a feature): this serves the card and accepts a
// message, running it as one delegation-shaped turn — the same shape the
// MCP server exposes. What A2A's richer verbs (tasks/streaming/push
// notifications) would add is recorded in the proposal as the follow-up;
// serving the card plus one synchronous verb is what "supports the
// protocol" can truthfully mean here.
package a2a

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
)

// Card is the Agent Card an A2A caller reads first. Field names are the
// spec's. Capabilities are declared for what this deployment actually
// serves — the same honesty rule as everywhere else in idev.
type Card struct {
	Name              string   `json:"name"`
	Description       string   `json:"description"`
	URL               string   `json:"url"`
	Version           string   `json:"version"`
	Capabilities      Caps     `json:"capabilities"`
	DefaultInputModes []string `json:"defaultInputModes"`
	DefaultOutputModes []string `json:"defaultOutputModes"`
	Skills            []Skill  `json:"skills"`
}

// Caps: what the endpoint serves. streaming/tasks/pushNotifications are
// false because they are not implemented — a caller reading the card
// must not be told otherwise.
type Caps struct {
	Streaming        bool `json:"streaming"`
	PushNotifications bool `json:"pushNotifications"`
	// StateTransitionHistory: not served either.
	StateTransitionHistory bool `json:"stateTransitionHistory"`
}

// Skill is one executor as the card presents it.
type Skill struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
}

// SendRequest is A2A's message/send body, the subset this accepts.
type SendRequest struct {
	// Message is the A2A Message; only parts of type text are read —
	// everything else a caller sends is data this endpoint does not
	// interpret, and saying so beats guessing.
	Message struct {
		Role  string `json:"role"`
		Parts []struct {
			Kind string `json:"kind"`
			Text string `json:"text"`
		} `json:"parts"`
	} `json:"message"`
}

// Text flattens the request's text parts.
func (r SendRequest) Text() string {
	var b strings.Builder
	for _, p := range r.Message.Parts {
		if p.Kind == "text" {
			b.WriteString(p.Text)
			b.WriteString("\n")
		}
	}
	return strings.TrimSpace(b.String())
}

// Handler serves the card and the one verb. handle is the caller's
// turn-runner: text in, answer text out — the same seam the MCP server's
// delegate tool uses, so A2A and MCP stay two thin protocols over one
// implementation.
type Handler struct {
	Card   Card
	Handle func(req SendRequest) (string, error)
}

// ServeHTTP implements http.Handler.
func (h Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.URL.Path == "/.well-known/agent-card.json":
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(h.Card)

	case r.URL.Path == "/" && r.Method == http.MethodPost:
		var req SendRequest
		body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if err != nil {
			http.Error(w, "read body: "+err.Error(), http.StatusBadRequest)
			return
		}
		if err := json.Unmarshal(body, &req); err != nil {
			http.Error(w, "bad JSON-RPC body: "+err.Error(), http.StatusBadRequest)
			return
		}
		if req.Text() == "" {
			http.Error(w, "message carries no text part", http.StatusUnprocessableEntity)
			return
		}
		answer, err := h.Handle(req)
		if err != nil {
			// A2A errors ride JSON-RPC; the code layer keeps that simple
			// by mapping any failure to one error envelope.
			w.WriteHeader(http.StatusInternalServerError)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"jsonrpc": "2.0",
				"error":   map[string]any{"code": -32000, "message": err.Error()},
			})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"jsonrpc": "2.0",
			"result": map[string]any{
				"kind": "message",
				"role": "agent",
				"parts": []map[string]any{
					{"kind": "text", "text": answer},
				},
			},
		})

	default:
		http.NotFound(w, r)
	}
}

// NewCard builds the card from what is actually mounted. executorDescs
// carries name+description pairs; the skill list is the card's way to say
// who answers.
func NewCard(url string, version string, executorDescs [][2]string) Card {
	card := Card{
		Name:              "ideva",
		Description:       "idev 端到端交付导体的第一方 agent：五个执行者委派面，A2A 同步 message/send。",
		URL:               url,
		Version:           version,
		Capabilities:      Caps{},
		DefaultInputModes: []string{"text"},
		DefaultOutputModes: []string{"text"},
	}
	for _, d := range executorDescs {
		card.Skills = append(card.Skills, Skill{ID: d[0], Name: d[0], Description: d[1]})
	}
	return card
}
