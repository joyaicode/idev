// Package server exposes ideva itself as an MCP server: the five
// executors' delegation surface, over stdio or the same HTTP transport
// idevd uses. Claude Code, Cursor, or any MCP host can then drive the
// executors without the ideva REPL — the "ideva as third host" story
// inverted: the executors are a mountable toolset, not a walled garden.
//
// Two tools, deliberately: `delegate` (one step to one executor, the
// brief verbatim) and `executors` (list who is mounted, with their tool
// whitelists). Everything else the control plane already offers over its
// own MCP surface; this server only adds what only this host can do —
// running the executors under host-enforced tool whitelists.
package server

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/idev/internal/agent/delegate"
	"github.com/idev/internal/agent/loop"
	"github.com/idev/internal/agent/provider"
	"github.com/idev/internal/agent/session"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Deps are what the tools close over.
type Deps struct {
	Registry  *delegate.Registry
	Provider  provider.Provider
	Sessions  session.Store
	Tools     map[string]loop.Tool
	Model     string
	Repo      string
	MaxTurns  int
}

// NewServer builds the MCP server with the two tools.
func NewServer(d Deps) *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{Name: "ideva", Version: "0.1.0"}, nil)
	ro := mcp.ToolAnnotations{ReadOnlyHint: true, IdempotentHint: true}

	mcp.AddTool(srv, &mcp.Tool{
		Name:        "executors",
		Description: "List the mounted executors (idev-coder 等) and each one's enforced tool whitelist.",
		Annotations: &ro,
	}, func(ctx context.Context, _ *mcp.CallToolRequest, _ struct{}) (*mcp.CallToolResult, executorsOut, error) {
		names := make([]string, 0, len(d.Registry.Executors))
		for name := range d.Registry.Executors {
			names = append(names, name)
		}
		sort.Strings(names)
		rows := make([]executorRow, 0, len(names))
		for _, name := range names {
			ex := d.Registry.Executors[name]
			rows = append(rows, executorRow{Name: name, Tools: ex.Tools})
		}
		return nil, executorsOut{Executors: rows}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "delegate",
		Description: "把一个 step 的委派包交给一个执行者，起独立子会话执行，回报经过 " +
			"STATUS/EVIDENCE 形状检查。brief 必须是完整委派包（agents.md「委派包」9+N 行）。",
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in delegateIn) (*mcp.CallToolResult, delegateOut, error) {
		if strings.TrimSpace(in.Brief) == "" {
			return errText("BLOCKED brief is required: the 9+N-line delegation packet"), delegateOut{}, nil
		}
		if _, ok := d.Registry.Executors[in.Executor]; !ok {
			return errText(fmt.Sprintf("BLOCKED unknown executor %q; call executors for the mounted list", in.Executor)), delegateOut{}, nil
		}
		parent := session.Session{Kind: "main", Agent: "mcp-caller"}
		if err := d.Sessions.CreateSession(ctx, &parent); err != nil {
			return errText("BLOCKED " + err.Error()), delegateOut{}, nil
		}
		rep, err := delegate.Run(ctx, delegate.Options{
			Registry:      d.Registry,
			Executor:      in.Executor,
			Provider:      d.Provider,
			Sessions:      d.Sessions,
			Tools:         d.Tools,
			ParentSession: parent.ID,
			Brief:         in.Brief,
			Model:         d.Model,
			Repo:          d.Repo,
			MaxTurns:      d.MaxTurns,
		})
		if err != nil {
			return errText("BLOCKED " + err.Error()), delegateOut{}, nil
		}
		return nil, delegateOut{
			Status:    rep.Status,
			Evidence:  rep.Evidence,
			Text:      rep.Text,
			SessionID: rep.SessionID,
		}, nil
	})
	return srv
}

type executorsOut struct {
	Executors []executorRow `json:"executors"`
}

type executorRow struct {
	Name  string   `json:"name"`
	Tools []string `json:"tools"`
}

type delegateIn struct {
	Executor string `json:"executor"`
	Brief    string `json:"brief"`
}

type delegateOut struct {
	Status    string `json:"status"`
	Evidence  string `json:"evidence,omitempty"`
	Text      string `json:"text"`
	SessionID string `json:"session_id"`
}

func errText(text string) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		IsError: true,
		Content: []mcp.Content{&mcp.TextContent{Text: text}},
	}
}

var _ = json.RawMessage{} // keep json import for the shape files' convention
