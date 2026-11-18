package httpmcp

import (
	"context"
	"fmt"
	"net"
	"testing"
	"time"

	"github.com/idev/internal/adapters/mcpface"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// End-to-end: serve idevd's real toolset over HTTP, list tools with the
// real SDK client. That is the same path a remote conductor takes — a
// mock here would test the SDK, not this package.

func freeAddr(t *testing.T) string {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	addr := l.Addr().String()
	l.Close()
	return addr
}

func TestServeListsToolsOverHTTP(t *testing.T) {
	deps, err := mcpface.NewDeps(context.Background())
	if err != nil {
		t.Skipf("idevd deps unavailable here: %v", err)
	}
	defer deps.Store.Close()
	addr := freeAddr(t)
	go func() { _ = Serve(context.Background(), deps, addr) }()
	// Poll until the listener is up: Serve binds inside a goroutine.
	url := ""
	for i := 0; i < 50; i++ {
		conn, err := net.DialTimeout("tcp", addr, 100*time.Millisecond)
		if err == nil {
			conn.Close()
			url = fmt.Sprintf("http://%s/mcp", addr)
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if url == "" {
		t.Fatal("server never came up")
	}

	client := mcp.NewClient(&mcp.Implementation{Name: "test-ideva", Version: "0"}, nil)
	transport := &mcp.StreamableClientTransport{Endpoint: url}
	sess, err := client.Connect(context.Background(), transport, nil)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer sess.Close()
	list, err := sess.ListTools(context.Background(), nil)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list.Tools) < 10 {
		t.Errorf("expected the control-plane toolset, got %d tools", len(list.Tools))
	}

	// A second connection over the same listener must also work: stateless
	// means no session stickiness (GET/DELETE 405 per the SDK docs, but
	// each POST initializes fresh).
	sess2, err := client.Connect(context.Background(), &mcp.StreamableClientTransport{Endpoint: url}, nil)
	if err != nil {
		t.Fatalf("second connect: %v", err)
	}
	defer sess2.Close()
	if _, err := sess2.ListTools(context.Background(), nil); err != nil {
		t.Fatalf("second list: %v", err)
	}
}
