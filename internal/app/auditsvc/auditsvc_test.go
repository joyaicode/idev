package auditsvc_test

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/memstore"
	"github.com/idev/internal/app/auditsvc"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/canonical"
)

// The tests pin the audit service's promises: a checkpoint is a real
// signature over the head as the store holds it (I-3 — an agent must not
// be able to forge one), signing and saving share one transaction (I-6),
// a head that moved under a standing checkpoint never gets a second
// signature over the same position, and verification walks the chain it
// actually finds and names the exact breakage (T7 — an attacker with
// write access to the store). The trust model is pinned too: a checkpoint
// buys a shorter walk, not a new truth — tampering inside the signed
// prefix is invisible to the anchored walk, and only the audit mode
// (from 1) recomputes it.

var at = time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)

// wrongDigest is a well-formed digest that matches nothing: the tamperer's
// fabricated link.
const wrongDigest = "sha256:0101010101010101010101010101010101010101010101010101010101010101"

type fixedClock struct{ t time.Time }

func (c fixedClock) Now() time.Time { return c.t }

// edSigner is a real ed25519 key pair. Checkpoints are signed with real
// cryptography so the tampering tests exercise the exact bytes an offline
// verifier will rebuild; a fake that signs everything with a constant
// would pass while binding nothing.
type edSigner struct {
	pub  ed25519.PublicKey
	priv ed25519.PrivateKey
}

func newSigner(t *testing.T) *edSigner {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("ed25519.GenerateKey: %v", err)
	}
	return &edSigner{pub: pub, priv: priv}
}

// keyID is the shape a stored checkpoint names its key by.
func (s *edSigner) keyID() string {
	return "ed25519:" + hex.EncodeToString(s.pub[:8])
}

func (s *edSigner) Sign(ctx context.Context, payload []byte) ([]byte, string, error) {
	return ed25519.Sign(s.priv, payload), s.keyID(), nil
}

func (s *edSigner) Verify(ctx context.Context, payload, sig []byte, keyID string) error {
	if keyID != s.keyID() {
		return fmt.Errorf("unknown key %s", keyID)
	}
	if !ed25519.Verify(s.pub, payload, sig) {
		return errors.New("the signature does not verify")
	}
	return nil
}

func (s *edSigner) KeyID(ctx context.Context) (string, error) { return s.keyID(), nil }

func newSvc(t *testing.T) (auditsvc.Service, *memstore.Store, *edSigner) {
	t.Helper()
	st := memstore.New()
	signer := newSigner(t)
	s := auditsvc.Service{
		Store:  st,
		Clock:  fixedClock{t: at},
		Signer: signer,
	}
	return s, st, signer
}

// appendEvents appends n well-formed events through transactions, the way
// the transitioning services do — auditsvc itself never appends.
func appendEvents(t *testing.T, st *memstore.Store, n int) {
	t.Helper()
	for i := 0; i < n; i++ {
		err := st.InTx(context.Background(), func(tx ports.Tx) error {
			_, err := tx.Audit().Append(context.Background(), audit.Event{
				At:     at,
				Action: audit.ActionLeaseAcquired,
				Actor:  audit.Actor{Handle: "conductor@claude", Kind: "agent"},
			})
			return err
		})
		if err != nil {
			t.Fatalf("appending event %d: %v", i+1, err)
		}
	}
}

// headOf reads the head the way the service does, through a transaction.
func headOf(t *testing.T, st *memstore.Store) (canonical.Digest, int64) {
	t.Helper()
	var hash canonical.Digest
	var seq int64
	if err := st.InTx(context.Background(), func(tx ports.Tx) error {
		h, s, err := tx.Audit().Head(context.Background())
		hash, seq = h, s
		return err
	}); err != nil {
		t.Fatalf("reading the head: %v", err)
	}
	return hash, seq
}

func readCheckpoint(t *testing.T, st *memstore.Store) (audit.Checkpoint, error) {
	t.Helper()
	var cp audit.Checkpoint
	var err error
	_ = st.InTx(context.Background(), func(tx ports.Tx) error {
		cp, err = tx.Audit().Checkpoint(context.Background())
		return nil
	})
	return cp, err
}

func wantNotFound(t *testing.T, err error, what string) {
	t.Helper()
	var ce *ports.ConflictError
	if !errors.As(err, &ce) || ce.Kind != ports.ConflictNotFound {
		t.Fatalf("%s: error = %v, want ConflictNotFound", what, err)
	}
}

func wantMsg(t *testing.T, err error, substr, what string) {
	t.Helper()
	if err == nil || !strings.Contains(err.Error(), substr) {
		t.Fatalf("%s: error = %v, want it to mention %q", what, err, substr)
	}
}

func wantBreakage(t *testing.T, err error, kind string, seq int64, what string) {
	t.Helper()
	var br audit.Breakage
	if !errors.As(err, &br) {
		t.Fatalf("%s: error = %v, want a breakage", what, err)
	}
	if br.Kind != kind || br.Seq != seq {
		t.Fatalf("%s: breakage = %s at %d, want %s at %d", what, br.Kind, br.Seq, kind, seq)
	}
}

func TestCheckpointSignsAndSavesTheHead(t *testing.T) {
	s, st, signer := newSvc(t)
	appendEvents(t, st, 3)

	cp, err := s.Checkpoint(context.Background())
	if err != nil {
		t.Fatalf("Checkpoint: %v", err)
	}
	hash, seq := headOf(t, st)
	if cp.Seq != seq || cp.Hash != hash {
		t.Errorf("checkpoint = (seq %d, %s), want the head (seq %d, %s)", cp.Seq, cp.Hash, seq, hash)
	}
	if cp.KeyID != signer.keyID() {
		t.Errorf("checkpoint key id = %q, want %q", cp.KeyID, signer.keyID())
	}
	if !cp.At.Equal(at) {
		t.Errorf("checkpoint at = %v, want the clock's %v", cp.At, at)
	}

	// The signature must be exactly what an offline verifier rebuilds:
	// the payload bytes, the hex, the real key.
	sig, err := hex.DecodeString(cp.Signature)
	if err != nil {
		t.Fatalf("checkpoint signature is not hex: %v", err)
	}
	payload, err := audit.CheckpointPayload(cp.Seq, cp.Hash, cp.At, cp.KeyID)
	if err != nil {
		t.Fatalf("CheckpointPayload: %v", err)
	}
	if err := signer.Verify(context.Background(), payload, sig, cp.KeyID); err != nil {
		t.Errorf("the signature does not verify: %v", err)
	}

	// And the store holds exactly that row.
	saved, err := readCheckpoint(t, st)
	if err != nil || saved != cp {
		t.Fatalf("the saved checkpoint = %+v (err %v), want %+v", saved, err, cp)
	}
	if all := st.Checkpoints(); len(all) != 1 || all[0] != cp {
		t.Errorf("Checkpoints() = %+v, want exactly the saved one", all)
	}
}

func TestCheckpointRefusesAnEmptyChain(t *testing.T) {
	s, st, _ := newSvc(t)

	_, err := s.Checkpoint(context.Background())
	wantMsg(t, err, "empty", "checkpointing an empty chain")
	if all := st.Checkpoints(); len(all) != 0 {
		t.Errorf("Checkpoints() = %d rows, want none", len(all))
	}
	_, err = readCheckpoint(t, st)
	wantNotFound(t, err, "reading a checkpoint after the refusal")
}

func TestCheckpointIsIdempotentWhileTheHeadHolds(t *testing.T) {
	s, st, _ := newSvc(t)
	appendEvents(t, st, 2)

	first, err := s.Checkpoint(context.Background())
	if err != nil {
		t.Fatalf("Checkpoint: %v", err)
	}
	again, err := s.Checkpoint(context.Background())
	if err != nil {
		t.Fatalf("Checkpoint again: %v", err)
	}
	if again != first {
		t.Errorf("second checkpoint = %+v, want the standing %+v", again, first)
	}
	if all := st.Checkpoints(); len(all) != 1 {
		t.Errorf("Checkpoints() = %d rows, want 1: an unmoved head needs no second signature", len(all))
	}

	// A new event moves the head, so the next checkpoint is a new
	// position — and a second row.
	appendEvents(t, st, 1)
	moved, err := s.Checkpoint(context.Background())
	if err != nil {
		t.Fatalf("Checkpoint after an append: %v", err)
	}
	if moved.Seq != 3 || moved.Hash == first.Hash {
		t.Errorf("checkpoint after the append = (seq %d, %s), want (3, a new hash)", moved.Seq, moved.Hash)
	}
	if all := st.Checkpoints(); len(all) != 2 {
		t.Errorf("Checkpoints() after the append = %d rows, want 2", len(all))
	}
}

func TestCheckpointLeavesNothingBehindWhenTheStoreFails(t *testing.T) {
	s, st, _ := newSvc(t)
	appendEvents(t, st, 2)
	st.FailOn["audit.SaveCheckpoint"] = errors.New("disk full")

	_, err := s.Checkpoint(context.Background())
	wantMsg(t, err, "disk full", "checkpointing while the store fails")

	// I-6: signing is stateless, but the row must not exist. What a
	// failed save claimed, the store does not hold.
	if all := st.Checkpoints(); len(all) != 0 {
		t.Errorf("Checkpoints() after the failed save = %d rows, want none", len(all))
	}
}

func TestCheckpointRefusesToResignAMovedHead(t *testing.T) {
	s, st, _ := newSvc(t)
	appendEvents(t, st, 2)
	if _, err := s.Checkpoint(context.Background()); err != nil {
		t.Fatalf("Checkpoint: %v", err)
	}

	// The tamperer rewrites the head's content and reseals it, so the
	// stored hash at the checkpointed position changes. The standing
	// checkpoint still names the old hash; putting a fresh signature
	// over the moved position would vouch for the rewrite.
	st.TamperEvent(2, func(e audit.Event) audit.Event {
		e.Actor = audit.Actor{Handle: "attacker@example", Kind: "human"}
		sealed, _ := audit.Seal(e, e.PrevHash)
		return sealed
	})

	_, err := s.Checkpoint(context.Background())
	wantMsg(t, err, "refusing", "re-checkpointing a moved head")
	if all := st.Checkpoints(); len(all) != 1 {
		t.Errorf("Checkpoints() = %d rows, want the one standing row", len(all))
	}
}

func TestVerifyRecomputesFromGenesis(t *testing.T) {
	s, st, _ := newSvc(t)
	appendEvents(t, st, 3)

	res, err := s.Verify(context.Background(), 1, 0)
	if err != nil {
		t.Fatalf("Verify from Genesis: %v", err)
	}
	want := auditsvc.VerifyResult{AnchoredOn: 0, From: 1, To: 3}
	if res != want {
		t.Errorf("Verify result = %+v, want %+v", res, want)
	}

	// from 0 is the nightly default. With no checkpoint there is
	// nothing to anchor on, so the walk is the full one.
	res, err = s.Verify(context.Background(), 0, 0)
	if err != nil || res != want {
		t.Errorf("Verify(0, 0) with no checkpoint = (%+v, %v), want the full walk", res, err)
	}

	// An empty chain has nothing to walk and verifies trivially.
	fresh, _, _ := newSvc(t)
	res, err = fresh.Verify(context.Background(), 1, 0)
	if err != nil || res != (auditsvc.VerifyResult{}) {
		t.Errorf("Verify on the empty chain = (%+v, %v), want the zero result", res, err)
	}
}

func TestVerifyNamesTheBreakage(t *testing.T) {
	cases := []struct {
		name   string
		tamper func(st *memstore.Store)
		kind   string
		seq    int64
	}{
		{
			// Content edited without resealing: the stored hash no
			// longer covers the row.
			name: "hash mismatch on edited content",
			tamper: func(st *memstore.Store) {
				st.TamperEvent(2, func(e audit.Event) audit.Event {
					e.Actor = audit.Actor{Handle: "attacker@example", Kind: "human"}
					return e
				})
			},
			kind: "hash-mismatch",
			seq:  2,
		},
		{
			// The tamperer reseals the row, so its own hash is
			// honest — but it points at a fabricated predecessor.
			name: "link mismatch on a resealed row",
			tamper: func(st *memstore.Store) {
				st.TamperEvent(2, func(e audit.Event) audit.Event {
					e.PrevHash = wrongDigest
					sealed, _ := audit.Seal(e, e.PrevHash)
					return sealed
				})
			},
			kind: "link-mismatch",
			seq:  2,
		},
		{
			// A resealed row keeps an honest link but claims a
			// position the walk did not expect.
			name: "sequence gap on a renumbered row",
			tamper: func(st *memstore.Store) {
				st.TamperEvent(3, func(e audit.Event) audit.Event {
					e.Seq = 4
					sealed, _ := audit.Seal(e, e.PrevHash)
					return sealed
				})
			},
			kind: "sequence-gap",
			seq:  4,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			s, st, _ := newSvc(t)
			appendEvents(t, st, 3)
			tc.tamper(st)
			_, err := s.Verify(context.Background(), 1, 0)
			wantBreakage(t, err, tc.kind, tc.seq, tc.name)
		})
	}
}

func TestVerifyAnchorsOnTheLastCheckpoint(t *testing.T) {
	s, st, _ := newSvc(t)
	appendEvents(t, st, 5)
	cp, err := s.Checkpoint(context.Background())
	if err != nil {
		t.Fatalf("Checkpoint: %v", err)
	}
	appendEvents(t, st, 3)

	res, err := s.Verify(context.Background(), 0, 0)
	if err != nil {
		t.Fatalf("Verify: %v", err)
	}
	want := auditsvc.VerifyResult{AnchoredOn: cp.Seq, From: cp.Seq + 1, To: 8, CheckedCheckpoint: true}
	if res != want {
		t.Errorf("Verify result = %+v, want %+v", res, want)
	}

	// Tampering after the checkpoint is the anchored walk's job.
	st.TamperEvent(7, func(e audit.Event) audit.Event {
		e.Actor = audit.Actor{Handle: "attacker@example", Kind: "human"}
		return e
	})
	_, err = s.Verify(context.Background(), 0, 0)
	wantBreakage(t, err, "hash-mismatch", 7, "verifying a post-checkpoint tamper")

	// The pinned prefix is the other half of the trust model: the
	// anchored walk does not recompute it (the checkpoint vouches for
	// it), and the audit mode does. A service that quietly walked the
	// prefix in the nightly mode would make the checkpoint pointless;
	// one that never recomputed it would make it a blind spot.
	s2, st2, _ := newSvc(t)
	appendEvents(t, st2, 5)
	if _, err := s2.Checkpoint(context.Background()); err != nil {
		t.Fatalf("Checkpoint: %v", err)
	}
	appendEvents(t, st2, 3)
	st2.TamperEvent(2, func(e audit.Event) audit.Event {
		e.Actor = audit.Actor{Handle: "attacker@example", Kind: "human"}
		return e
	})
	if _, err := s2.Verify(context.Background(), 0, 0); err != nil {
		t.Errorf("anchored Verify over a tampered prefix = %v, want nil: the prefix is the checkpoint's to vouch for", err)
	}
	_, err = s2.Verify(context.Background(), 1, 0)
	wantBreakage(t, err, "hash-mismatch", 2, "the audit mode recomputing the prefix")
}

func TestVerifyCatchesACheckpointThatDoesNotMatchTheChain(t *testing.T) {
	saveCP := func(t *testing.T, st *memstore.Store, cp audit.Checkpoint) {
		t.Helper()
		if err := st.InTx(context.Background(), func(tx ports.Tx) error {
			return tx.Audit().SaveCheckpoint(context.Background(), cp)
		}); err != nil {
			t.Fatalf("SaveCheckpoint: %v", err)
		}
	}

	t.Run("a forged signature", func(t *testing.T) {
		s, st, signer := newSvc(t)
		appendEvents(t, st, 3)
		hash, seq := headOf(t, st)
		// A row that looks like a checkpoint but was never signed by
		// the key it names — written straight into the store, the
		// way an attacker with write access would.
		saveCP(t, st, audit.Checkpoint{Seq: seq, Hash: hash, At: at, KeyID: signer.keyID(), Signature: "deadbeef"})
		_, err := s.Verify(context.Background(), 0, 0)
		wantMsg(t, err, "does not verify", "verifying a forged checkpoint")
	})

	t.Run("bytes edited after signing", func(t *testing.T) {
		s, st, _ := newSvc(t)
		appendEvents(t, st, 3)
		cp, err := s.Checkpoint(context.Background())
		if err != nil {
			t.Fatalf("Checkpoint: %v", err)
		}
		// The signature covers the exact bytes; editing the hash
		// after signing breaks it, whatever was edited.
		cp.Hash = wrongDigest
		saveCP(t, st, cp)
		_, err = s.Verify(context.Background(), 0, 0)
		wantMsg(t, err, "does not verify", "verifying an edited checkpoint")
	})

	t.Run("a position the chain no longer holds", func(t *testing.T) {
		s, st, _ := newSvc(t)
		appendEvents(t, st, 5)
		if _, err := s.Checkpoint(context.Background()); err != nil {
			t.Fatalf("Checkpoint: %v", err)
		}
		appendEvents(t, st, 3)
		// The event at the checkpointed position is rewritten and
		// resealed. Its successor still links to the OLD hash, so
		// the walk from the checkpoint would pass — only the
		// position check binds the signature to the chain.
		st.TamperEvent(5, func(e audit.Event) audit.Event {
			e.Actor = audit.Actor{Handle: "attacker@example", Kind: "human"}
			sealed, _ := audit.Seal(e, e.PrevHash)
			return sealed
		})
		_, err := s.Verify(context.Background(), 0, 0)
		wantMsg(t, err, "the checkpoint signs", "verifying a moved position")
	})

	t.Run("a signature over a seq the chain does not have", func(t *testing.T) {
		s, st, signer := newSvc(t)
		appendEvents(t, st, 3)
		// A real signature over a position this chain never held —
		// a checkpoint from elsewhere, or a truncated chain.
		payload, err := audit.CheckpointPayload(99, wrongDigest, at, signer.keyID())
		if err != nil {
			t.Fatalf("CheckpointPayload: %v", err)
		}
		sig, _, err := signer.Sign(context.Background(), payload)
		if err != nil {
			t.Fatalf("Sign: %v", err)
		}
		saveCP(t, st, audit.Checkpoint{Seq: 99, Hash: wrongDigest, At: at, KeyID: signer.keyID(), Signature: hex.EncodeToString(sig)})
		_, err = s.Verify(context.Background(), 0, 0)
		wantMsg(t, err, "the chain has nothing", "verifying a checkpoint beyond the head")
	})
}

func TestVerifyHonoursTheUpperBound(t *testing.T) {
	s, st, _ := newSvc(t)
	appendEvents(t, st, 8)

	res, err := s.Verify(context.Background(), 1, 5)
	if err != nil {
		t.Fatalf("Verify(1, 5): %v", err)
	}
	if res.AnchoredOn != 0 || res.From != 1 || res.To != 5 {
		t.Errorf("Verify(1, 5) = %+v, want the walk to stop at seq 5", res)
	}

	// A tampered event outside the window is not the walk's to judge.
	st.TamperEvent(6, func(e audit.Event) audit.Event {
		e.Actor = audit.Actor{Handle: "attacker@example", Kind: "human"}
		return e
	})
	if _, err := s.Verify(context.Background(), 1, 5); err != nil {
		t.Errorf("Verify(1, 5) over a tampered seq 6 = %v, want nil: outside the window", err)
	}
	_, err = s.Verify(context.Background(), 1, 0)
	wantBreakage(t, err, "hash-mismatch", 6, "the full walk meeting the same tamper")

	// With a checkpoint in the middle, the window is measured from the
	// anchor: to 6 walks only seq 6.
	s2, st2, _ := newSvc(t)
	appendEvents(t, st2, 5)
	if _, err := s2.Checkpoint(context.Background()); err != nil {
		t.Fatalf("Checkpoint: %v", err)
	}
	appendEvents(t, st2, 3)
	st2.TamperEvent(8, func(e audit.Event) audit.Event {
		e.Actor = audit.Actor{Handle: "attacker@example", Kind: "human"}
		return e
	})
	res, err = s2.Verify(context.Background(), 0, 6)
	if err != nil || res.From != 6 || res.To != 6 {
		t.Errorf("Verify(0, 6) anchored = (%+v, %v), want only seq 6 walked", res, err)
	}
}

func TestRefusesWithoutASigner(t *testing.T) {
	st := memstore.New()
	appendEvents(t, st, 1)
	s := auditsvc.Service{Store: st, Clock: fixedClock{t: at}}

	if _, err := s.Checkpoint(context.Background()); err == nil {
		t.Error("Checkpoint without a signer = nil, want a refusal: a signature nobody can verify is just a row")
	}
	if _, err := s.Verify(context.Background(), 0, 0); err == nil {
		t.Error("Verify without a signer = nil, want a refusal: the signature is half the check")
	}
}
