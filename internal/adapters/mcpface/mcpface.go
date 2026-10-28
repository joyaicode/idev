// Package mcpface is the agent-facing MCP tool surface for idevd (E5.1).
//
// Human approval stays off this surface (E5.2): gate_approve / gate_reject
// are never registered. Agents use gate_request + gate_status; people approve
// through the idev CLI.
package mcpface

import (
	"context"
	"fmt"
	"path/filepath"
	"time"

	"github.com/idev/internal/adapters/kindreg"
	"github.com/idev/internal/adapters/local"
	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/adapters/ticketbaseline"
	"github.com/idev/internal/app/baselinesvc"
	"github.com/idev/internal/app/leasesvc"
	"github.com/idev/internal/app/runsvc"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/schemas"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// Version is reported in the MCP Implementation block.
const Version = "0.1.0-e5.1"

// Deps are the services the tool handlers need. Tests inject a temp store.
type Deps struct {
	Store *sqlite.Store
	Runs  runsvc.Service
	Lease leasesvc.Service
	Base  baselinesvc.Service
}

// NewDeps opens the default data dir and wires services.
func NewDeps(ctx context.Context) (Deps, error) {
	data, err := local.DataDir()
	if err != nil {
		return Deps{}, err
	}
	st, err := sqlite.Open(ctx, filepath.Join(data, "idev.db"))
	if err != nil {
		return Deps{}, err
	}
	kinds := kindreg.MustLoad()
	d := Deps{
		Store: st,
		Runs:  runsvc.Service{Store: st, Clock: local.Clock{}, IDs: local.IDs{}, Registry: kinds},
		Lease: leasesvc.Service{Store: st, Clock: local.Clock{}, IDs: local.IDs{}, Kinds: kinds},
		Base:  baselinesvc.Service{Store: st, Clock: local.Clock{}},
	}
	return d, nil
}

// NewServer builds the MCP server with the agent tool surface.
func NewServer(d Deps) *mcp.Server {
	srv := mcp.NewServer(&mcp.Implementation{Name: "idev", Version: Version}, nil)
	register(srv, d)
	return srv
}

// ToolNames is the agent-visible catalogue. Tests lock that gate_approve is
// absent and that run / step / delegation / lease / baseline are present.
func ToolNames() []string {
	return []string{
		"run_start", "run_get", "run_apply",
		"step_record",
		"delegation_allocate", "delegation_get",
		"lease_acquire", "lease_release", "lease_check",
		"baseline_verify", "baseline_sealed",
		"gate_request", "gate_status",
	}
}

func register(srv *mcp.Server, d Deps) {
	ro := mcp.ToolAnnotations{ReadOnlyHint: true, IdempotentHint: true}

	mcp.AddTool(srv, &mcp.Tool{
		Name: "run_start",
		InputSchema: schemas.MustTool("run_start.input"),
		OutputSchema: schemas.MustTool("run_start.output"),
		Description: "Start a live run in SQLite and return its id",
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in runStartIn) (*mcp.CallToolResult, runStartOut, error) {
		steps := make([]run.Step, 0, len(in.Steps))
		for _, s := range in.Steps {
			steps = append(steps, run.Step{ID: s.ID, Kind: s.Kind})
		}
		out, err := d.Runs.Start(ctx, runsvc.StartParams{
			WorkflowID: in.WorkflowID, FeatureID: in.Feature, Feature: in.Feature,
			Steps: steps,
			Actor: ports.Principal{Handle: "conductor@mcp", Kind: "agent", OwnerHandle: "system"},
		})
		if err != nil {
			return errResult(err), runStartOut{}, nil
		}
		return nil, runStartOut{RunID: out.ID, Status: string(out.Status())}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "run_get",
		InputSchema: schemas.MustTool("run_get.input"),
		OutputSchema: schemas.MustTool("run_get.output"),
		Description: "Load a run by id", Annotations: &ro,
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in runIDIn) (*mcp.CallToolResult, map[string]any, error) {
		var loaded run.Run
		err := d.Store.InTx(ctx, func(tx ports.Tx) error {
			r, _, err := tx.Runs().Get(ctx, in.RunID)
			loaded = r
			return err
		})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{"run_id": loaded.ID, "feature": loaded.Feature, "status": string(loaded.Status())}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "run_apply",
		InputSchema: schemas.MustTool("run_apply.input"),
		OutputSchema: schemas.MustTool("run_apply.output"),
		Description: "Apply a domain event to a live run",
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in runApplyIn) (*mcp.CallToolResult, map[string]any, error) {
		next, err := d.Runs.Apply(ctx, in.RunID, run.Event{
			Kind: run.EventKind(in.Event), Actor: run.ActorSystem, StepID: in.StepID,
			Outcome: run.StepState(in.Outcome), Note: in.Note, Agent: in.Agent,
		}, ports.Principal{Handle: "conductor@mcp", Kind: "agent", OwnerHandle: "system"})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{"run_id": next.ID, "status": string(next.Status())}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "step_record",
		InputSchema: schemas.MustTool("step_record.input"),
		OutputSchema: schemas.MustTool("step_record.output"),
		Description: "Record a step outcome via Apply (DelegationReturned / GateApproved path)",
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in stepRecordIn) (*mcp.CallToolResult, map[string]any, error) {
		ev := run.Event{
			Kind: run.EvDelegationReturned, Actor: run.ActorSystem, StepID: in.StepID,
			Outcome: run.StepState(in.Status), Note: in.Note, Evidence: in.Evidence, Agent: in.Agent,
		}
		if in.Event != "" {
			ev.Kind = run.EventKind(in.Event)
		}
		next, err := d.Runs.Apply(ctx, in.RunID, ev, ports.Principal{Handle: "conductor@mcp", Kind: "agent"})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{"run_id": next.ID, "status": string(next.Status())}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "delegation_allocate",
		InputSchema: schemas.MustTool("delegation_allocate.input"),
		OutputSchema: schemas.MustTool("delegation_allocate.output"),
		Description: "Server-assign the next attempt for a step (I-5)",
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in delegAllocIn) (*mcp.CallToolResult, map[string]any, error) {
		if in.Feature != "" {
			_ = d.Store.ProjectExternalRun(ctx, in.RunID, in.Feature)
		}
		id := in.ID
		if id == "" {
			id = d.Runs.IDs.New()
		}
		var assigned ports.Delegation
		err := d.Store.InTx(ctx, func(tx ports.Tx) error {
			rec := ports.Delegation{
				ID: id, RunID: in.RunID, StepID: in.StepID, Attempt: 0,
				Agent: in.Agent, Packet: []byte("{}"), State: "issued",
				IssuedAt: time.Now().UTC(),
			}
			if err := tx.Delegations().Insert(ctx, rec); err != nil {
				return err
			}
			var err error
			assigned, err = tx.Delegations().Get(ctx, id)
			return err
		})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{
			"id": assigned.ID, "run_id": assigned.RunID, "step_id": assigned.StepID,
			"attempt": assigned.Attempt, "agent": assigned.Agent,
		}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "delegation_get",
		InputSchema: schemas.MustTool("delegation_get.input"),
		OutputSchema: schemas.MustTool("delegation_get.output"),
		Description: "Load a delegation by id", Annotations: &ro,
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in idIn) (*mcp.CallToolResult, map[string]any, error) {
		var rec ports.Delegation
		err := d.Store.InTx(ctx, func(tx ports.Tx) error {
			var err error
			rec, err = tx.Delegations().Get(ctx, in.ID)
			return err
		})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{
			"id": rec.ID, "run_id": rec.RunID, "step_id": rec.StepID,
			"attempt": rec.Attempt, "agent": rec.Agent, "state": rec.State,
		}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "lease_acquire",
		InputSchema: schemas.MustTool("lease_acquire.input"),
		OutputSchema: schemas.MustTool("lease_acquire.output"),
		Description: "Acquire a write or verify lease",
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in leaseAcquireIn) (*mcp.CallToolResult, map[string]any, error) {
		purpose := lease.PurposeWrite
		if in.Purpose == "verify" {
			purpose = lease.PurposeVerify
		}
		out, err := d.Lease.Acquire(ctx, leasesvc.AcquireParams{
			Feature: in.Feature, RunID: in.RunID, StepID: in.StepID,
			Agent: in.Agent, Purpose: purpose, TicketDir: in.TicketDir,
			WritePaths: in.WritePaths,
			Actor:      ports.Principal{Handle: in.Agent, Kind: "agent"},
		})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{
			"lease_id": out.Lease.ID, "fencing": out.Lease.Fencing, "token": out.Token,
			"expires_at": out.Lease.ExpiresAt.Format(time.RFC3339),
		}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "lease_release",
		InputSchema: schemas.MustTool("lease_release.input"),
		OutputSchema: schemas.MustTool("lease_release.output"),
		Description: "Release a held lease",
		Annotations: &mcp.ToolAnnotations{IdempotentHint: true},
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in leaseReleaseIn) (*mcp.CallToolResult, map[string]any, error) {
		err := d.Lease.Release(ctx, in.LeaseID, in.Token, ports.Principal{Handle: "conductor@mcp", Kind: "agent"})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{"released": true}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "lease_check",
		InputSchema: schemas.MustTool("lease_check.input"),
		OutputSchema: schemas.MustTool("lease_check.output"),
		Description: "Report which paths fall outside a lease", Annotations: &ro,
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in leaseCheckIn) (*mcp.CallToolResult, map[string]any, error) {
		var l lease.Lease
		err := d.Store.InTx(ctx, func(tx ports.Tx) error {
			var err error
			l, err = tx.Leases().Get(ctx, in.LeaseID)
			return err
		})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{
			"lease_id": l.ID, "agent": l.Agent, "fencing": l.Fencing,
			"write_paths": l.WritePaths, "outside": l.Outside(in.Paths),
		}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "baseline_verify",
		InputSchema: schemas.MustTool("baseline_verify.input"),
		OutputSchema: schemas.MustTool("baseline_verify.output"),
		Description: "Recompute the ticket manifest against the sealed row", Annotations: &ro,
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in baselineVerifyIn) (*mcp.CallToolResult, map[string]any, error) {
		current, err := ticketbaseline.FromTicket(in.Feature, in.Ticket, 0, time.Now().UTC())
		if err != nil {
			return errResult(err), nil, nil
		}
		out, err := d.Base.Check(ctx, in.Feature, current, ports.Principal{
			Handle: "conductor@mcp", Kind: "agent", OwnerHandle: "system",
		})
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{"verdict": string(out.Verdict), "line": out.Line}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "baseline_sealed",
		InputSchema: schemas.MustTool("baseline_sealed.input"),
		OutputSchema: schemas.MustTool("baseline_sealed.output"),
		Description: "Return the sealed baseline row if any", Annotations: &ro,
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in featureIn) (*mcp.CallToolResult, map[string]any, error) {
		m, err := d.Base.Sealed(ctx, in.Feature)
		if err != nil {
			return errResult(err), nil, nil
		}
		return nil, map[string]any{
			"feature": in.Feature, "revision": m.Revision, "manifest_root": string(m.ManifestRoot),
		}, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "gate_request",
		InputSchema: schemas.MustTool("gate_request.input"),
		OutputSchema: schemas.MustTool("gate_request.output"),
		Description: "Open a human gate (approve stays on the CLI, not MCP)",
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in map[string]any) (*mcp.CallToolResult, map[string]any, error) {
		return errResult(fmt.Errorf("gate_request: use idev gate request for now; MCP binding lands with E5.3")), nil, nil
	})

	mcp.AddTool(srv, &mcp.Tool{
		Name: "gate_status",
		InputSchema: schemas.MustTool("gate_status.input"),
		OutputSchema: schemas.MustTool("gate_status.output"),
		Description: "Read a gate's status", Annotations: &ro,
	}, func(ctx context.Context, _ *mcp.CallToolRequest, in idIn) (*mcp.CallToolResult, map[string]any, error) {
		return errResult(fmt.Errorf("gate_status: use idev gate status for now; MCP binding lands with E5.3")), nil, nil
	})
}

func errResult(err error) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		IsError: true,
		Content: []mcp.Content{&mcp.TextContent{Text: "BLOCKED " + err.Error()}},
	}
}

// --- input / output shapes ---------------------------------------------------

type runStartIn struct {
	WorkflowID string     `json:"workflow_id"`
	Feature    string     `json:"feature"`
	Steps      []stepSpec `json:"steps"`
}
type stepSpec struct {
	ID   string `json:"id"`
	Kind string `json:"kind"`
}
type runStartOut struct {
	RunID  string `json:"run_id"`
	Status string `json:"status"`
}
type runIDIn struct {
	RunID string `json:"run_id"`
}
type runApplyIn struct {
	RunID   string `json:"run_id"`
	Event   string `json:"event"`
	StepID  string `json:"step_id"`
	Outcome string `json:"outcome"`
	Note    string `json:"note"`
	Agent   string `json:"agent"`
}
type stepRecordIn struct {
	RunID    string `json:"run_id"`
	StepID   string `json:"step_id"`
	Status   string `json:"status"`
	Evidence string `json:"evidence"`
	Note     string `json:"note"`
	Agent    string `json:"agent"`
	Event    string `json:"event"`
}
type delegAllocIn struct {
	RunID   string `json:"run_id"`
	StepID  string `json:"step_id"`
	Agent   string `json:"agent"`
	Feature string `json:"feature"`
	ID      string `json:"id"`
}
type idIn struct {
	ID string `json:"id"`
}
type leaseAcquireIn struct {
	Feature    string   `json:"feature"`
	RunID      string   `json:"run_id"`
	StepID     string   `json:"step_id"`
	Agent      string   `json:"agent"`
	Purpose    string   `json:"purpose"`
	TicketDir  string   `json:"ticket_dir"`
	WritePaths []string `json:"write_paths"`
}
type leaseReleaseIn struct {
	LeaseID string `json:"lease_id"`
	Token   string `json:"token"`
}
type leaseCheckIn struct {
	LeaseID string   `json:"lease_id"`
	Paths   []string `json:"paths"`
}
type baselineVerifyIn struct {
	Feature string `json:"feature"`
	Ticket  string `json:"ticket"`
}
type featureIn struct {
	Feature string `json:"feature"`
}
