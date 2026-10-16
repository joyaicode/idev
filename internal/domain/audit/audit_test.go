package audit_test

import (
	"errors"
	"testing"
	"time"

	"pgregory.net/rapid"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/pkg/canonical"
)

var at = time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)

func ev(seq int64, action audit.Action) audit.Event {
	return audit.Event{
		Seq:     seq,
		At:      at.Add(time.Duration(seq) * time.Minute),
		Action:  action,
		Actor:   audit.Actor{Handle: "wangwei794", Kind: "human"},
		RunID:   "01M4ZS7F90PJA5BGZKRQGE4V78",
		Feature: "demo",
	}
}

func chain(t *testing.T, n int) []audit.Event {
	t.Helper()
	events := make([]audit.Event, 0, n)
	for i := 1; i <= n; i++ {
		events = append(events, ev(int64(i), audit.ActionStepRecorded))
	}
	sealed, err := audit.Chain(audit.Genesis, events)
	if err != nil {
		t.Fatalf("Chain: %v", err)
	}
	return sealed
}

func TestAValidChainVerifies(t *testing.T) {
	events := chain(t, 5)
	if err := audit.Verify(audit.Genesis, events); err != nil {
		t.Fatalf("a chain this package built does not verify: %v", err)
	}
	if events[0].PrevHash != audit.Genesis {
		t.Error("the first event does not link to Genesis")
	}
	for i := 1; i < len(events); i++ {
		if events[i].PrevHash != events[i-1].Hash {
			t.Errorf("event %d does not link to its predecessor", i)
		}
	}
}

func TestAnEmptyChainVerifies(t *testing.T) {
	if err := audit.Verify(audit.Genesis, nil); err != nil {
		t.Errorf("an empty chain should verify: %v", err)
	}
}

func TestSealRefusesAnUnattributableEvent(t *testing.T) {
	cases := map[string]audit.Event{
		"no action": {Seq: 1, Actor: audit.Actor{Handle: "a", Kind: "human"}},
		"no actor handle": {
			Seq: 1, Action: audit.ActionRunStarted, Actor: audit.Actor{Kind: "human"},
		},
		"no actor kind": {
			Seq: 1, Action: audit.ActionRunStarted, Actor: audit.Actor{Handle: "a"},
		},
		"zero seq": {
			Seq: 0, Action: audit.ActionRunStarted, Actor: audit.Actor{Handle: "a", Kind: "human"},
		},
	}
	for name, e := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := audit.Seal(e, audit.Genesis); err == nil {
				t.Error("Seal accepted an event that records nothing useful")
			}
		})
	}
	// An unset prev_hash is a programming error, not an empty chain.
	if _, err := audit.Seal(ev(1, audit.ActionRunStarted), ""); err == nil {
		t.Error("Seal accepted an unset prev_hash; use Genesis for the first event")
	}
}

// --- the three ways a chain breaks ---------------------------------------

func TestEditingAnEventIsDetected(t *testing.T) {
	events := chain(t, 5)
	// The record now says someone else did it. The hash still claims
	// otherwise.
	events[2].Actor.Handle = "idev-coder"

	err := audit.Verify(audit.Genesis, events)
	if err == nil {
		t.Fatal("an edited event verified")
	}
	var b audit.Breakage
	if !errors.As(err, &b) {
		t.Fatalf("error type = %T, want audit.Breakage", err)
	}
	if b.Kind != "hash-mismatch" || b.Seq != 3 {
		t.Errorf("breakage = %+v, want hash-mismatch at seq 3", b)
	}
}

func TestEditingAnyFieldIsDetected(t *testing.T) {
	// Every hashed field, so a field accidentally left out of the payload
	// shows up here rather than years later.
	mutations := map[string]func(*audit.Event){
		"action":       func(e *audit.Event) { e.Action = audit.ActionGateApproved },
		"actor handle": func(e *audit.Event) { e.Actor.Handle = "someone" },
		"actor kind":   func(e *audit.Event) { e.Actor.Kind = "agent" },
		"on_behalf_of": func(e *audit.Event) { e.Actor.OnBehalfOf = "alice" },
		"via":          func(e *audit.Event) { e.Actor.Via = "conductor" },
		"run_id":       func(e *audit.Event) { e.RunID = "01M4ZS7F90PJA5BGZKRQGE4V79" },
		"step_id":      func(e *audit.Event) { e.StepID = "other" },
		"feature":      func(e *audit.Event) { e.Feature = "other" },
		"subject":      func(e *audit.Event) { e.Subject = "g-2" },
		"detail":       func(e *audit.Event) { e.Detail = map[string]any{"note": "x"} },
		"timestamp":    func(e *audit.Event) { e.At = at.Add(time.Hour) },
		"seq":          func(e *audit.Event) { e.Seq = 99 },
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			events := chain(t, 3)
			mutate(&events[1])
			if err := audit.Verify(audit.Genesis, events); err == nil {
				t.Errorf("editing %s went undetected; it is not part of the hash", name)
			}
		})
	}
}

func TestRemovingAnEventIsDetected(t *testing.T) {
	events := chain(t, 5)
	// Drop the middle one and close the gap. The sequence numbers now jump.
	tampered := append(append([]audit.Event{}, events[:2]...), events[3:]...)

	err := audit.Verify(audit.Genesis, tampered)
	if err == nil {
		t.Fatal("a chain with an event removed verified")
	}
	var b audit.Breakage
	if !errors.As(err, &b) {
		t.Fatalf("error type = %T", err)
	}
	if b.Kind != "sequence-gap" {
		t.Errorf("kind = %s, want sequence-gap", b.Kind)
	}
}

func TestReorderingIsDetected(t *testing.T) {
	events := chain(t, 4)
	events[1], events[2] = events[2], events[1]
	if err := audit.Verify(audit.Genesis, events); err == nil {
		t.Fatal("a reordered chain verified")
	}
}

func TestReplacingATailIsDetected(t *testing.T) {
	// The sharpest case: rewrite the end of the chain *and* re-seal it, but
	// starting from the wrong predecessor. The sequence is intact and every
	// hash is self-consistent; only the link to the untouched prefix fails.
	events := chain(t, 5)
	forged, err := audit.Chain(canonical.Hash([]byte("not the real prefix")), []audit.Event{
		ev(4, audit.ActionGateApproved),
		ev(5, audit.ActionRunCompleted),
	})
	if err != nil {
		t.Fatal(err)
	}
	tampered := append(append([]audit.Event{}, events[:3]...), forged...)

	err = audit.Verify(audit.Genesis, tampered)
	if err == nil {
		t.Fatal("a re-sealed forged tail verified")
	}
	var b audit.Breakage
	if !errors.As(err, &b) {
		t.Fatalf("error type = %T", err)
	}
	if b.Kind != "link-mismatch" || b.Seq != 4 {
		t.Errorf("breakage = %+v, want link-mismatch at seq 4", b)
	}
	if b.Error() == "" {
		t.Error("a breakage must describe itself")
	}
}

func TestVerifyingFromTheWrongStartFails(t *testing.T) {
	events := chain(t, 3)
	if err := audit.Verify(canonical.Hash([]byte("elsewhere")), events); err == nil {
		t.Error("a chain verified against a start it does not link to")
	}
}

// --- checkpoints ----------------------------------------------------------

func TestCheckpointPayloadIsStable(t *testing.T) {
	a, err := audit.CheckpointPayload(42, canonical.Hash([]byte("x")), at, "ed25519:0123456789abcdef")
	if err != nil {
		t.Fatal(err)
	}
	b, err := audit.CheckpointPayload(42, canonical.Hash([]byte("x")), at, "ed25519:0123456789abcdef")
	if err != nil {
		t.Fatal(err)
	}
	if string(a) != string(b) {
		t.Error("the signed bytes are not deterministic; an offline verifier could not reproduce them")
	}
}

func TestCheckpointPayloadCoversEveryField(t *testing.T) {
	base, _ := audit.CheckpointPayload(1, canonical.Hash([]byte("x")), at, "k")
	variants := map[string][]byte{}
	variants["seq"], _ = audit.CheckpointPayload(2, canonical.Hash([]byte("x")), at, "k")
	variants["hash"], _ = audit.CheckpointPayload(1, canonical.Hash([]byte("y")), at, "k")
	variants["at"], _ = audit.CheckpointPayload(1, canonical.Hash([]byte("x")), at.Add(time.Second), "k")
	variants["key_id"], _ = audit.CheckpointPayload(1, canonical.Hash([]byte("x")), at, "k2")
	for name, v := range variants {
		if string(v) == string(base) {
			t.Errorf("%s is not covered by the checkpoint signature", name)
		}
	}
}

func TestCheckpointTimezoneDoesNotMatter(t *testing.T) {
	utc, _ := audit.CheckpointPayload(1, canonical.Hash([]byte("x")), at, "k")
	shanghai, _ := audit.CheckpointPayload(
		1, canonical.Hash([]byte("x")), at.In(time.FixedZone("CST", 8*3600)), "k")
	if string(utc) != string(shanghai) {
		t.Error("the same instant in two zones produced different signed bytes")
	}
}

func TestEventTimezoneDoesNotMatter(t *testing.T) {
	a, err := audit.Seal(ev(1, audit.ActionRunStarted), audit.Genesis)
	if err != nil {
		t.Fatal(err)
	}
	shifted := ev(1, audit.ActionRunStarted)
	shifted.At = shifted.At.In(time.FixedZone("CST", 8*3600))
	b, err := audit.Seal(shifted, audit.Genesis)
	if err != nil {
		t.Fatal(err)
	}
	if a.Hash != b.Hash {
		t.Error("the same event hashed differently depending on the writer's timezone")
	}
}

// --- properties -----------------------------------------------------------

// Any chain this package builds verifies, and any single-field edit anywhere
// in it is caught.
func TestPropertyAnyEditBreaksTheChain(t *testing.T) {
	actions := []audit.Action{
		audit.ActionRunStarted, audit.ActionStepRecorded, audit.ActionGateApproved,
		audit.ActionBaselineSealed, audit.ActionLeaseAcquired,
	}
	rapid.Check(t, func(t *rapid.T) {
		n := rapid.IntRange(1, 12).Draw(t, "events")
		raw := make([]audit.Event, 0, n)
		for i := 1; i <= n; i++ {
			e := ev(int64(i), rapid.SampledFrom(actions).Draw(t, "action"))
			e.Subject = rapid.SampledFrom([]string{"", "g-1", "d-2"}).Draw(t, "subject")
			if rapid.Bool().Draw(t, "hasDetail") {
				e.Detail = map[string]any{"note": rapid.SampledFrom([]string{"a", "b"}).Draw(t, "note")}
			}
			raw = append(raw, e)
		}
		sealed, err := audit.Chain(audit.Genesis, raw)
		if err != nil {
			t.Fatalf("Chain: %v", err)
		}
		if err := audit.Verify(audit.Genesis, sealed); err != nil {
			t.Fatalf("a freshly built chain does not verify: %v", err)
		}

		// Edit one event and it must stop verifying.
		i := rapid.IntRange(0, len(sealed)-1).Draw(t, "victim")
		tampered := append([]audit.Event{}, sealed...)
		switch rapid.IntRange(0, 3).Draw(t, "field") {
		case 0:
			tampered[i].Actor.Handle += "x"
		case 1:
			tampered[i].Action = audit.ActionRunAborted + "x"
		case 2:
			tampered[i].At = tampered[i].At.Add(time.Second)
		case 3:
			tampered[i].Subject += "x"
		}
		if err := audit.Verify(audit.Genesis, tampered); err == nil {
			t.Fatalf("an edit to event %d went undetected", i)
		}
	})
}

// Truncating a chain still verifies — the prefix is intact, and that is the
// correct answer. Detecting truncation is what checkpoints are for, which is
// why this is asserted rather than left implicit.
func TestPropertyAPrefixStillVerifies(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		sealed := chainOf(t, rapid.IntRange(1, 10).Draw(t, "events"))
		k := rapid.IntRange(0, len(sealed)).Draw(t, "keep")
		if err := audit.Verify(audit.Genesis, sealed[:k]); err != nil {
			t.Fatalf("a prefix of a valid chain failed to verify: %v", err)
		}
	})
}

func chainOf(t *rapid.T, n int) []audit.Event {
	events := make([]audit.Event, 0, n)
	for i := 1; i <= n; i++ {
		events = append(events, ev(int64(i), audit.ActionStepRecorded))
	}
	sealed, err := audit.Chain(audit.Genesis, events)
	if err != nil {
		t.Fatalf("Chain: %v", err)
	}
	return sealed
}
