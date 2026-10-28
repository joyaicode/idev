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
	"github.com/idev/internal/adapters/workspace"
	"github.com/idev/internal/app/baselinesvc"
	"github.com/idev/internal/domain/audit"
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
	repo := fs.String("repo", "", "repo root for details[] paths (default: guess from ticket)")
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
	m, err := workspace.FromTicket(*feature, *ticket, *repo, *revision, time.Now().UTC())
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

// baselineAdopt takes a ticket sealed before the store existed into it. A
// person runs it once per legacy ticket; the proof is the ticket's git
// history, so the row is recorded with low assurance.
func (a app) baselineAdopt(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("baseline adopt", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	feature := fs.String("feature", "", "feature id")
	ticket := fs.String("ticket", "", "ticket directory with baseline.yaml")
	repo := fs.String("repo", "", "repo root for details[] paths (default: guess from ticket)")
	by := fs.String("by", "", "the person running the migration")
	reason := fs.String("reason", "", "why this legacy seal is taken over")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *feature == "" || *ticket == "" || *by == "" || strings.TrimSpace(*reason) == "" {
		return usageError{"baseline adopt needs --feature, --ticket, --by and --reason"}
	}
	m, err := workspace.FromTicket(*feature, *ticket, *repo, 0, time.Now().UTC())
	if err != nil {
		return err
	}
	paths := make([]string, 0, len(m.Files))
	for _, f := range m.Files {
		paths = append(paths, f.Path)
	}
	proof, err := workspace.FindLegacySeal(*ticket, *repo, paths, baselinesvc.LegacyCutover)
	if err != nil {
		return err
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	svc := baselinesvc.Service{Store: e.store, Clock: local.Clock{}}
	adopted, err := svc.Adopt(ctx, baselinesvc.AdoptParams{
		Feature:     *feature,
		Manifest:    m,
		Commit:      proof.Commit,
		CommittedAt: proof.CommittedAt,
		Reason:      strings.TrimSpace(*reason),
		Actor:       ports.Principal{Handle: *by, Kind: "human"},
	})
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"feature":       *feature,
		"revision":      adopted.Revision,
		"manifest_root": string(adopted.ManifestRoot),
		"status":        "sealed",
		"provenance":    "legacy-yaml",
		"assurance":     "low",
		"legacy_commit": proof.Commit,
	})
}

func (a app) baselineVerify(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("baseline verify", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	feature := fs.String("feature", "", "feature id")
	ticket := fs.String("ticket", "", "ticket directory with baseline.yaml")
	repo := fs.String("repo", "", "repo root for details[] paths (default: guess from ticket)")
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
	svc := baselinesvc.Service{Store: e.store, Clock: local.Clock{}}
	sealed, err := svc.Sealed(ctx, *feature)
	if err != nil {
		var ce *ports.ConflictError
		if errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound {
			return fmt.Errorf("no sealed baseline for %s", *feature)
		}
		return err
	}
	current, err := workspace.Recompute(sealed, *ticket, *repo, time.Now().UTC())
	if err != nil {
		return err
	}
	out, err := svc.Check(ctx, *feature, current, ports.Principal{
		Handle: *by, Kind: "agent", OwnerHandle: "system",
	})
	if err != nil {
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

// delegationAccept records a step passing although machine checks on its
// delegation failed: which checks, and why. The refusal is the default; this
// is the trail of the exception.
func (a app) delegationAccept(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("delegation accept", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	id := fs.String("id", "", "the delegation being accepted")
	reason := fs.String("reason", "", "why the step passes despite the findings")
	by := fs.String("by", "conductor", "who accepted it")
	var findings multi
	fs.Var(&findings, "finding", "a failed check being accepted (repeatable)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *id == "" || strings.TrimSpace(*reason) == "" || len(findings) == 0 {
		return usageError{"delegation accept needs --id, --reason and at least one --finding"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	var d ports.Delegation
	err = e.store.InTx(ctx, func(tx ports.Tx) error {
		var err error
		d, err = tx.Delegations().Get(ctx, *id)
		if err != nil {
			return err
		}
		_, err = tx.Audit().Append(ctx, audit.Event{
			Action:  audit.ActionDelegationAccepted,
			Actor:   audit.Actor{Handle: *by, Kind: "agent"},
			RunID:   d.RunID,
			StepID:  d.StepID,
			Subject: d.ID,
			Detail: map[string]any{
				"accepted_with_findings": []string(findings),
				"reason":                 strings.TrimSpace(*reason),
				"attempt":                d.Attempt,
				"agent":                  d.Agent,
			},
		})
		return err
	})
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"delegation_id": d.ID,
		"step_id":       d.StepID,
		"attempt":       d.Attempt,
		"findings":      []string(findings),
	})
}

// delegationVerify attaches a verifier's verdict to the writer's delegation.
// A verification is not another attempt at the step: it takes no attempt
// number, and there is at most one per delegation.
func (a app) delegationVerify(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("delegation verify", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	id := fs.String("id", "", "the writer's delegation id")
	verifier := fs.String("verifier", "", "the verifying agent")
	verdict := fs.String("verdict", "", "the verifier's STATUS")
	var evidence multi
	fs.Var(&evidence, "evidence", "the verifier's report (repeatable)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *id == "" || *verifier == "" || *verdict == "" {
		return usageError{"delegation verify needs --id, --verifier and --verdict"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	var writer ports.Delegation
	err = e.store.InTx(ctx, func(tx ports.Tx) error {
		var err error
		writer, err = tx.Delegations().Get(ctx, *id)
		if err != nil {
			return err
		}
		if writer.Agent == *verifier {
			return fmt.Errorf("%s wrote %s attempt %d; a verification has to come from another agent",
				writer.Agent, writer.StepID, writer.Attempt)
		}
		now := time.Now().UTC()
		if err := tx.Delegations().RecordVerification(ctx, writer.ID, *verifier, *verdict, evidence, now); err != nil {
			return err
		}
		_, err = tx.Audit().Append(ctx, audit.Event{
			Action:  audit.ActionVerification,
			Actor:   audit.Actor{Handle: *verifier, Kind: "agent"},
			RunID:   writer.RunID,
			StepID:  writer.StepID,
			Subject: writer.ID,
			Detail: map[string]any{
				"verdict":  *verdict,
				"evidence": []string(evidence),
				"attempt":  writer.Attempt,
				"writer":   writer.Agent,
			},
		})
		return err
	})
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"delegation_id": writer.ID,
		"step_id":       writer.StepID,
		"attempt":       writer.Attempt,
		"verifier":      *verifier,
		"verdict":       *verdict,
	})
}
