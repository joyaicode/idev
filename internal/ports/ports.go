// Package ports declares what the application layer needs from the outside
// world, as interfaces it owns.
//
// Dependencies point inwards: app depends on these, adapters implement them,
// and cmd decides which adapter is wired in. That is not architecture for
// its own sake — it is what makes a use case testable without a database,
// and what let the same app layer run against SQLite locally and PostgreSQL
// remotely in P4 without the services knowing which.
//
// The interfaces are narrow on purpose. A Store that exposes "run SQL" would
// satisfy every caller and constrain nothing; these expose the operations
// the use cases actually perform, so a reader can see the whole data
// boundary by reading this file.
package ports

import (
	"context"
	"time"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/baseline"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/pkg/canonical"
)

// Tx is one transaction. A use case is a transaction: the state change and
// its audit event are written together or not at all (invariant I-6).
type Tx interface {
	Runs() RunRepo
	Leases() LeaseRepo
	Delegations() DelegationRepo
	Gates() GateRepo
	Baselines() BaselineRepo
	Audit() AuditRepo
	Idempotency() IdempotencyRepo
}

// Store opens transactions.
type Store interface {
	// InTx runs fn in one transaction, committing when it returns nil.
	InTx(ctx context.Context, fn func(Tx) error) error
	Close() error
}

// ConflictError is how an adapter reports a constraint the caller can act
// on. The app layer branches on Kind rather than on driver strings.
type ConflictError struct {
	Kind   string
	Detail string
}

func (e *ConflictError) Error() string {
	if e.Detail == "" {
		return "conflict: " + e.Kind
	}
	return "conflict: " + e.Kind + ": " + e.Detail
}

// The conflict kinds the app layer distinguishes.
const (
	ConflictLiveRun        = "live_run"
	ConflictLeaseHeld      = "lease_held"
	ConflictAttemptExists  = "attempt_exists"
	ConflictGatePending    = "gate_pending"
	ConflictApprovalExists = "approval_exists"
	ConflictSealedBaseline = "sealed_baseline"
	ConflictVerification   = "verification_exists"
	ConflictIdempotency    = "idempotency_key_reuse"
	ConflictStaleVersion   = "stale_version"
	ConflictNotFound       = "not_found"
)

// RunRepo stores runs and their steps.
type RunRepo interface {
	Create(ctx context.Context, r run.Run, featureID string) error
	Get(ctx context.Context, runID string) (run.Run, int64, error)
	// FindLive returns the live run for a feature and workflow, if any.
	FindLive(ctx context.Context, featureID, workflowID string) (run.Run, int64, error)
	// Save writes a run back, failing with ConflictStaleVersion unless the
	// stored version still equals `version`. Optimistic concurrency is what
	// stops two conductors applying decisions to the same run.
	Save(ctx context.Context, r run.Run, version int64) error
}

// LeaseRepo issues and retires leases.
type LeaseRepo interface {
	// Issue fails with ConflictLeaseHeld when a write lease already exists
	// for the feature. The database decides, not the caller.
	Issue(ctx context.Context, l lease.Lease, tokenHash string) error
	Get(ctx context.Context, leaseID string) (lease.Lease, error)
	// ActiveFor returns the live lease on a step, if any.
	ActiveFor(ctx context.Context, runID, stepID string) (lease.Lease, error)
	// Release retires a lease. It is idempotent at the service layer: the
	// services release leases they did not issue, so it is never an error
	// for the lease to already be gone.
	Release(ctx context.Context, leaseID string) error
	// TokenHash returns the hash of the lease's bearer token, so a service
	// can prove a caller holds it before retiring the lease.
	TokenHash(ctx context.Context, leaseID string) (string, error)
	// Extend pushes a live lease's deadline to `until`, proving ownership
	// with the token hash. A mismatched token, a lease that is no longer
	// active, or one that already ran out fails with ConflictLeaseHeld: a
	// late renewal must not resurrect a lease, the holder has to acquire a
	// fresh one. The fencing token and holder are immutable, so both stay
	// as they are.
	Extend(ctx context.Context, leaseID, tokenHash string, now, until time.Time) (lease.Lease, error)
	// NextFencing returns the next monotonic token for a feature.
	NextFencing(ctx context.Context, featureID string) (uint64, error)
	// Expire marks leases past their deadline and returns them, for the
	// sweeper.
	Expire(ctx context.Context, now time.Time, limit int) ([]lease.Lease, error)
}

// Delegation is one handoff to an agent, as stored.
type Delegation struct {
	ID       string
	RunID    string
	StepID   string
	Attempt  int
	Agent    string
	LeaseID  string
	Packet   []byte
	Return   []byte
	Checks   map[string]string
	State    string
	Outcome  string
	Via      string
	IssuedAt time.Time
}

// DelegationRepo stores delegation records.
type DelegationRepo interface {
	// Insert fails with ConflictAttemptExists when (run, step, attempt) is
	// taken. Invariant I-5: a record is never replaced.
	Insert(ctx context.Context, d Delegation) error
	Get(ctx context.Context, id string) (Delegation, error)
	// Latest returns the most recent attempt for a step, if any.
	Latest(ctx context.Context, runID, stepID string) (Delegation, error)
	Update(ctx context.Context, d Delegation) error
	// RecordVerification fails with ConflictVerification if one exists.
	RecordVerification(ctx context.Context, delegationID, verifier, verdict string, evidence []string, at time.Time) error
}

// GateRepo stores gates and approvals.
type GateRepo interface {
	Open(ctx context.Context, g gate.Gate, featureID string) error
	Get(ctx context.Context, gateID string) (gate.Gate, error)
	Save(ctx context.Context, g gate.Gate) error
	// BindSubject records the files the gate's digest covers. It belongs
	// in the same transaction as Open: a digest of files with no record
	// of which files cannot be checked later (I-4).
	BindSubject(ctx context.Context, gateID, root string, paths []string) error
	// RecordApproval fails with ConflictApprovalExists on a second
	// approval for the same gate (threat T6, replay).
	RecordApproval(ctx context.Context, a Approval) error
	Approval(ctx context.Context, approvalID string) (Approval, error)
}

// Approval is a stored human decision.
type Approval struct {
	ID            string
	GateID        string
	GateType      string
	Decision      string
	SubjectDigest canonical.Digest
	Handle        string
	Kind          string
	Assurance     string
	Downgraded    bool
	Quote         string
	Channel       string
	Signature     []byte
	DecidedAt     time.Time
}

// BaselineRepo stores baseline manifests.
type BaselineRepo interface {
	Put(ctx context.Context, featureID string, m baseline.Manifest, status string) (string, error)
	Sealed(ctx context.Context, featureID string) (baseline.Manifest, error)
	Get(ctx context.Context, baselineID string) (baseline.Manifest, error)
	// Seal promotes a draft, failing with ConflictSealedBaseline if one is
	// already sealed.
	Seal(ctx context.Context, baselineID string, at time.Time) error
	Reopen(ctx context.Context, featureID string) error
}

// AuditRepo appends to the chain and stores the checkpoints that make a
// long chain worth verifying.
type AuditRepo interface {
	// Append seals the event against the current head and stores it. The
	// repo owns the sequence number and the head, so two concurrent writers
	// cannot produce two events claiming the same predecessor.
	Append(ctx context.Context, e audit.Event) (audit.Event, error)
	Head(ctx context.Context) (canonical.Digest, int64, error)
	Range(ctx context.Context, fromSeq int64, limit int) ([]audit.Event, error)
	// SaveCheckpoint records a signed position. The chain stays the truth;
	// the checkpoint is only a promise about it from the signer's key.
	SaveCheckpoint(ctx context.Context, cp audit.Checkpoint) error
	// Checkpoint returns the latest signed position, or ConflictNotFound
	// when nobody has signed yet.
	Checkpoint(ctx context.Context) (audit.Checkpoint, error)
}

// IdempotencyRepo makes a retried request safe.
type IdempotencyRepo interface {
	// Claim records the key, returning the stored result when it was
	// already used. A retry after a network failure must not start a second
	// run.
	Claim(ctx context.Context, key, scope string) (result []byte, replayed bool, err error)
	Complete(ctx context.Context, key string, result []byte) error
}

// Workspace is the filesystem side: hashing files, reading git, locating
// tickets. Remote deployments satisfy it over the idev-local MCP server
// rather than locally, which is why it is a port rather than a package.
type Workspace interface {
	// Manifest computes a baseline manifest without storing it.
	Manifest(ctx context.Context, repoRoot, feature string, revision int) (baseline.Manifest, error)
	// ChangedSince returns paths changed since a ref, for the lease-paths
	// check. An agent's own CHANGED list is a claim; this is the evidence.
	ChangedSince(ctx context.Context, repoRoot, baseRef string) ([]string, error)
	// LocateTicket resolves a ticket directory. Side-effect free: it never
	// creates one, because a probe that creates directories turns a
	// question into a change.
	LocateTicket(ctx context.Context, repoRoot, feature, key string) (string, error)
	// Head returns the current commit and whether the tree is dirty.
	Head(ctx context.Context, repoRoot string) (commit string, dirty bool, err error)
}

// Signer signs approvals and audit checkpoints.
type Signer interface {
	Sign(ctx context.Context, payload []byte) (signature []byte, keyID string, err error)
	Verify(ctx context.Context, payload, signature []byte, keyID string) error
	KeyID(ctx context.Context) (string, error)
}

// Clock is injectable so tests are deterministic.
type Clock interface{ Now() time.Time }

// IDGen produces ULIDs.
type IDGen interface{ New() string }

// Principal is an authenticated caller.
type Principal struct {
	ID     string
	Handle string
	// Kind is human, agent or service. The gate domain refuses anything but
	// human, and this is where that value comes from.
	Kind string
	// OwnerHandle is the person an agent acts for.
	OwnerHandle string
	Scopes      []string
}

// Authorizer answers whether a principal may do something.
type Authorizer interface {
	Can(ctx context.Context, p Principal, action, scope string) bool
}

// KindRegistry answers what a kind or an agent requires.
//
// The registry itself is a YAML file, so reading it is an adapter's job
// (internal/adapters/kindreg). The app layer only needs these questions
// answered, and declaring them here is what keeps the dependency pointing
// inwards.
type KindRegistry interface {
	// AgentFor returns the agent a kind delegates to, or "-" when the
	// conductor keeps it.
	AgentFor(kind string) string
	// IsFacts reports whether an agent must declare where its facts came
	// from.
	IsFacts(agent string) bool
	// IsBoost reports whether an agent reads convention pages from the
	// kernel, and so needs idev_root in its brief.
	IsBoost(agent string) bool
	// S0Agent is the agent coding.md §0 applies to.
	S0Agent() string
	// Forbidden reports whether a kind is one of the refused shapes.
	Forbidden(kind string) bool
	// NeedsIndependentVerification reports whether a kind's PASS requires a
	// second agent, and who.
	NeedsIndependentVerification(kind string) (string, bool)
	// LeaseFor returns the lease purpose a kind needs.
	LeaseFor(kind string) string
	// IsGate reports whether a kind is the human gate.
	IsGate(kind string) bool
}
