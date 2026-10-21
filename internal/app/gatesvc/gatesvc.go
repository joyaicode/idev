// Package gatesvc is where questions to a person are asked and answered.
//
// The design's invariant I-3 — the one thing an agent must not be able to
// do — is a human signature, and this service is the only path to one. The
// domain package decides whether a submission is valid; this package owns
// the three things that must not be decided anywhere else:
//
//   - the transaction boundary: a gate changing and its audit event are
//     written together or not at all (I-6);
//   - the authz questions: does the principal hold the approver action,
//     and does their scope cover this feature;
//   - the signature: every recorded approval is signed over the exact
//     bytes of its payload, so the record can be verified offline against
//     the content digest it names (I-4).
//
// Refused submissions write nothing — no approval, no gate change, no
// audit event. A refusal is an answer to the caller, not a fact about the
// world.
package gatesvc

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/domain/signoff"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/canonical"
)

// The authz questions a decision asks. One action, two scopes: the
// wildcard scope asks whether the principal holds the approver action at
// all, and the feature scope asks whether this feature is theirs to
// approve. An authorizer that answers the wildcard question for any
// principal granted the action somewhere lets an approver scoped to a
// single feature pass the role question; the feature question does the
// narrowing.
const (
	authzAction   = "gate.approve"
	authzAnyScope = "*"
)

// The channels an answer can arrive on, and the assurance each proves.
// Assurance is not a parameter anyone chooses: it follows from how the
// answer arrived (design §10.4), so the channel vocabulary is this
// package's contract with the adapters.
const (
	// #nosec G101 -- the string names a channel, not a credential: the
	// token itself is minted at answer time and never stored anywhere.
	ChannelLocalTokenTTY = "local_token_tty" // a local token typed in a TTY
	ChannelOIDC          = "oidc"            // a logged-in web session
	ChannelWebAuthn      = "webauthn"        // a user-verifying authenticator
	ChannelOIDCWebAuthn  = "oidc_webauthn"   // a session plus an authenticator
)

// approvalSchema tags the signed payload, so a verifier can tell which
// contract a signature was made under.
const approvalSchema = "idev.approval/1"

// Service asks, answers, withdraws and expires gates.
type Service struct {
	Store ports.Store
	Clock ports.Clock
	IDs   ports.IDGen
	// Signer signs approvals. A service with no signer cannot record a
	// decision: Decide refuses rather than storing an approval nobody can
	// verify.
	Signer ports.Signer
	// Authorizer answers the two questions a decision asks. Nil is the
	// safe default: every question is answered no, so a service with no
	// authorizer wired can open gates but nobody can pass one.
	Authorizer ports.Authorizer
	// Policy is the per-deployment assurance matrix, applied when a gate
	// is opened and again when it is answered.
	Policy gate.Policy
}

// AskParams describes the question being put to a person.
type AskParams struct {
	Type   gate.Type
	RunID  string
	StepID string
	// Feature is the feature's ID, not its display name: the authz scope
	// question and the audit chain are keyed by it.
	Feature string
	Risk    gate.RiskTier
	Subject gate.Subject
	// Origin is the origin a defect_origin question asks the person to
	// choose.
	Origin    string
	WillWrite []string
	Proof     string
	TTL       time.Duration
	Actor     ports.Principal
	// SubjectRoot and SubjectPaths are the files Subject.Digest covers.
	// Written in the same transaction as the gate. Empty means the gate
	// binds to the question itself.
	SubjectRoot  string
	SubjectPaths []string
}

// Ask opens a gate: one pending question, written with the event that says
// it was asked. The domain applies the asking rules — a subject digest to
// bind to, the fields that will be written, proof to show, the default TTL
// when none is given.
func (s Service) Ask(ctx context.Context, p AskParams) (gate.Gate, error) {
	if p.Feature == "" {
		return gate.Gate{}, fmt.Errorf("gatesvc: a gate needs a feature: the authz question and the audit chain are keyed by it")
	}
	now := s.now()
	g, err := gate.Open(s.Policy, gate.Request{
		ID: s.IDs.New(), Type: p.Type, RunID: p.RunID, StepID: p.StepID,
		Feature: p.Feature, Risk: p.Risk, Subject: p.Subject, Origin: p.Origin,
		WillWrite: p.WillWrite, Proof: p.Proof, Now: now, TTL: p.TTL,
	})
	if err != nil {
		return gate.Gate{}, fmt.Errorf("gatesvc: %w", err)
	}
	err = s.Store.InTx(ctx, func(tx ports.Tx) error {
		if err := tx.Gates().Open(ctx, g, p.Feature); err != nil {
			return fmt.Errorf("gatesvc: opening gate %s: %w", g.ID, err)
		}
		if len(p.SubjectPaths) > 0 {
			if p.SubjectRoot == "" {
				return fmt.Errorf("gatesvc: a file subject needs the directory the paths are relative to")
			}
			if err := tx.Gates().BindSubject(ctx, g.ID, p.SubjectRoot, p.SubjectPaths); err != nil {
				return fmt.Errorf("gatesvc: binding subject of %s: %w", g.ID, err)
			}
		}
		detail := map[string]any{
			"gate_type":          string(g.Type),
			"risk":               string(g.Risk),
			"subject_digest":     g.Subject.Digest,
			"required_assurance": string(g.RequiredAssurance),
			"will_write":         g.WillWrite,
			"expires_at":         g.ExpiresAt.Format(time.RFC3339),
		}
		if len(g.RequiredKeywords) > 0 {
			detail["required_keywords"] = g.RequiredKeywords
		}
		return appendAudit(ctx, tx, audit.Event{
			Action: audit.ActionGateRequested,
			Actor:  actorOf(p.Actor),
			RunID:  g.RunID, StepID: g.StepID, Feature: g.Feature,
			Subject: g.ID,
			Detail:  detail,
		}, s.Clock)
	})
	if err != nil {
		return gate.Gate{}, err
	}
	return g, nil
}

// DecisionParams is one answer on its way in.
type DecisionParams struct {
	GateID string
	// Quote is the person's words, verbatim. The decision is read from
	// them — 驳回 rejects, a parseable confirmation approves — so a caller
	// cannot submit an approval the person never wrote.
	Quote string
	// Channel is how the answer arrived; the assurance follows from it.
	Channel string
	// RecomputedDigest is the digest of the content as it is now,
	// supplied by the caller because the service never sees the content
	// itself. It is compared with what the person was shown (I-4).
	RecomputedDigest string
	Actor            ports.Principal
}

// Decision is an answered gate: the updated gate and the signed record.
type Decision struct {
	Gate     gate.Gate
	Approval ports.Approval
}

// Decide submits a person's answer. Everything happens in one transaction:
// the gate is loaded, the authz questions are asked, the domain applies
// the validity rules, the approval is signed and recorded, the gate is
// saved, and the audit events land with it.
//
// RecordApproval is the serialization point (threat T6): a second answer
// to the same gate fails there instead of overwriting the first, whatever
// order the two submissions arrived in.
//
// A refused submission — wrong identity, weak authentication, a quote that
// is not a confirmation, content that changed — writes nothing and returns
// *gate.Error. The caller shows the person why; the chain records what was
// actually decided, not every attempt at deciding it.
func (s Service) Decide(ctx context.Context, p DecisionParams) (Decision, error) {
	if p.GateID == "" {
		return Decision{}, fmt.Errorf("gatesvc: deciding needs a gate id")
	}
	if p.Quote == "" {
		return Decision{}, fmt.Errorf("gatesvc: deciding needs the person's words; an empty quote decides nothing")
	}
	assurance, ok := assuranceFromChannel(p.Channel)
	if !ok {
		return Decision{}, fmt.Errorf("gatesvc: unknown channel %q; assurance follows from how the answer arrived, so the channel must be one the service knows", p.Channel)
	}
	if p.RecomputedDigest == "" {
		return Decision{}, fmt.Errorf("gatesvc: deciding needs the digest of the content as it is now; without it an approval could bind to stale content (I-4)")
	}
	if s.Signer == nil {
		return Decision{}, fmt.Errorf("gatesvc: deciding needs a signer; a service that cannot sign cannot record an approval")
	}

	now := s.now()
	var out Decision
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		g, err := tx.Gates().Get(ctx, p.GateID)
		if err != nil {
			return fmt.Errorf("gatesvc: loading gate %s: %w", p.GateID, err)
		}

		// The words decide. 驳回 rejects; anything else must parse as a
		// confirmation, and a parse that fails is a quote-rejected
		// refusal, not a rejection.
		decision := gate.DecisionApprove
		var parsed signoff.Result
		if signoff.IsReject(p.Quote) {
			decision = gate.DecisionReject
		} else {
			parsed = signoff.ParseConfirm(p.Quote, signoffGateType(g.Type), gateOrigin(g))
		}

		approvalID := s.IDs.New()
		outcome, err := gate.Decide(g, s.Policy, gate.Submission{
			Decision: decision,
			Approver: gate.Approver{
				Handle:             p.Actor.Handle,
				Kind:               gate.PrincipalKind(p.Actor.Kind),
				HasApproverRole:    s.can(ctx, p.Actor, authzAction, authzAnyScope),
				ScopeCoversFeature: s.can(ctx, p.Actor, authzAction, g.Feature),
				Assurance:          assurance,
			},
			QuoteOK:          parsed.OK,
			QuoteKeywords:    parsed.Tokens,
			RecomputedDigest: p.RecomputedDigest,
			ApprovalID:       approvalID,
			Now:              now,
		})
		if err != nil {
			// A refusal. Nothing has been written; nothing will be.
			return err
		}

		a := ports.Approval{
			ID:            approvalID,
			GateID:        g.ID,
			GateType:      string(g.Type),
			Decision:      string(decision),
			SubjectDigest: canonical.Digest(g.Subject.Digest),
			Handle:        p.Actor.Handle,
			Kind:          p.Actor.Kind,
			Assurance:     string(assurance),
			Downgraded:    outcome.Downgraded,
			Quote:         p.Quote,
			Channel:       p.Channel,
			DecidedAt:     now,
		}
		if err := s.signApproval(ctx, &a); err != nil {
			return err
		}
		if err := tx.Gates().RecordApproval(ctx, a); err != nil {
			return fmt.Errorf("gatesvc: recording approval %s: %w", a.ID, err)
		}
		if err := tx.Gates().Save(ctx, outcome.Gate); err != nil {
			return fmt.Errorf("gatesvc: saving gate %s: %w", g.ID, err)
		}

		action := audit.ActionGateApproved
		if decision == gate.DecisionReject {
			action = audit.ActionGateRejected
		}
		if err := appendAudit(ctx, tx, audit.Event{
			Action: action,
			Actor:  actorOf(p.Actor),
			RunID:  g.RunID, StepID: g.StepID, Feature: g.Feature,
			Subject: a.ID,
			Detail: map[string]any{
				"gate_id":   g.ID,
				"gate_type": string(g.Type),
				"assurance": string(assurance),
			},
		}, s.Clock); err != nil {
			return err
		}
		if outcome.Downgraded {
			// The transition switch was used: a `high` requirement
			// completed at `low`. The chain must be able to find every
			// approval that rode the switch without joining to the
			// approvals table.
			if err := appendAudit(ctx, tx, audit.Event{
				Action: audit.ActionAssuranceDowngraded,
				Actor:  actorOf(p.Actor),
				RunID:  g.RunID, StepID: g.StepID, Feature: g.Feature,
				Subject: a.ID,
				Detail: map[string]any{
					"gate_id":     g.ID,
					"approval_id": a.ID,
					"required":    string(g.RequiredAssurance),
					"achieved":    string(assurance),
				},
			}, s.Clock); err != nil {
				return err
			}
		}
		out = Decision{Gate: outcome.Gate, Approval: a}
		return nil
	})
	if err != nil {
		return Decision{}, err
	}
	return out, nil
}

// Withdraw cancels a pending question — the conductor asked the wrong
// thing, or the work changed under it. It needs a note, because a question
// that vanishes without a reason is indistinguishable from one that was
// never asked; the note is the audit record's answer.
func (s Service) Withdraw(ctx context.Context, gateID, note string, actor ports.Principal) (gate.Gate, error) {
	var out gate.Gate
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		g, err := tx.Gates().Get(ctx, gateID)
		if err != nil {
			return fmt.Errorf("gatesvc: loading gate %s: %w", gateID, err)
		}
		out, err = gate.Withdraw(g, note)
		if err != nil {
			return err
		}
		if err := tx.Gates().Save(ctx, out); err != nil {
			return fmt.Errorf("gatesvc: withdrawing gate %s: %w", gateID, err)
		}
		return appendAudit(ctx, tx, audit.Event{
			Action: audit.ActionGateWithdrawn,
			Actor:  actorOf(actor),
			RunID:  out.RunID, StepID: out.StepID, Feature: out.Feature,
			Subject: out.ID,
			Detail:  map[string]any{"note": note},
		}, s.Clock)
	})
	if err != nil {
		return gate.Gate{}, err
	}
	return out, nil
}

// Expire marks a gate nobody answered. Nobody answering is not a refusal:
// the run falls back to ready and the question can be asked again. The
// caller is whoever sweeps stale gates — there is no batch sweep here,
// because the gate repo has no way to list pending ones.
func (s Service) Expire(ctx context.Context, gateID string) (gate.Gate, error) {
	now := s.now()
	var out gate.Gate
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		g, err := tx.Gates().Get(ctx, gateID)
		if err != nil {
			return fmt.Errorf("gatesvc: loading gate %s: %w", gateID, err)
		}
		out, err = gate.Expire(g, now)
		if err != nil {
			return err
		}
		if err := tx.Gates().Save(ctx, out); err != nil {
			return fmt.Errorf("gatesvc: expiring gate %s: %w", gateID, err)
		}
		return appendAudit(ctx, tx, audit.Event{
			Action: audit.ActionGateExpired,
			// The sweeper is not a person and not the conductor: it is
			// the system, and the record says so.
			Actor: audit.Actor{Handle: "sweeper", Kind: "system"},
			RunID: out.RunID, StepID: out.StepID, Feature: out.Feature,
			Subject: out.ID,
			Detail:  map[string]any{"expires_at": out.ExpiresAt.Format(time.RFC3339)},
		}, s.Clock)
	})
	if err != nil {
		return gate.Gate{}, err
	}
	return out, nil
}

// Get returns a gate by id.
func (s Service) Get(ctx context.Context, gateID string) (gate.Gate, error) {
	var g gate.Gate
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		var err error
		g, err = tx.Gates().Get(ctx, gateID)
		return err
	})
	return g, err
}

// Approval returns one recorded decision, signature included.
func (s Service) Approval(ctx context.Context, approvalID string) (ports.Approval, error) {
	var a ports.Approval
	err := s.Store.InTx(ctx, func(tx ports.Tx) error {
		var err error
		a, err = tx.Gates().Approval(ctx, approvalID)
		return err
	})
	return a, err
}

// --- signatures ---------------------------------------------------------

// signatureRecord is the signature object inside a stored approval: the
// algorithm, which key signed, and the signature as hex. ports.Approval
// carries it as one []byte so the adapters store exactly what the service
// produced, and the offline verifier — which reads the record's JSON —
// sees the same three fields.
type signatureRecord struct {
	Alg   string `json:"alg"`
	KeyID string `json:"key_id"`
	Value string `json:"value"`
}

// ApprovalPayload is the exact bytes an approval's signature covers: the
// JCS form of the record without the signature, in the shape of
// api/schemas/approval.schema.json. Optional fields are present only when
// they carry information — a false downgrade or an empty channel signs
// nothing, because signing a null is how a payload drifts from its record.
//
// Exported because the offline verifier must build the identical bytes; a
// private payload would mean two implementations that can only be kept in
// agreement by luck.
func ApprovalPayload(a ports.Approval) ([]byte, error) {
	m := map[string]any{
		"schema":         approvalSchema,
		"approval_id":    a.ID,
		"gate_id":        a.GateID,
		"gate_type":      a.GateType,
		"decision":       a.Decision,
		"subject_digest": string(a.SubjectDigest),
		"approver":       map[string]any{"handle": a.Handle, "kind": a.Kind},
		"assurance":      a.Assurance,
		"quote":          a.Quote,
		"decided_at":     a.DecidedAt.UTC().Format(time.RFC3339Nano),
	}
	if a.Downgraded {
		m["assurance_downgraded"] = true
	}
	if a.Channel != "" {
		m["channel"] = a.Channel
	}
	return canonical.JCS(m)
}

// signApproval signs the payload and stores the signature object on the
// record.
func (s Service) signApproval(ctx context.Context, a *ports.Approval) error {
	payload, err := ApprovalPayload(*a)
	if err != nil {
		return fmt.Errorf("gatesvc: canonicalising approval %s: %w", a.ID, err)
	}
	sig, keyID, err := s.Signer.Sign(ctx, payload)
	if err != nil {
		return fmt.Errorf("gatesvc: signing approval %s: %w", a.ID, err)
	}
	rec, err := json.Marshal(signatureRecord{Alg: "ed25519", KeyID: keyID, Value: hex.EncodeToString(sig)})
	if err != nil {
		return fmt.Errorf("gatesvc: encoding approval %s signature: %w", a.ID, err)
	}
	a.Signature = rec
	return nil
}

// VerifyApproval checks a stored approval against the signer: it rebuilds
// the payload from the record and verifies the signature with the key the
// record names. Server-side twin of the offline verifier — same payload,
// same key — which is the point: the two cannot disagree if there is only
// one payload builder.
func (s Service) VerifyApproval(ctx context.Context, a ports.Approval) error {
	var rec signatureRecord
	if err := json.Unmarshal(a.Signature, &rec); err != nil {
		return fmt.Errorf("gatesvc: approval %s carries no signature object: %w", a.ID, err)
	}
	if rec.Alg != "ed25519" {
		return fmt.Errorf("gatesvc: approval %s is signed with %q; ed25519 is the only algorithm this service records", a.ID, rec.Alg)
	}
	sig, err := hex.DecodeString(rec.Value)
	if err != nil {
		return fmt.Errorf("gatesvc: approval %s signature value is not hex: %w", a.ID, err)
	}
	payload, err := ApprovalPayload(a)
	if err != nil {
		return err
	}
	if err := s.Signer.Verify(ctx, payload, sig, rec.KeyID); err != nil {
		return fmt.Errorf("gatesvc: approval %s fails verification: %w", a.ID, err)
	}
	return nil
}

// --- helpers ------------------------------------------------------------

// assuranceFromChannel maps an arrival channel to the assurance it proves.
// The mapping is closed: a channel the service does not know is a caller
// bug, and guessing its strength would be deciding the answer's weight
// from a string nobody has defined.
func assuranceFromChannel(channel string) (gate.Assurance, bool) {
	switch channel {
	case ChannelLocalTokenTTY, ChannelOIDC:
		return gate.AssuranceLow, true
	case ChannelWebAuthn, ChannelOIDCWebAuthn:
		return gate.AssuranceHigh, true
	}
	return "", false
}

// signoffGateType narrows a gate type to the two signoff knows keyword
// requirements for. Every other gate type asks for a plain confirmation.
func signoffGateType(t gate.Type) signoff.GateType {
	switch t {
	case gate.TypeDefectOrigin:
		return signoff.GateDefectOrigin
	case gate.TypeReopenBaseline:
		return signoff.GateReopenBaseline
	}
	return ""
}

// gateOrigin recovers the origin a defect_origin gate is asking about. The
// gate record does not keep Origin as its own field — it is folded into
// RequiredKeywords — so this reads it back out. The keyword check in the
// domain is the enforcement; this is only so the parse expects the right
// keyword.
func gateOrigin(g gate.Gate) string {
	for _, kw := range g.RequiredKeywords {
		if strings.HasPrefix(kw, "origin=") {
			return strings.TrimPrefix(kw, "origin=")
		}
	}
	return ""
}

func (s Service) now() time.Time {
	if s.Clock == nil {
		return time.Now()
	}
	return s.Clock.Now()
}

// can asks the authorizer one question. A service with no authorizer
// wired answers no to everything: opening gates stays possible, but no
// decision can pass, which fails closed rather than open.
func (s Service) can(ctx context.Context, p ports.Principal, action, scope string) bool {
	if s.Authorizer == nil {
		return false
	}
	return s.Authorizer.Can(ctx, p, action, scope)
}

// The two helpers below are the runsvc ones, copied: they are package
// private there, and the alternative — exporting them so the app services
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
