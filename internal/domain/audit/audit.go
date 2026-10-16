// Package audit holds the append-only event chain.
//
// Invariant I-6: every state transition writes one audit event in the same
// transaction that made the transition. The chain is what makes the record
// worth having — each event carries sha256(prev_hash ‖ JCS(event)), so
// removing or editing an event breaks every hash after it. A log you can
// edit answers "what happened" only as well as whoever had write access
// wants it to.
//
// Checkpoints exist because verifying a long chain means rehashing all of
// it. A checkpoint is a server signature over one position, so verification
// can start from the last signed point instead of from the beginning.
//
// Zero IO: the chain is computed here, stored by the adapter. The DB also
// refuses UPDATE and DELETE on the table with a trigger, so the two
// defences are independent.
package audit

import (
	"fmt"
	"time"

	"github.com/idev/pkg/canonical"
)

// Action names what happened. The vocabulary is deliberately small: an audit
// trail with a hundred verbs is one nobody reads.
type Action string

// The actions.
const (
	ActionRunStarted          Action = "run.started"
	ActionRunAborted          Action = "run.aborted"
	ActionRunCompleted        Action = "run.completed"
	ActionStepActivated       Action = "step.activated"
	ActionStepRecorded        Action = "step.recorded"
	ActionStepRetried         Action = "step.retried"
	ActionStepAmended         Action = "step.amended"
	ActionStepSkipped         Action = "step.skipped"
	ActionDelegationIssued    Action = "delegation.issued"
	ActionDelegationReturned  Action = "delegation.returned"
	ActionDelegationAccepted  Action = "delegation.accepted"
	ActionVerification        Action = "verification.recorded"
	ActionLeaseAcquired       Action = "lease.acquired"
	ActionLeaseReleased       Action = "lease.released"
	ActionLeaseExpired        Action = "lease.expired"
	ActionGateRequested       Action = "gate.requested"
	ActionGateApproved        Action = "gate.approved"
	ActionGateRejected        Action = "gate.rejected"
	ActionGateExpired         Action = "gate.expired"
	ActionGateWithdrawn       Action = "gate.withdrawn"
	ActionBaselineSealed      Action = "baseline.sealed"
	ActionBaselineDrift       Action = "baseline.drift"
	ActionBaselineReopened    Action = "baseline.reopened"
	ActionStageAdvanced       Action = "stage.advanced"
	ActionStageRolledBack     Action = "stage.rolled_back"
	ActionAssuranceDowngraded Action = "assurance.downgraded"
)

// Actor is who caused the event.
//
// OnBehalfOf is the point of recording an actor at all: an agent acting for
// a person is a different fact from the person acting, and "the agent did
// it" with no owner is how accountability disappears.
type Actor struct {
	Handle     string `json:"handle"`
	Kind       string `json:"kind"`
	OnBehalfOf string `json:"on_behalf_of,omitempty"`
	// Via records a submission relayed by the conductor rather than sent by
	// the agent itself (design §6.2, submit_on_behalf).
	Via string `json:"via,omitempty"`
}

// Event is one entry. The JSON tags matter: the hash is over the JCS form of
// this struct, so a field rename changes every hash after it.
type Event struct {
	Seq     int64     `json:"seq"`
	At      time.Time `json:"at"`
	Action  Action    `json:"action"`
	Actor   Actor     `json:"actor"`
	RunID   string    `json:"run_id,omitempty"`
	StepID  string    `json:"step_id,omitempty"`
	Feature string    `json:"feature,omitempty"`
	// Subject is what the action was about: a gate id, a delegation id, a
	// baseline revision.
	Subject string `json:"subject,omitempty"`
	// Detail is free-form but canonicalised, so it is part of the hash.
	Detail map[string]any `json:"detail,omitempty"`

	PrevHash canonical.Digest `json:"prev_hash"`
	Hash     canonical.Digest `json:"-"`
}

// Genesis is the prev_hash of the first event. A fixed, recognisable value
// rather than an empty string, so "the chain starts here" and "prev_hash was
// never set" are different.
const Genesis canonical.Digest = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

// payload is the hashed projection: everything but the hash itself.
type payload struct {
	Seq      int64          `json:"seq"`
	At       string         `json:"at"`
	Action   Action         `json:"action"`
	Actor    Actor          `json:"actor"`
	RunID    string         `json:"run_id,omitempty"`
	StepID   string         `json:"step_id,omitempty"`
	Feature  string         `json:"feature,omitempty"`
	Subject  string         `json:"subject,omitempty"`
	Detail   map[string]any `json:"detail,omitempty"`
	PrevHash string         `json:"prev_hash"`
}

func (e Event) payload() payload {
	return payload{
		Seq: e.Seq,
		// RFC 3339 in UTC to the nanosecond: a hash must not depend on the
		// writer's timezone.
		At:       e.At.UTC().Format(time.RFC3339Nano),
		Action:   e.Action,
		Actor:    e.Actor,
		RunID:    e.RunID,
		StepID:   e.StepID,
		Feature:  e.Feature,
		Subject:  e.Subject,
		Detail:   e.Detail,
		PrevHash: string(e.PrevHash),
	}
}

// Seal computes the event's hash from its content and its predecessor.
func Seal(e Event, prev canonical.Digest) (Event, error) {
	if e.Action == "" {
		return Event{}, fmt.Errorf("audit: an event with no action records nothing")
	}
	if e.Actor.Handle == "" || e.Actor.Kind == "" {
		return Event{}, fmt.Errorf("audit: %s has no actor; an unattributed event is not an audit record", e.Action)
	}
	if e.Seq <= 0 {
		return Event{}, fmt.Errorf("audit: seq must be positive, got %d", e.Seq)
	}
	if prev == "" {
		return Event{}, fmt.Errorf("audit: prev_hash is unset; use Genesis for the first event")
	}
	e.PrevHash = prev
	h, err := canonical.HashJCS(e.payload())
	if err != nil {
		return Event{}, fmt.Errorf("audit: %w", err)
	}
	e.Hash = h
	return e, nil
}

// Chain seals a run of events in order, starting from `prev`.
func Chain(prev canonical.Digest, events []Event) ([]Event, error) {
	out := make([]Event, 0, len(events))
	for i, e := range events {
		sealed, err := Seal(e, prev)
		if err != nil {
			return nil, fmt.Errorf("audit: event %d: %w", i, err)
		}
		out = append(out, sealed)
		prev = sealed.Hash
	}
	return out, nil
}

// Breakage describes where a chain stopped being valid.
type Breakage struct {
	Seq int64
	// Kind is "hash-mismatch" (the content was edited), "link-mismatch" (an
	// event was removed or reordered), or "sequence-gap".
	Kind     string
	Expected canonical.Digest
	Found    canonical.Digest
}

func (b Breakage) Error() string {
	return fmt.Sprintf("audit: chain broken at seq %d: %s (expected %s, found %s)",
		b.Seq, b.Kind, b.Expected, b.Found)
}

// Verify walks a chain and reports the first breakage.
//
// Three distinct failures, kept distinct because they mean different things:
// a hash mismatch is an edited event, a link mismatch is a removed or
// reordered one, and a sequence gap is a missing one.
func Verify(start canonical.Digest, events []Event) error {
	prev := start
	var lastSeq int64 = -1
	for _, e := range events {
		if lastSeq >= 0 && e.Seq != lastSeq+1 {
			return Breakage{Seq: e.Seq, Kind: "sequence-gap"}
		}
		lastSeq = e.Seq

		if e.PrevHash != prev {
			return Breakage{
				Seq: e.Seq, Kind: "link-mismatch", Expected: prev, Found: e.PrevHash,
			}
		}
		want, err := canonical.HashJCS(e.payload())
		if err != nil {
			return fmt.Errorf("audit: seq %d: %w", e.Seq, err)
		}
		if want != e.Hash {
			return Breakage{
				Seq: e.Seq, Kind: "hash-mismatch", Expected: want, Found: e.Hash,
			}
		}
		prev = e.Hash
	}
	return nil
}

// Checkpoint is a signed position in the chain, so verification can start
// from the last signed point rather than from the beginning.
type Checkpoint struct {
	Seq   int64            `json:"seq"`
	Hash  canonical.Digest `json:"hash"`
	At    time.Time        `json:"at"`
	KeyID string           `json:"key_id"`
	// Signature is over the JCS form of the fields above. Produced by the
	// signer port; this package only defines what gets signed, so the
	// offline verifier and the server cannot disagree about it.
	Signature string `json:"signature"`
}

// CheckpointPayload is the exact bytes a checkpoint signature covers.
func CheckpointPayload(seq int64, hash canonical.Digest, at time.Time, keyID string) ([]byte, error) {
	return canonical.JCS(map[string]any{
		"seq":    seq,
		"hash":   string(hash),
		"at":     at.UTC().Format(time.RFC3339Nano),
		"key_id": keyID,
	})
}
