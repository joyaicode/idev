// Package baselinesvc is where a sealed requirement becomes a fact the
// system defends.
//
// The design's invariant I-6 is the whole shape of this package: the
// baseline row and the audit event that says who sealed what, on whose
// approval, are written in one transaction or not at all. A seal with no
// event is unauditable; an event with no seal is a lie.
//
// The binding rules are I-4 applied to baselines. What a person approves at
// a gate is a *question about a manifest*: "may this manifest_root at this
// revision be sealed". Seal and Reopen therefore refuse a gate whose subject
// names anything other than the manifest in hand — signing one manifest and
// sealing another is exactly the swap this check exists to stop. The
// signature on the approval itself is verified where the approval is
// recorded, in gatesvc; here the record's word is enough.
package baselinesvc

import (
	"context"
	"fmt"
	"time"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/baseline"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/ports"
)

// Service seals, checks and reopens baselines.
type Service struct {
	Store ports.Store
	Clock ports.Clock
}

// SealParams describes the seal being made.
type SealParams struct {
	// Feature is the feature whose baseline this becomes.
	Feature string
	// Manifest is the built, immutable manifest being sealed.
	Manifest baseline.Manifest
	// GateID names the gate whose approval covers this manifest.
	GateID string
	// Actor is the principal doing the sealing.
	Actor ports.Principal
}

// Seal turns a person's approval of a manifest into the feature's sealed
// baseline. The gate must be an approved sealed question about this exact
// manifest — same feature, same manifest_root, same revision — and the
// baseline row and its audit event are written in one transaction (I-6).
// Once sealed, the feature's manifest_root is what every later run compares
// itself against; refusing here is cheaper than unwinding there.
func (s Service) Seal(ctx context.Context, p SealParams) (baseline.Manifest, error) {
	if p.Feature == "" {
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: a seal names its feature")
	}
	if p.Manifest.ManifestRoot == "" {
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: a seal over an empty manifest seals nothing")
	}
	if p.Manifest.Feature != p.Feature {
		return baseline.Manifest{}, fmt.Errorf(
			"baselinesvc: the manifest names feature %q, not %q; a baseline is per feature",
			p.Manifest.Feature, p.Feature)
	}
	if p.GateID == "" {
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: a seal needs the gate whose approval covers it")
	}
	if p.Actor.Handle == "" {
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: a seal without an actor is not an audit record")
	}

	var sealed baseline.Manifest
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		g, err := tx.Gates().Get(ctx, p.GateID)
		if err != nil {
			return fmt.Errorf("baselinesvc: reading gate %s: %w", p.GateID, err)
		}
		if err := verifyGate(g, p.Feature, p.Manifest, gate.TypeSealed); err != nil {
			return err
		}
		now := s.now()
		id, err := tx.Baselines().Put(ctx, p.Feature, p.Manifest, "draft")
		if err != nil {
			return fmt.Errorf("baselinesvc: storing the draft: %w", err)
		}
		if err := tx.Baselines().Seal(ctx, id, now); err != nil {
			// ConflictSealedBaseline bubbles: the repo owns one-sealed-per-feature.
			return err
		}
		sealed = p.Manifest
		return appendAudit(ctx, tx, audit.Event{
			Action:  audit.ActionBaselineSealed,
			Actor:   actorOf(p.Actor),
			RunID:   g.RunID,
			StepID:  g.StepID,
			Feature: p.Feature,
			Subject: string(p.Manifest.ManifestRoot),
			Detail: map[string]any{
				"revision":      p.Manifest.Revision,
				"manifest_root": string(p.Manifest.ManifestRoot),
				"raw_root":      string(p.Manifest.RawRoot),
				"files":         len(p.Manifest.Files),
				"repo_head":     p.Manifest.RepoHead,
				"dirty":         p.Manifest.Dirty,
				"gate_id":       p.GateID,
			},
		}, s.Clock)
	})
	if err != nil {
		return baseline.Manifest{}, err
	}
	return sealed, nil
}

// LegacyCutover is when a seal stopped being a field in baseline.yaml and
// became a row here (E4.3, kernel commit 2f46b0f). A ticket whose sealed
// baseline.yaml was committed before it never had a gate to point at.
var LegacyCutover = time.Date(2026, 10, 28, 5, 51, 44, 0, time.UTC)

// AdoptParams describes a seal made before the store existed.
type AdoptParams struct {
	Feature  string
	Manifest baseline.Manifest
	// Commit is the product-repo commit whose baseline.yaml said sealed: true;
	// CommittedAt is its committer date, which must precede LegacyCutover.
	Commit      string
	CommittedAt time.Time
	Reason      string
	Actor       ports.Principal
}

// Adopt takes a pre-store seal into the store. There is no gate to bind, so
// the proof is the git history the caller found, and the event says so:
// provenance legacy-yaml, assurance low. History can be rewritten by whoever
// owns the repository, which is why this is a migration for tickets sealed
// before the cutover and never a second way to seal.
func (s Service) Adopt(ctx context.Context, p AdoptParams) (baseline.Manifest, error) {
	switch {
	case p.Feature == "":
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: an adoption names its feature")
	case p.Manifest.ManifestRoot == "":
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: adopting an empty manifest adopts nothing")
	case p.Manifest.Feature != p.Feature:
		return baseline.Manifest{}, fmt.Errorf(
			"baselinesvc: the manifest names feature %q, not %q", p.Manifest.Feature, p.Feature)
	case p.Commit == "" || p.CommittedAt.IsZero():
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: an adoption needs the commit that sealed it")
	case !p.CommittedAt.Before(LegacyCutover):
		return baseline.Manifest{}, fmt.Errorf(
			"baselinesvc: %s sealed %s at %s, after seals moved into the store (%s); seal it through a gate",
			p.Commit, p.Feature, p.CommittedAt.UTC().Format(time.RFC3339), LegacyCutover.Format(time.RFC3339))
	case p.Reason == "":
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: an adoption without a reason is not an audit record")
	case p.Actor.Handle == "":
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: an adoption without an actor is not an audit record")
	}

	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		id, err := tx.Baselines().Put(ctx, p.Feature, p.Manifest, "draft")
		if err != nil {
			return fmt.Errorf("baselinesvc: storing the draft: %w", err)
		}
		if err := tx.Baselines().Seal(ctx, id, s.now()); err != nil {
			return err
		}
		return appendAudit(ctx, tx, audit.Event{
			Action:  audit.ActionBaselineAdopted,
			Actor:   actorOf(p.Actor),
			Feature: p.Feature,
			Subject: string(p.Manifest.ManifestRoot),
			Detail: map[string]any{
				"revision":            p.Manifest.Revision,
				"manifest_root":       string(p.Manifest.ManifestRoot),
				"raw_root":            string(p.Manifest.RawRoot),
				"files":               len(p.Manifest.Files),
				"repo_head":           p.Manifest.RepoHead,
				"dirty":               p.Manifest.Dirty,
				"provenance":          "legacy-yaml",
				"assurance":           "low",
				"legacy_commit":       p.Commit,
				"legacy_committed_at": p.CommittedAt.UTC().Format(time.RFC3339),
				"reason":              p.Reason,
			},
		}, s.Clock)
	})
	if err != nil {
		return baseline.Manifest{}, err
	}
	return p.Manifest, nil
}

// Check compares the manifest as it is now with the feature's sealed one
// and records what it found. Drift is the only verdict worth an event: it
// is the one that blocks runs. A format-only change is a warning to the
// caller, not a fact in the chain. The sealed read and the drift event
// share one transaction so the comparison is against the baseline that was
// current when the check started, not one sealed mid-check.
func (s Service) Check(
	ctx context.Context, featureID string, current baseline.Manifest, actor ports.Principal,
) (baseline.Comparison, error) {
	if featureID == "" {
		return baseline.Comparison{}, fmt.Errorf("baselinesvc: a check names its feature")
	}
	if current.ManifestRoot == "" {
		return baseline.Comparison{}, fmt.Errorf("baselinesvc: checking against an empty manifest checks nothing")
	}
	if actor.Handle == "" {
		return baseline.Comparison{}, fmt.Errorf("baselinesvc: a check without an actor is not an audit record")
	}

	var out baseline.Comparison
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		stored, err := tx.Baselines().Sealed(ctx, featureID)
		if err != nil {
			return fmt.Errorf("baselinesvc: reading the sealed baseline of %s: %w", featureID, err)
		}
		out = baseline.Compare(stored, current)
		if out.Verdict != baseline.VerdictDrift {
			return nil
		}
		changes := make([]string, 0, len(out.Changes))
		for _, c := range out.Changes {
			changes = append(changes, c.Kind+" "+c.Path)
		}
		return appendAudit(ctx, tx, audit.Event{
			Action:  audit.ActionBaselineDrift,
			Actor:   actorOf(actor),
			Feature: featureID,
			Subject: string(stored.ManifestRoot),
			Detail: map[string]any{
				"sealed_revision": stored.Revision,
				"line":            out.Line,
				"changes":         changes,
			},
		}, s.Clock)
	})
	if err != nil {
		return baseline.Comparison{}, err
	}
	return out, nil
}

// ReopenParams describes the reopen being made.
type ReopenParams struct {
	// Feature is the feature whose sealed baseline is being reopened.
	Feature string
	// GateID names the gate whose approval covers reopening.
	GateID string
	// Actor is the principal doing the reopening.
	Actor ports.Principal
}

// Reopen takes a sealed baseline back to an open question, so the feature
// can change its manifest again. Like a seal it needs a person's approval —
// an approved reopen question about the sealed manifest — and the reopen
// and its event are written in one transaction (I-6). What was sealed is
// returned so the caller can say what it was that got reopened.
func (s Service) Reopen(ctx context.Context, p ReopenParams) (baseline.Manifest, error) {
	if p.Feature == "" {
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: a reopen names its feature")
	}
	if p.GateID == "" {
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: a reopen needs the gate whose approval covers it")
	}
	if p.Actor.Handle == "" {
		return baseline.Manifest{}, fmt.Errorf("baselinesvc: a reopen without an actor is not an audit record")
	}

	var was baseline.Manifest
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		stored, err := tx.Baselines().Sealed(ctx, p.Feature)
		if err != nil {
			return fmt.Errorf("baselinesvc: reading the sealed baseline of %s: %w", p.Feature, err)
		}
		g, err := tx.Gates().Get(ctx, p.GateID)
		if err != nil {
			return fmt.Errorf("baselinesvc: reading gate %s: %w", p.GateID, err)
		}
		if err := verifyGate(g, p.Feature, stored, gate.TypeReopenBaseline); err != nil {
			return err
		}
		if err := tx.Baselines().Reopen(ctx, p.Feature); err != nil {
			return fmt.Errorf("baselinesvc: reopening %s: %w", p.Feature, err)
		}
		was = stored
		return appendAudit(ctx, tx, audit.Event{
			Action:  audit.ActionBaselineReopened,
			Actor:   actorOf(p.Actor),
			RunID:   g.RunID,
			StepID:  g.StepID,
			Feature: p.Feature,
			Subject: string(stored.ManifestRoot),
			Detail: map[string]any{
				"revision":      stored.Revision,
				"manifest_root": string(stored.ManifestRoot),
				"gate_id":       p.GateID,
			},
		}, s.Clock)
	})
	if err != nil {
		return baseline.Manifest{}, err
	}
	return was, nil
}

// Sealed returns the feature's sealed manifest — the thing every later run
// is compared against. An unsealed feature reports ConflictNotFound; that
// is the caller's problem, usually a missing seal rather than a broken one.
func (s Service) Sealed(ctx context.Context, featureID string) (baseline.Manifest, error) {
	var m baseline.Manifest
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		var err error
		m, err = tx.Baselines().Sealed(ctx, featureID)
		return err
	})
	return m, err
}

// Get returns one stored manifest by baseline id.
func (s Service) Get(ctx context.Context, baselineID string) (baseline.Manifest, error) {
	var m baseline.Manifest
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		var err error
		m, err = tx.Baselines().Get(ctx, baselineID)
		return err
	})
	return m, err
}

// verifyGate is the manifest binding (I-4): the gate must be an approved
// question of exactly the type wanted, about this feature, whose subject is
// a baseline with this manifest's root and revision. Each clause is a
// different lie a caller could tell, so each gets its own message.
func verifyGate(g gate.Gate, feature string, m baseline.Manifest, want gate.Type) error {
	switch {
	case g.Type != want:
		return fmt.Errorf("baselinesvc: gate %s is a %s question, not %s", g.ID, g.Type, want)
	case g.Status != gate.StatusApproved:
		return fmt.Errorf("baselinesvc: gate %s is %s; only a person's yes seals or reopens", g.ID, g.Status)
	case g.Feature != feature:
		return fmt.Errorf("baselinesvc: gate %s is about feature %q, not %q", g.ID, g.Feature, feature)
	case g.Subject.Kind != gate.SubjectBaseline:
		return fmt.Errorf("baselinesvc: gate %s signs a %s, not a baseline", g.ID, g.Subject.Kind)
	case g.Subject.Digest != string(m.ManifestRoot):
		return fmt.Errorf(
			"baselinesvc: gate %s approved digest %s, but this manifest's root is %s; "+
				"approving one thing and sealing another is what the binding exists to stop",
			g.ID, g.Subject.Digest, m.ManifestRoot)
	case g.Subject.BaselineRevision != m.Revision:
		return fmt.Errorf(
			"baselinesvc: gate %s approved revision %d, but this manifest is revision %d",
			g.ID, g.Subject.BaselineRevision, m.Revision)
	}
	return nil
}

// The two helpers below are the gatesvc ones, copied: they are package
// private there, and the alternative — exporting them so the app services
// can share them — would make an app-internal detail part of the API.

func (s Service) now() time.Time {
	if s.Clock == nil {
		return time.Now()
	}
	return s.Clock.Now()
}

func appendAudit(ctx context.Context, tx ports.Tx, e audit.Event, clock ports.Clock) error {
	if e.At.IsZero() && clock != nil {
		e.At = clock.Now()
	}
	_, err := tx.Audit().Append(ctx, e)
	return err
}

func actorOf(p ports.Principal) audit.Actor {
	return audit.Actor{
		Handle:     p.Handle,
		Kind:       p.Kind,
		OnBehalfOf: p.OwnerHandle,
	}
}
