package mcpface_test

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"slices"
	"testing"

	"github.com/idev/internal/adapters/kindreg"
	"github.com/idev/internal/adapters/local"
	"github.com/idev/internal/adapters/mcpface"
	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/app/baselinesvc"
	"github.com/idev/internal/app/leasesvc"
	"github.com/idev/internal/app/runsvc"
	"github.com/idev/pkg/schemas"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestToolsListCoversSurfaceAndOmitsGateApprove(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	kinds := kindreg.MustLoad()
	srv := mcpface.NewServer(mcpface.Deps{
		Store: st,
		Runs:  runsvc.Service{Store: st, Clock: local.Clock{}, IDs: local.IDs{}, Registry: kinds},
		Lease: leasesvc.Service{Store: st, Clock: local.Clock{}, IDs: local.IDs{}, Kinds: kinds},
		Base:  baselinesvc.Service{Store: st, Clock: local.Clock{}},
	})

	ct, stTransport := mcp.NewInMemoryTransports()
	ss, err := srv.Connect(ctx, stTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer ss.Close()

	client := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "v0"}, nil)
	cs, err := client.Connect(ctx, ct, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer cs.Close()

	tools, err := cs.ListTools(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	got := make([]string, 0, len(tools.Tools))
	for _, tool := range tools.Tools {
		got = append(got, tool.Name)
		if tool.Name == "gate_approve" || tool.Name == "gate_reject" {
			t.Fatalf("MCP surface must not expose %s", tool.Name)
		}
	}
	for _, want := range mcpface.ToolNames() {
		if !slices.Contains(got, want) {
			t.Errorf("missing tool %q in %v", want, got)
		}
	}
	for _, prefix := range []string{"run_", "step_", "delegation_", "lease_", "baseline_"} {
		found := false
		for _, name := range got {
			if len(name) >= len(prefix) && name[:len(prefix)] == prefix {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("no tool with prefix %q", prefix)
		}
	}
}

func TestToolSchemasComeFromAPIContracts(t *testing.T) {
	ctx := context.Background()
	st, err := sqlite.Open(ctx, filepath.Join(t.TempDir(), "idev.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	kinds := kindreg.MustLoad()
	srv := mcpface.NewServer(mcpface.Deps{
		Store: st,
		Runs:  runsvc.Service{Store: st, Clock: local.Clock{}, IDs: local.IDs{}, Registry: kinds},
		Lease: leasesvc.Service{Store: st, Clock: local.Clock{}, IDs: local.IDs{}, Kinds: kinds},
		Base:  baselinesvc.Service{Store: st, Clock: local.Clock{}},
	})
	ct, stTransport := mcp.NewInMemoryTransports()
	ss, err := srv.Connect(ctx, stTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer ss.Close()
	client := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "v0"}, nil)
	cs, err := client.Connect(ctx, ct, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer cs.Close()
	tools, err := cs.ListTools(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, tool := range tools.Tools {
		want := schemas.MustTool(tool.Name + ".input")
		gotRaw, err := json.Marshal(tool.InputSchema)
		if err != nil {
			t.Fatal(err)
		}
		wantRaw, err := json.Marshal(want)
		if err != nil {
			t.Fatal(err)
		}
		var gotObj, wantObj any
		_ = json.Unmarshal(gotRaw, &gotObj)
		_ = json.Unmarshal(wantRaw, &wantObj)
		// Title/$id/$schema may be stripped by the SDK; require type+required to match.
		gm, _ := gotObj.(map[string]any)
		wm, _ := wantObj.(map[string]any)
		if gm == nil || wm == nil {
			t.Fatalf("%s: schemas not objects", tool.Name)
		}
		if gm["type"] != wm["type"] {
			t.Errorf("%s type = %v, want %v", tool.Name, gm["type"], wm["type"])
		}
		if fmt.Sprint(gm["required"]) != fmt.Sprint(wm["required"]) {
			t.Errorf("%s required = %v, want %v", tool.Name, gm["required"], wm["required"])
		}
	}
}
