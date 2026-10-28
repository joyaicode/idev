// Command idevd is the local control-plane daemon: MCP over stdio for agents.
//
// Human approval stays on `idev gate approve` — this binary never exposes it
// (E5.1 / E5.2).
package main

import (
	"context"
	"fmt"
	"os"

	"github.com/idev/internal/adapters/mcpface"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "usage: idevd mcp | version")
		return 2
	}
	switch args[0] {
	case "version":
		fmt.Println(mcpface.Version)
		return 0
	case "mcp":
		return serveMCP()
	default:
		fmt.Fprintf(os.Stderr, "idevd: unknown command %q\n", args[0])
		return 2
	}
}

func serveMCP() int {
	ctx := context.Background()
	deps, err := mcpface.NewDeps(ctx)
	if err != nil {
		fmt.Fprintln(os.Stderr, "idevd:", err)
		return 1
	}
	defer deps.Store.Close()
	srv := mcpface.NewServer(deps)
	if err := srv.Run(ctx, &mcp.StdioTransport{}); err != nil {
		fmt.Fprintln(os.Stderr, "idevd mcp:", err)
		return 1
	}
	return 0
}
