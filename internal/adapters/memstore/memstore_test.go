package memstore_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/idev/internal/adapters/memstore"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/ports"
)

// The audit repo's contract is what every service's audit trail stands on:
// Append owns the sequence and the sealing, checkpoints round-trip through
// transactions, and a transaction either persists what its writes claimed
// or nothing.

var at = time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)

// appendOne appends a single well-formed event through a transaction and
// returns the sealed row.
func appendOne(t *testing.T, st *memstore.Store) audit.Event {
	t.Helper()
	var sealed audit.Event
	err := st.InTx(context.Background(), func(tx ports.Tx) error {
		e, err := tx.Audit().Append(context.Background(), audit.Event{
			At:     at,
			Action: audit.ActionLeaseAcquired,
			Actor:  audit.Actor{Handle: "conductor@claude", Kind: "agent"},
		})
		if err != nil {
			return err
		}
		sealed = e
		return nil
	})
	if err != nil {
		t.Fatalf("InTx Append: %v", err)
	}
	return sealed
}

func wantNotFound(t *testing.T, err error, what string) {
	t.Helper()
	var ce *ports.ConflictError
	if !errors.As(err, &ce) || ce.Kind != ports.ConflictNotFound {
		t.Fatalf("%s: error = %v, want ConflictNotFound", what, err)
	}
}

func rangeFrom(t *testing.T, st *memstore.Store, from int64, limit int) ([]audit.Event, error) {
	t.Helper()
	var out []audit.Event
	err := st.InTx(context.Background(), func(tx ports.Tx) error {
		var err error
		out, err = tx.Audit().Range(context.Background(), from, limit)
		return err
	})
	return out, err
}

func TestAppendSealsAndSequences(t *testing.T) {
	st := memstore.New()
	first := appendOne(t, st)
	if first.Seq != 1 {
		t.Errorf("first event seq = %d, want 1", first.Seq)
	}
	if first.PrevHash != audit.Genesis {
		t.Errorf("first event prev_hash = %s, want Genesis", first.PrevHash)
	}
	second := appendOne(t, st)
	if second.Seq != 2 || second.PrevHash != first.Hash {
		t.Errorf("second event = (seq %d, prev %s), want (2, %s)", second.Seq, second.PrevHash, first.Hash)
	}
	third := appendOne(t, st)

	// The whole chain verifies from Genesis, and Range pages it in order.
	events := st.Events()
	if err := audit.Verify(audit.Genesis, events); err != nil {
		t.Fatalf("Verify: %v", err)
	}
	ranged, err := rangeFrom(t, st, 2, 10)
	if err != nil || len(ranged) != 2 || ranged[0].Seq != 2 || ranged[1].Seq != third.Seq {
		t.Fatalf("Range(2, 10) = %v (err %v), want events 2 and 3", ranged, err)
	}
}

func TestCheckpointRoundtripReturnsLatest(t *testing.T) {
	st := memstore.New()
	first := appendOne(t, st)
	second := appendOne(t, st)

	cp := audit.Checkpoint{Seq: second.Seq, Hash: second.Hash, At: at, KeyID: "ed25519:aa", Signature: "ab"}
	if err := st.InTx(context.Background(), func(tx ports.Tx) error {
		return tx.Audit().SaveCheckpoint(context.Background(), cp)
	}); err != nil {
		t.Fatalf("SaveCheckpoint: %v", err)
	}

	// The checkpoint survives its own transaction (the InTx snapshot must
	// carry checkpoints, or a commit would silently drop them), and the
	// read returns the latest one.
	var got audit.Checkpoint
	err := st.InTx(context.Background(), func(tx ports.Tx) error {
		var err error
		got, err = tx.Audit().Checkpoint(context.Background())
		return err
	})
	if err != nil {
		t.Fatalf("Checkpoint: %v", err)
	}
	if got != cp {
		t.Errorf("Checkpoint() = %+v, want %+v", got, cp)
	}

	// A second checkpoint supersedes the first.
	newer := audit.Checkpoint{Seq: first.Seq, Hash: first.Hash, At: at.Add(time.Minute), KeyID: "ed25519:aa", Signature: "cd"}
	if err := st.InTx(context.Background(), func(tx ports.Tx) error {
		return tx.Audit().SaveCheckpoint(context.Background(), newer)
	}); err != nil {
		t.Fatalf("SaveCheckpoint (second): %v", err)
	}
	err = st.InTx(context.Background(), func(tx ports.Tx) error {
		var err error
		got, err = tx.Audit().Checkpoint(context.Background())
		return err
	})
	if err != nil || got != newer {
		t.Fatalf("Checkpoint() after two saves = %+v (err %v), want the second %+v", got, err, newer)
	}
	if all := st.Checkpoints(); len(all) != 2 {
		t.Errorf("Checkpoints() has %d rows, want 2", len(all))
	}
}

func TestCheckpointAbsentReturnsNotFound(t *testing.T) {
	st := memstore.New()
	var err error
	_ = st.InTx(context.Background(), func(tx ports.Tx) error {
		_, err = tx.Audit().Checkpoint(context.Background())
		return nil
	})
	wantNotFound(t, err, "reading a checkpoint from an empty store")
}

func TestRolledBackSaveLeavesNoCheckpoint(t *testing.T) {
	st := memstore.New()
	sentinel := errors.New("boom")
	err := st.InTx(context.Background(), func(tx ports.Tx) error {
		if err := tx.Audit().SaveCheckpoint(context.Background(), audit.Checkpoint{Seq: 1, Signature: "ab"}); err != nil {
			return err
		}
		return sentinel
	})
	if !errors.Is(err, sentinel) {
		t.Fatalf("InTx error = %v, want the sentinel", err)
	}

	var readErr error
	_ = st.InTx(context.Background(), func(tx ports.Tx) error {
		_, readErr = tx.Audit().Checkpoint(context.Background())
		return nil
	})
	wantNotFound(t, readErr, "reading a checkpoint after a rolled-back save")
	if all := st.Checkpoints(); len(all) != 0 {
		t.Errorf("Checkpoints() after rollback = %d rows, want none", len(all))
	}
}
