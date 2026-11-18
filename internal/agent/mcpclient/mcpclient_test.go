package mcpclient

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// The end-to-end test here is real: it launches the actual idevd binary
// (built from this repo) over stdio, lists its tools, and calls one. That
// is the exact path the ideva conductor will use — anything less would be
// testing the SDK, not this package.

func isolateData(t *testing.T) {
	t.Helper()
	// idevd resolves its database through IDEV_DATA (local.DataDir). The
	// default is the real ~/.idev — a test writing there leaves a live
	// run behind and the NEXT run_start is refused by the one-live-run
	// invariant, which is exactly the flake this line used to be.
	t.Setenv("IDEV_DATA", t.TempDir())
}

func idevdPath(t *testing.T) string {
	t.Helper()
	// go test runs in the package dir; the binary lands in bin/ next to
	// the module root, two levels up.
	path, err := filepath.Abs(filepath.Join("..", "..", "..", "bin", "idevd"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := exec.LookPath(path); err != nil {
		t.Skipf("idevd not built (%s): go build -o bin/idevd ./cmd/idevd", err)
	}
	return path
}

func TestConnectAndListIdevdTools(t *testing.T) {
	isolateData(t)
	idevd := idevdPath(t)
	sess, err := Connect(context.Background(), ServerSpec{
		Name:    "idev",
		Command: idevd + " mcp",
	})
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer sess.Close()
	set, err := sess.ToolSet(context.Background())
	if err != nil {
		t.Fatalf("toolset: %v", err)
	}
	if len(set) < 10 {
		t.Errorf("expected the control-plane toolset (16 tools), got %d", len(set))
	}
	// Names carry the server prefix — the namespace rule.
	for name := range set {
		if !strings.HasPrefix(name, "mcp_idev_") {
			t.Errorf("tool %q missing mcp_idev_ prefix", name)
		}
	}
	if _, ok := set["mcp_idev_run_get"]; !ok {
		t.Error("run_get not offered by idevd")
	}
}

func TestCallToolRoundTrip(t *testing.T) {
	isolateData(t)
	idevd := idevdPath(t)
	sess, err := Connect(context.Background(), ServerSpec{Name: "idev", Command: idevd + " mcp"})
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer sess.Close()
	set, err := sess.ToolSet(context.Background())
	if err != nil {
		t.Fatalf("toolset: %v", err)
	}
	tool, ok := set["mcp_idev_run_get"]
	if !ok {
		t.Fatal("run_get missing")
	}
	// A real round trip: start a run, then get it back. (Calling with a
	// nonexistent id exposes a known server-side gap — mcpface's errResult
	// skips its own output schema on the error branch and the SDK client
	// refuses the shape; recorded as a known issue, not fixed here.)
	start, ok := set["mcp_idev_run_start"]
	if !ok {
		t.Fatal("run_start missing")
	}
	created, err := start.Execute(context.Background(), json.RawMessage(
		`{"workflow_id":"lite-change","feature":"mcpclient-test","steps":[{"id":"one","kind":"shell.confirmed"}]}`))
	if err != nil {
		t.Fatalf("run_start: %v", err)
	}
	_ = created
	// The fresh run's id rides the result; parse it and round-trip run_get.
	var payload struct {
		RunID string `json:"run_id"`
	}
	for _, line := range strings.Split(created, "\n") {
		if err := json.Unmarshal([]byte(strings.TrimSpace(line)), &payload); err == nil && payload.RunID != "" {
			break
		}
	}
	if payload.RunID == "" {
		t.Fatalf("run_start result carried no run_id: %q", created)
	}
	out, err := tool.Execute(context.Background(), json.RawMessage(fmt.Sprintf(`{"run_id":%q}`, payload.RunID)))
	if err != nil {
		t.Fatalf("execute: %v", err)
	}
	if !strings.Contains(out, payload.RunID) {
		t.Errorf("run_get round trip lost the id: %q", out)
	}
}

func TestArgsObject(t *testing.T) {
	if argsObject(nil) != nil {
		t.Error("nil args must stay nil")
	}
	m := argsObject(json.RawMessage(`{"a":1}`))
	if m == nil || m["a"] != float64(1) {
		t.Errorf("args: %#v", m)
	}
	if argsObject(json.RawMessage(`not json`)) != nil {
		t.Error("bad args degrade to nil, not a crash")
	}
}
