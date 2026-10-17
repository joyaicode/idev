// Package leasesvc is where leases are minted and retired.
//
// runsvc applies the lease effects that need no secret — releasing a lease
// can only cost the holder its turn — but acquiring one mints a bearer
// token that must exist exactly once and must never travel through the
// audit log. That is this package: the service that issues a lease hands
// the token to the agent and keeps only its hash, which is also all the
// store ever sees.
//
// As everywhere in the app layer, one use case is one transaction: the
// lease and its audit event are written together or not at all (invariant
// I-6), so there is never a lease without a record of who won it.
package leasesvc

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"fmt"
	"time"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/canonical"
)

const (
	defaultTTL      = 30 * time.Minute
	defaultRenewFor = 30 * time.Minute
	// sweepBatch caps one Sweep call. The sweeper's own deadline matters
	// too: a batch that ran unbounded would hold its transaction open for
	// as long as there are leases to expire.
	sweepBatch = 100
)

// Service issues, renews, releases and sweeps leases.
type Service struct {
	Store ports.Store
	Clock ports.Clock
	IDs   ports.IDGen
	// TTL is how long a fresh lease runs; RenewFor is how far a renewal
	// pushes the deadline. Zero means the defaults above. A renewal window
	// shorter than the TTL is what makes a dead holder lose the lease
	// instead of holding it forever.
	TTL      time.Duration
	RenewFor time.Duration
}

// AcquireParams describes the lease an agent asks for.
type AcquireParams struct {
	Purpose lease.Purpose
	// Feature is the feature's ID, not its display name: the fencing
	// counter and the single-writer index (I-1) are keyed by it, so every
	// lease — verify included — names one.
	Feature    string
	RunID      string
	StepID     string
	Agent      string
	WritePaths []string
	// TicketDir is the boundary of I-2's other half: a verify lease may
	// only write inside it.
	TicketDir string
	Actor     ports.Principal
}

// Held is a lease plus the one copy of its bearer token. Hand it to the
// agent and forget it: only the hash is stored, so a lost token cannot be
// recovered, by design — the agent has to ask for a fresh lease.
type Held struct {
	Lease lease.Lease
	Token string
}

// Acquire issues a lease. There is deliberately no idempotency key: a
// replayed Acquire would have to return the original token, which means
// storing the raw token, which is exactly what the hash-only design
// refuses. A retry after a timeout either hits the I-1 conflict (the first
// attempt won) or issues a fresh lease, and both are safe.
//
// The lease is bound to the step the run says it is for: a write lease only
// when the step is delegated to this agent, a verify lease only while the
// step is verifying. Without this, "release, then acquire" would hand the
// feature to whoever asked first (review D2).
func (s Service) Acquire(ctx context.Context, p AcquireParams) (Held, error) {
	if p.Purpose != lease.PurposeWrite && p.Purpose != lease.PurposeVerify {
		return Held{}, fmt.Errorf("leasesvc: a %s step needs no lease", p.Purpose)
	}
	if p.Agent == "" {
		return Held{}, fmt.Errorf("leasesvc: a lease needs the agent that will hold it")
	}
	if p.RunID == "" || p.StepID == "" {
		return Held{}, fmt.Errorf("leasesvc: a lease is scoped to one step of one run")
	}
	if p.Feature == "" {
		return Held{}, fmt.Errorf("leasesvc: a lease needs a feature: the fencing counter and the single-writer rule are keyed by it")
	}
	if p.Purpose == lease.PurposeVerify {
		if p.TicketDir == "" {
			return Held{}, fmt.Errorf("leasesvc: a verify lease needs the ticket directory (I-2)")
		}
		if err := lease.ValidateVerifyPaths(p.TicketDir, p.WritePaths); err != nil {
			return Held{}, fmt.Errorf("leasesvc: %w", err)
		}
	}

	token, err := newToken()
	if err != nil {
		return Held{}, err
	}
	now := s.now()

	var held Held
	err = s.Store.InTx(ctx, func(tx ports.Tx) error {
		if err := checkStepForPurpose(ctx, tx, p); err != nil {
			return err
		}
		// Fencing before Issue: if the store refuses the lease (I-1), the
		// increment rolls back with it, so a refused acquire does not burn
		// a fencing token.
		fencing, err := tx.Leases().NextFencing(ctx, p.Feature)
		if err != nil {
			return err
		}
		l := lease.Lease{
			ID:         s.IDs.New(),
			Purpose:    p.Purpose,
			Feature:    p.Feature,
			RunID:      p.RunID,
			StepID:     p.StepID,
			Agent:      p.Agent,
			WritePaths: append([]string{}, p.WritePaths...),
			Fencing:    fencing,
			ExpiresAt:  now.Add(s.ttl()),
		}
		if err := tx.Leases().Issue(ctx, l, string(canonical.Hash([]byte(token)))); err != nil {
			return err
		}
		if err := appendAudit(ctx, tx, audit.Event{
			Action:  audit.ActionLeaseAcquired,
			Actor:   actorOf(p.Actor),
			RunID:   p.RunID,
			StepID:  p.StepID,
			Feature: p.Feature,
			Subject: l.ID,
			Detail: map[string]any{
				"purpose":    string(p.Purpose),
				"agent":      p.Agent,
				"fencing":    fencing,
				"expires_at": l.ExpiresAt.Format(time.RFC3339),
			},
		}, s.Clock); err != nil {
			return err
		}
		held = Held{Lease: l, Token: token}
		return nil
	})
	return held, err
}

// checkStepForPurpose binds a lease to the state the run says the step is
// in: a write lease goes to the agent the step was delegated to, a verify
// lease only while the step is verifying. Anything else is an attempt to
// hold a step the caller has no claim on.
func checkStepForPurpose(ctx context.Context, tx ports.Tx, p AcquireParams) error {
	r, _, err := tx.Runs().Get(ctx, p.RunID)
	if err != nil {
		return err
	}
	for i := range r.Steps {
		if r.Steps[i].ID != p.StepID {
			continue
		}
		st := r.Steps[i]
		switch p.Purpose {
		case lease.PurposeWrite:
			if st.State != run.StepDelegated {
				return fmt.Errorf(
					"leasesvc: %s is %s, not delegated; a write lease follows a delegation",
					p.StepID, st.State)
			}
			if st.Writer != p.Agent {
				return fmt.Errorf(
					"leasesvc: %s holds the delegation for %s, not %s",
					st.Writer, p.StepID, p.Agent)
			}
		case lease.PurposeVerify:
			if st.State != run.StepVerifying {
				return fmt.Errorf(
					"leasesvc: %s is %s, not verifying; a verify lease follows an accepted report",
					p.StepID, st.State)
			}
		}
		return nil
	}
	return fmt.Errorf("leasesvc: run %s has no step %s", p.RunID, p.StepID)
}

// Renew pushes a live lease's deadline out. It is a keepalive: no audit
// event, because none of the lease's facts — holder, purpose, fencing —
// changed, and a chain that logged every heartbeat would drown the events
// worth reading.
func (s Service) Renew(ctx context.Context, leaseID, token string) (lease.Lease, error) {
	now := s.now()
	var out lease.Lease
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		l, err := tx.Leases().Extend(ctx, leaseID, string(canonical.Hash([]byte(token))), now, now.Add(s.renewFor()))
		out = l
		return err
	})
	return out, err
}

// Release retires a lease. The bearer token proves the caller is the
// holder: without it, anyone could retire anyone else's lease and then
// acquire the freed feature — the two-step I-1 bypass of review D2. The
// one caller that legitimately holds no token is runsvc, which releases
// inside the run's own transaction when the domain's effects say so.
//
// Release is idempotent, and every already-gone path returns nil without
// an audit event, so a retry cannot forge a second release record.
func (s Service) Release(ctx context.Context, leaseID, token string, actor ports.Principal) error {
	now := s.now()
	return s.Store.InTx(ctx, func(tx ports.Tx) error {
		l, err := tx.Leases().Get(ctx, leaseID)
		if isNotFound(err) {
			return nil
		}
		if err != nil {
			return err
		}
		// The token decides, before any state does: a caller that cannot
		// present it has no claim on this lease, whatever shape the lease
		// is in (review D2).
		if hash, err := tx.Leases().TokenHash(ctx, leaseID); err != nil {
			return err
		} else if hash != string(canonical.Hash([]byte(token))) {
			return &ports.ConflictError{
				Kind:   ports.ConflictLeaseHeld,
				Detail: fmt.Sprintf("%s is not the holder of %s; releasing a lease needs its token", actor.Handle, leaseID),
			}
		}
		if l.Expired(now) {
			// Past its deadline the lease is the sweeper's to record; a
			// release here would hide that it ran out.
			return nil
		}
		active, err := tx.Leases().ActiveFor(ctx, l.RunID, l.StepID)
		if isNotFound(err) {
			return nil
		}
		if err != nil {
			return err
		}
		if active.ID != leaseID {
			// Another lease has the step; this one is already retired.
			return nil
		}
		if err := tx.Leases().Release(ctx, leaseID); err != nil {
			return err
		}
		return appendAudit(ctx, tx, audit.Event{
			Action:  audit.ActionLeaseReleased,
			Actor:   actorOf(actor),
			RunID:   l.RunID,
			StepID:  l.StepID,
			Feature: l.Feature,
			Subject: leaseID,
			Detail:  map[string]any{"agent": l.Agent},
		}, s.Clock)
	})
}

// Sweep expires leases past their deadline and returns how many. One batch
// per call; running until drained is the caller's loop, so a sweeper that
// dies mid-run leaves no half-finished work behind.
func (s Service) Sweep(ctx context.Context) (int, error) {
	now := s.now()
	n := 0
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		expired, err := tx.Leases().Expire(ctx, now, sweepBatch)
		if err != nil {
			return err
		}
		n = len(expired)
		for _, l := range expired {
			if err := appendAudit(ctx, tx, audit.Event{
				Action:  audit.ActionLeaseExpired,
				Actor:   audit.Actor{Handle: "sweeper", Kind: "system"},
				RunID:   l.RunID,
				StepID:  l.StepID,
				Feature: l.Feature,
				Subject: l.ID,
				Detail: map[string]any{
					"agent":      l.Agent,
					"expired_at": now.Format(time.RFC3339),
				},
			}, s.Clock); err != nil {
				return err
			}
		}
		return nil
	})
	return n, err
}

// --- helpers ----------------------------------------------------------------

// newToken mints 32 random bytes. Base64 without padding so the token is
// one clean word, not something an agent will re-wrap by accident.
func newToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("leasesvc: no entropy for a token: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}

func (s Service) now() time.Time {
	if s.Clock == nil {
		return time.Now()
	}
	return s.Clock.Now()
}

func (s Service) ttl() time.Duration {
	if s.TTL <= 0 {
		return defaultTTL
	}
	return s.TTL
}

func (s Service) renewFor() time.Duration {
	if s.RenewFor <= 0 {
		return defaultRenewFor
	}
	return s.RenewFor
}

// The three helpers below are the runsvc ones, copied: they are package
// private there, and the alternative — exporting them so two app services
// can share them — would make an app-internal detail part of the API.

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

func isNotFound(err error) bool {
	var ce *ports.ConflictError
	return errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound
}
