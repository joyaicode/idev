// Package mcpclient is ideva's client side of MCP: the control-plane tools
// (idevd's sixteen) become loop tools the conductor can call, and any other
// MCP server configured the same way joins the tool set too.
//
// The go-sdk client surface: NewClient → Connect(StdioTransport{command})
// → ListTools / CallTool. Errors arrive as CallToolResult.IsError, the
// same convention the server side sets (mcpface §16.1: code/message/hint
// in structuredContent) — so a BLOCKED from the control plane is a tool
// result the model reads and reasons about, not a wire failure.
package mcpclient

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"sync"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// ServerSpec is one MCP server to mount: a command to launch over stdio.
type ServerSpec struct {
	Name    string
	Command string   // argv, e.g. ["idevd", "mcp"]
	Env     []string // extra env, KEY=VALUE
}

// Session is one connected MCP server.
type Session struct {
	spec    ServerSpec
	session *mcp.ClientSession
}

// Connect launches the server and completes the MCP handshake. The client
// implementation block names ideva so the server's logs say who called.
func Connect(ctx context.Context, spec ServerSpec) (*Session, error) {
	impl := &mcp.Implementation{Name: "ideva", Version: "0.1.0"}
	client := mcp.NewClient(impl, nil)
	fields := strings.Fields(spec.Command)
	cmd := exec.Command(fields[0], fields[1:]...)
	if len(spec.Env) > 0 {
		cmd.Env = append(cmd.Environ(), spec.Env...)
	}
	// CommandTransport: the SDK owns the subprocess lifecycle (stdin closed
	// → wait → SIGTERM), which is exactly the lifecycle a mounted server
	// should have — not one the caller hand-rolls.
	sess, err := client.Connect(ctx, &mcp.CommandTransport{Command: cmd}, nil)
	if err != nil {
		return nil, fmt.Errorf("mcpclient: connect %s: %w", spec.Name, err)
	}
	return &Session{spec: spec, session: sess}, nil
}

// Close ends the session.
func (s *Session) Close() error {
	return s.session.Close()
}

// ToolSet lists the server's tools and wraps each one as a loop-callable
// tool. The wrapper marshals args, calls, and returns the text content
// joined; a tool error is returned as the result text (the model must see
// BLOCKED, not a crash) with a prefix naming it.
func (s *Session) ToolSet(ctx context.Context) (map[string]MCPTool, error) {
	list, err := s.session.ListTools(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("mcpclient: list %s: %w", s.spec.Name, err)
	}
	out := map[string]MCPTool{}
	for _, tool := range list.Tools {
		name := tool.Name
		desc := strings.TrimSpace(tool.Description)
		var params json.RawMessage
		if tool.InputSchema != nil {
			blob, err := json.Marshal(tool.InputSchema)
			if err == nil {
				params = blob
			}
		}
		if len(params) == 0 {
			params = json.RawMessage(`{"type":"object"}`)
		}
		// The map key is the prefixed name: two servers with the same
		// tool name must not shadow each other, and the key is where
		// that guarantee actually lives.
		remote := MCPTool{
			Server:       s.spec.Name,
			ToolName:     name,
			Desc:         desc,
			Params:       params,
			ReadOnlyHint: hasReadOnlyHint(tool),
			session:      s,
			serverPrefix: s.spec.Name,
		}
		out[remote.Name()] = remote
	}
	return out, nil
}

func hasReadOnlyHint(tool *mcp.Tool) bool {
	return tool != nil && tool.Annotations != nil && tool.Annotations.ReadOnlyHint
}

// MCPTool is one remote tool exposed to the loop. Name() prefixes the
// server name (mcp_<server>_<tool>) so two servers with same-named tools
// cannot shadow each other — the namespace is the host's to keep.
type MCPTool struct {
	Server    string
	ToolName  string
	Desc      string
	Params    json.RawMessage
	// Read-only per the server's own annotation; prefixed fields are the
	// declaration, the method is the loop interface.
	ReadOnlyHint bool

	session      *Session
	serverPrefix string
}

// Name implements loop.Tool.
func (t MCPTool) Name() string {
	return "mcp_" + t.Server + "_" + t.ToolName
}

// Description implements loop.Tool.
func (t MCPTool) Description() string {
	return fmt.Sprintf("[%s] %s", t.Server, t.Desc)
}

// ParametersJSON implements loop.Tool.
func (t MCPTool) ParametersJSON() json.RawMessage {
	return t.Params
}

// ReadOnly implements loop.Tool.
func (t MCPTool) ReadOnly() bool { return t.ReadOnlyHint }

// Execute implements loop.Tool: one CallTool round trip.
func (t MCPTool) Execute(ctx context.Context, args json.RawMessage) (string, error) {
	result, err := t.session.session.CallTool(ctx, &mcp.CallToolParams{
		Name:      t.ToolName,
		Arguments: argsObject(args),
	})
	if err != nil {
		return "", fmt.Errorf("mcpclient: call %s.%s: %w", t.Server, t.ToolName, err)
	}
	var b strings.Builder
	for _, block := range result.Content {
		if text, ok := block.(*mcp.TextContent); ok {
			b.WriteString(text.Text)
			b.WriteString("\n")
		}
	}
	if result.IsError {
		// The server said no. The model sees it as data and decides what
		// to do — exactly the deny-with-reason pattern the kernel's hooks
		// already follow.
		return fmt.Sprintf("ERROR: %s", strings.TrimRight(b.String(), "\n")), nil
	}
	return b.String(), nil
}

func argsObject(args json.RawMessage) map[string]any {
	if len(args) == 0 {
		return nil
	}
	var m map[string]any
	if err := json.Unmarshal(args, &m); err != nil {
		return nil
	}
	return m
}

// Manager holds all connected sessions; ideva closes them on exit.
type Manager struct {
	mu       sync.Mutex
	sessions []*Session
}

// ConnectAll dials every spec; a server that fails to start is a returned
// error entry, not a dead manager — the conductor runs with what mounted.
func (m *Manager) ConnectAll(ctx context.Context, specs []ServerSpec) (map[string]MCPTool, []error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	tools := map[string]MCPTool{}
	var errs []error
	for _, spec := range specs {
		sess, err := Connect(ctx, spec)
		if err != nil {
			errs = append(errs, err)
			continue
		}
		m.sessions = append(m.sessions, sess)
		set, err := sess.ToolSet(ctx)
		if err != nil {
			errs = append(errs, err)
			continue
		}
		for name, tool := range set {
			tools[name] = tool
		}
	}
	return tools, errs
}

// Close ends every session.
func (m *Manager) Close() {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, s := range m.sessions {
		_ = s.Close()
	}
	m.sessions = nil
}
