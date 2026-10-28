package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/idev/internal/adapters/local"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/adapters/ticketbaseline"
	"github.com/idev/internal/app/baselinesvc"
	"github.com/idev/internal/domain/baseline"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
	"go.yaml.in/yaml/v3"
)

func (a app) baselineSeal(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("baseline seal", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	feature := fs.String("feature", "", "feature id")
	gateID := fs.String("gate", "", "approved sealed gate id")
	ticket := fs.String("ticket", "", "ticket directory with baseline.yaml")
	revision := fs.Int("revision", 0, "override revision (default: from baseline.yaml)")
	by := fs.String("by", "", "actor handle doing the seal")
	project := fs.Bool("project-yaml", true, "write sealed: true into baseline.yaml as a projection")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *feature == "" || *gateID == "" || *ticket == "" || *by == "" {
		return usageError{"baseline seal needs --feature, --gate, --ticket and --by"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	m, err := ticketbaseline.FromTicket(*feature, *ticket, *revision, time.Now().UTC())
	if err != nil {
		return err
	}
	svc := baselinesvc.Service{Store: e.store, Clock: local.Clock{}}
	sealed, err := svc.Seal(ctx, baselinesvc.SealParams{
		Feature:  *feature,
		Manifest: m,
		GateID:   *gateID,
		Actor:    ports.Principal{Handle: *by, Kind: "human"},
	})
	if err != nil {
		return err
	}
	if *project {
		if err := projectSealedYAML(filepath.Join(*ticket, "baseline.yaml"), true); err != nil {
			return err
		}
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"feature":       *feature,
		"revision":      sealed.Revision,
		"manifest_root": string(sealed.ManifestRoot),
		"status":        "sealed",
	})
}

func (a app) baselineVerify(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("baseline verify", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	feature := fs.String("feature", "", "feature id")
	ticket := fs.String("ticket", "", "ticket directory with baseline.yaml")
	by := fs.String("by", "conductor@claude", "actor handle for the audit event")
	blockRun := fs.Bool("block-run", true, "on drift, Apply BaselineDriftDetected to the live run")
	workflow := fs.String("workflow", "", "workflow id of the live run to block (optional)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *feature == "" || *ticket == "" {
		return usageError{"baseline verify needs --feature and --ticket"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	current, err := ticketbaseline.FromTicket(*feature, *ticket, 0, time.Now().UTC())
	if err != nil {
		return err
	}
	svc := baselinesvc.Service{Store: e.store, Clock: local.Clock{}}
	out, err := svc.Check(ctx, *feature, current, ports.Principal{
		Handle: *by, Kind: "agent", OwnerHandle: "system",
	})
	if err != nil {
		var ce *ports.ConflictError
		if errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound {
			return fmt.Errorf("no sealed baseline for %s", *feature)
		}
		return err
	}
	payload := map[string]any{
		"feature": *feature,
		"verdict": string(out.Verdict),
		"line":    out.Line,
	}
	if out.Verdict == baseline.VerdictDrift && *blockRun {
		if err := a.blockRunOnDrift(ctx, e, *feature, *workflow, out.Line); err != nil {
			payload["block_error"] = err.Error()
		} else {
			payload["run_blocked"] = true
		}
	}
	enc := json.NewEncoder(a.stdout)
	if err := enc.Encode(payload); err != nil {
		return err
	}
	if out.Verdict == baseline.VerdictDrift {
		return fmt.Errorf("%s", out.Line)
	}
	return nil
}

func (a app) baselineSealed(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("baseline sealed", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	feature := fs.String("feature", "", "feature id")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *feature == "" {
		return usageError{"baseline sealed needs --feature"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	svc := baselinesvc.Service{Store: e.store, Clock: local.Clock{}}
	m, err := svc.Sealed(ctx, *feature)
	if err != nil {
		var ce *ports.ConflictError
		if errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound {
			return fmt.Errorf("no sealed baseline for %s", *feature)
		}
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"feature":       *feature,
		"revision":      m.Revision,
		"manifest_root": string(m.ManifestRoot),
		"status":        "sealed",
	})
}

func (a app) blockRunOnDrift(ctx context.Context, e env, feature, workflow, line string) error {
	if workflow == "" {
		// Drift is still reported; without a workflow the live run is ambiguous.
		return nil
	}
	var live run.Run
	err := e.store.InTx(ctx, func(tx ports.Tx) error {
		r, _, err := tx.Runs().FindLive(ctx, feature, workflow)
		if err != nil {
			return err
		}
		live = r
		return nil
	})
	if err != nil {
		var ce *ports.ConflictError
		if errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound {
			return nil
		}
		return err
	}
	_, err = e.runs.Apply(ctx, live.ID, run.Event{
		Kind: run.EvBaselineDriftDetected, Actor: run.ActorSystem, Note: line,
	}, ports.Principal{Handle: "system", Kind: "system"})
	return err
}

func projectSealedYAML(path string, sealed bool) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return err
	}
	if sealed {
		doc["sealed"] = true
	} else {
		doc["sealed"] = false
	}
	out, err := yaml.Marshal(doc)
	if err != nil {
		return err
	}
	return os.WriteFile(path, out, 0o644)
}

func (a app) delegationAllocate(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("delegation allocate", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	runID := fs.String("run-id", "", "run id")
	step := fs.String("step", "", "step id")
	agent := fs.String("agent", "", "agent name")
	feature := fs.String("feature", "", "feature id (projects an external run when the row is missing)")
	id := fs.String("id", "", "delegation id (optional; generated when empty)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *runID == "" || *step == "" || *agent == "" {
		return usageError{"delegation allocate needs --run-id, --step and --agent"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	delegID := strings.TrimSpace(*id)
	if delegID == "" {
		delegID = e.runs.IDs.New()
	}
	feat := strings.TrimSpace(*feature)
	if feat != "" {
		if err := e.store.ProjectExternalRun(ctx, *runID, feat); err != nil {
			return err
		}
	}
	var assigned ports.Delegation
	err = e.store.InTx(ctx, func(tx ports.Tx) error {
		rec := ports.Delegation{
			ID: delegID, RunID: *runID, StepID: *step, Attempt: 0,
			Agent: *agent, Packet: []byte("{}"), State: "issued",
			IssuedAt: time.Now().UTC(),
		}
		if err := tx.Delegations().Insert(ctx, rec); err != nil {
			return err
		}
		var err error
		assigned, err = tx.Delegations().Get(ctx, delegID)
		if err != nil {
			return err
		}
		_, err = tx.Audit().Append(ctx, audit.Event{
			Action:  audit.ActionDelegationIssued,
			Actor:   audit.Actor{Handle: assigned.Agent, Kind: "agent"},
			RunID:   assigned.RunID,
			StepID:  assigned.StepID,
			Feature: feat,
			Subject: assigned.ID,
			Detail:  map[string]any{"attempt": assigned.Attempt, "agent": assigned.Agent},
		})
		return err
	})
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"id":      assigned.ID,
		"run_id":  assigned.RunID,
		"step_id": assigned.StepID,
		"attempt": assigned.Attempt,
		"agent":   assigned.Agent,
	})
}
