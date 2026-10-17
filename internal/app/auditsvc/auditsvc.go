// Package auditsvc owns the audit chain's maintenance: signing the head
// as a checkpoint, and verifying the chain — whole, or from the last
// checkpoint.
//
// What it does not own is deliberate. It never appends events: the
// service performing a state transition writes its own audit row in the
// same transaction (I-6), so the chain is only ever as fresh as the
// decisions it records. It does not decide when to checkpoint — that
// cadence belongs to the caller (a sweep after a batch, a timer at
// night); it only guarantees that when a checkpoint exists it is a real
// signature over the head the store actually holds. And it does not
// authorize reads: the chain is a public record.
//
// Verification has two modes. from 1 recomputes every hash from Genesis —
// the audit mode, for re-establishing the whole chain. Anything else
// anchors on the last checkpoint: its signature and the position it
// names are checked, and only what came after is walked (with no
// checkpoint, the anchor is Genesis anyway, so the default is still a
// full walk). A checkpoint buys a shorter walk, not a new truth —
// content edits inside the signed prefix are invisible to the anchored
// walk, and catching those is what the audit mode is for.
package auditsvc

import (
	"context"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/ports"
)

// verifyPageSize bounds each Range call while walking the chain. The
// chain grows without bound; the walk must not build a slice to match.
const verifyPageSize = 100

// Service signs checkpoints and verifies the audit chain. Store, Clock
// and Signer are wired by main; a nil Signer is refused rather than
// quietly skipped — a checkpoint nobody can verify is just a row, and a
// verification without the signature check is half a check.
type Service struct {
	Store  ports.Store
	Clock  ports.Clock
	Signer ports.Signer
}

// VerifyResult reports what a verification actually covered, so a caller
// can tell "verified everything" from "verified the new part" from
// "verified nothing new" — all honest answers to different questions.
type VerifyResult struct {
	// AnchoredOn is the seq the walk started after: the last
	// checkpoint's seq, or 0 for Genesis. It names what vouched for
	// everything below From.
	AnchoredOn int64
	// From and To bound the events whose hashes the walk recomputed.
	// Both are 0 when nothing was walked — an empty chain, or a
	// window already covered by the checkpoint's signature.
	From, To int64
	// CheckedCheckpoint reports whether a checkpoint's signature was
	// checked against the chain. False means there was none.
	CheckedCheckpoint bool
}

// Checkpoint signs the current head and stores the signature in one
// transaction (I-6): a checkpoint either exists as a row the store
// honours, or does not exist at all.
//
// Calling it again while the head holds returns the standing checkpoint
// — an unmoved head needs no second signature. A head that moved under
// a standing checkpoint is refused: the standing row names the old
// hash, and signing the new position over it would leave a signature
// chain an attacker could replay around. If the head truly moved, the
// new checkpoint's seq is ahead of the standing one's, and the caller
// who wants it can have it — but never at the same seq.
func (s Service) Checkpoint(ctx context.Context) (audit.Checkpoint, error) {
	if s.Signer == nil {
		return audit.Checkpoint{}, errors.New("auditsvc: Checkpoint without a signer: a signature nobody can verify is just a row")
	}
	var cp audit.Checkpoint
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		repo := tx.Audit()

		hash, seq, err := repo.Head(ctx)
		if err != nil {
			return err
		}
		if seq == 0 {
			return errors.New("auditsvc: refusing to checkpoint an empty chain: there is nothing to vouch for")
		}

		// The standing checkpoint decides whether this is a fresh
		// signature, an idempotent repeat, or a refusal.
		existing, err := repo.Checkpoint(ctx)
		if err != nil && !isNotFound(err) {
			return err
		}
		if err == nil {
			if existing.Seq == seq && existing.Hash == hash {
				cp = existing
				return nil
			}
			if existing.Seq == seq {
				return fmt.Errorf("auditsvc: refusing to re-sign seq %d: the head moved to %s under a standing checkpoint that says %s", seq, hash, existing.Hash)
			}
			if existing.Seq > seq {
				return fmt.Errorf("auditsvc: refusing to checkpoint seq %d: the head is behind the standing checkpoint at seq %d", seq, existing.Seq)
			}
		}

		keyID, err := s.Signer.KeyID(ctx)
		if err != nil {
			return fmt.Errorf("auditsvc: reading the signer's key id: %w", err)
		}
		now := s.now()
		payload, err := audit.CheckpointPayload(seq, hash, now, keyID)
		if err != nil {
			return fmt.Errorf("auditsvc: building the checkpoint payload: %w", err)
		}
		sig, signedAs, err := s.Signer.Sign(ctx, payload)
		if err != nil {
			return fmt.Errorf("auditsvc: signing the checkpoint: %w", err)
		}
		if signedAs != keyID {
			return fmt.Errorf("auditsvc: the signer signed as %s but answers for %s: refusing to store a checkpoint under a key it does not speak for", signedAs, keyID)
		}

		cp = audit.Checkpoint{
			Seq:       seq,
			Hash:      hash,
			At:        now,
			KeyID:     keyID,
			Signature: hex.EncodeToString(sig),
		}
		if err := repo.SaveCheckpoint(ctx, cp); err != nil {
			return fmt.Errorf("auditsvc: saving the checkpoint: %w", err)
		}
		return nil
	})
	if err != nil {
		return audit.Checkpoint{}, err
	}
	return cp, nil
}

// Verify walks the audit chain and recomputes every hash it covers,
// naming the first breakage it meets (T7).
//
// from 1 is the audit mode: the walk starts at Genesis and recomputes
// everything. Any other from anchors on the last checkpoint — its
// signature is checked against the row the store holds at the position
// it names, and the walk covers only what came after it. With no
// checkpoint stored the anchor is Genesis anyway, so the default (from
// 0) is a full walk on a young chain and shrinks as checkpoints accrue.
// to > 0 caps the walk at that seq (0 walks to the head), for callers
// that verify incrementally.
//
// A standing checkpoint is checked before any mode is chosen: a forged
// or moved checkpoint row is itself a finding, whatever mode asked for.
// The walk reads pages, so a long chain costs memory proportional to a
// page, not to history. Everything happens in one read transaction, so
// the result describes a chain that held still while it was checked.
func (s Service) Verify(ctx context.Context, from, to int64) (VerifyResult, error) {
	if s.Signer == nil {
		return VerifyResult{}, errors.New("auditsvc: Verify without a signer: the checkpoint signature is half the check")
	}
	var res VerifyResult
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		repo := tx.Audit()

		// The anchor: Genesis, or the last checkpoint — after its
		// signature has been held against the chain it claims to
		// vouch for.
		prevHash := audit.Genesis
		var first int64 = 1
		cp, err := repo.Checkpoint(ctx)
		switch {
		case err == nil:
			if err := s.checkCheckpoint(ctx, repo, cp); err != nil {
				return err
			}
			res.CheckedCheckpoint = true
			prevHash, first = cp.Hash, cp.Seq+1
		case isNotFound(err):
			// No checkpoint: the anchor is Genesis, whatever the
			// caller asked for.
		default:
			return err
		}
		if from == 1 {
			// The audit mode recomputes the whole chain, signed
			// prefix included. It still pays for the checkpoint
			// check above — a forged row is a finding here too.
			prevHash, first = audit.Genesis, 1
		}
		res.AnchoredOn = first - 1

		for {
			limit := verifyPageSize
			if to > 0 {
				remaining := to - first + 1
				if remaining <= 0 {
					break
				}
				if remaining < int64(limit) {
					limit = int(remaining)
				}
			}
			page, err := repo.Range(ctx, first, limit)
			if err != nil {
				return fmt.Errorf("auditsvc: reading the chain from seq %d: %w", first, err)
			}
			if len(page) == 0 {
				break
			}
			// The store serves what it holds; if the first row of
			// the page is not where the walk is, the chain itself
			// is off — a deleted prefix shows up exactly here.
			if page[0].Seq != first {
				return audit.Breakage{Seq: page[0].Seq, Kind: "sequence-gap"}
			}
			if err := audit.Verify(prevHash, page); err != nil {
				return fmt.Errorf("auditsvc: verifying seqs %d-%d: %w", first, page[len(page)-1].Seq, err)
			}
			if res.From == 0 {
				res.From = page[0].Seq
			}
			res.To = page[len(page)-1].Seq
			prevHash = page[len(page)-1].Hash
			first = page[len(page)-1].Seq + 1
			if to > 0 && res.To >= to {
				break
			}
			if len(page) < limit {
				break
			}
		}
		return nil
	})
	if err != nil {
		return VerifyResult{}, err
	}
	return res, nil
}

// checkCheckpoint holds a stored checkpoint against the chain: first the
// signature (an offline verifier rebuilds the same payload from the row
// and checks it against the named key), then the position (the row at
// the signed seq must still carry the signed hash). A signature that
// verifies but points past the chain, or at a row that changed, is not
// a checkpoint the walk may anchor on.
func (s Service) checkCheckpoint(ctx context.Context, repo ports.AuditRepo, cp audit.Checkpoint) error {
	sig, err := hex.DecodeString(cp.Signature)
	if err != nil {
		return fmt.Errorf("auditsvc: the checkpoint at seq %d has a signature that is not hex: %w", cp.Seq, err)
	}
	payload, err := audit.CheckpointPayload(cp.Seq, cp.Hash, cp.At, cp.KeyID)
	if err != nil {
		return fmt.Errorf("auditsvc: rebuilding the checkpoint payload for seq %d: %w", cp.Seq, err)
	}
	if err := s.Signer.Verify(ctx, payload, sig, cp.KeyID); err != nil {
		return fmt.Errorf("auditsvc: the checkpoint at seq %d does not verify: %w", cp.Seq, err)
	}
	rows, err := repo.Range(ctx, cp.Seq, 1)
	if err != nil {
		return fmt.Errorf("auditsvc: checking where the checkpoint at seq %d points: %w", cp.Seq, err)
	}
	if len(rows) == 0 {
		return fmt.Errorf("auditsvc: the checkpoint signs seq %d but the chain has nothing there", cp.Seq)
	}
	if rows[0].Hash != cp.Hash {
		return fmt.Errorf("auditsvc: the checkpoint signs hash %s at seq %d but the chain holds %s there", cp.Hash, cp.Seq, rows[0].Hash)
	}
	return nil
}

// now reads the clock the way the rest of the services do: an injected
// clock for tests, the machine's word for production.
func (s Service) now() time.Time {
	if s.Clock == nil {
		return time.Now()
	}
	return s.Clock.Now()
}

// isNotFound tells a missing row from a broken store, the gatesvc way.
func isNotFound(err error) bool {
	var ce *ports.ConflictError
	return errors.As(err, &ce) && ce.Kind == ports.ConflictNotFound
}
