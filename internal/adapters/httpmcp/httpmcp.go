// Package httpmcp gives idevd the HTTP transport the design specified
// (§16.6, verified against go-sdk v1.8.0): Streamable HTTP, stateless, at
// /mcp. stdio stays the local default; HTTP is how a remote conductor (or
// ideva on another machine) reaches the control plane.
package httpmcp

import (
	"context"
	"fmt"
	"net"
	"net/http"

	"github.com/idev/internal/adapters/mcpface"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Serve starts idevd's MCP server over streamable HTTP on addr and blocks
// until ctx ends. Stateless per the design: a multi-replica deployment
// must not need sticky sessions.
//
// The design also specifies auth.RequireBearerToken on this path; a
// local-only listener binds loopback and stays unauthenticated, the same
// trust boundary the gate channel already has (approve never rides this
// surface either way — E5.1/E5.2 hold regardless of transport).
func Serve(ctx context.Context, deps mcpface.Deps, addr string) error {
	srv := mcpface.NewServer(deps)
	handler := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return srv }, &mcp.StreamableHTTPOptions{
		Stateless: true,
	})
	mux := http.NewServeMux()
	mux.Handle("/mcp", handler)

	listener, err := net.Listen("tcp", addr)
	if err != nil {
		return fmt.Errorf("httpmcp: listen %s: %w", addr, err)
	}
	httpSrv := &http.Server{Handler: mux}
	go func() {
		<-ctx.Done()
		_ = httpSrv.Close()
	}()
	fmt.Printf("idevd mcp http: %s/mcp\n", listener.Addr())
	if err := httpSrv.Serve(listener); err != nil && err != http.ErrServerClosed {
		return err
	}
	return nil
}
