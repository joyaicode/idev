package sqlite

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/baseline"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/canonical"
)

// InTx makes the Store a ports.Store.
//
// Gates, leases, audit and idempotency are backed by SQL. Runs are read-only
// projections of the Python driver's run.yaml (ProjectRun writes them), so
// creating or saving one through the port refuses; delegations and
// baselines are not wired at all. A service that reaches one of those is a
// service this binary does not run yet.
func (s *Store) InTx(ctx context.Context, fn func(ports.Tx) error) error {
	return s.Tx(ctx, func(tx *sql.Tx) error { return fn(txRepos{tx: tx}) })
}

var errNotWired = errors.New("sqlite: not wired in this build; runs, leases, delegations and baselines still live in the Python driver's files")

type txRepos struct{ tx *sql.Tx }

func (t txRepos) Runs() ports.RunRepo                { return runRepo{t.tx} }
func (t txRepos) Leases() ports.LeaseRepo            { return leaseRepo{t.tx} }
func (t txRepos) Delegations() ports.DelegationRepo  { return unwiredDelegations{} }
func (t txRepos) Baselines() ports.BaselineRepo      { return unwiredBaselines{} }
func (t txRepos) Gates() ports.GateRepo              { return gateRepo{t.tx} }
func (t txRepos) Audit() ports.AuditRepo             { return auditRepo{t.tx} }
func (t txRepos) Idempotency() ports.IdempotencyRepo { return idempRepo{t.tx} }

// stampLayout is fixed-width so stored times order as strings: RFC3339Nano
// drops trailing zeros, and "…05Z" sorts after "…05.5Z".
const stampLayout = "2006-01-02T15:04:05.000000000Z"

func stamp(t time.Time) string { return t.UTC().Format(stampLayout) }

func parseStamp(s string) (time.Time, error) { return time.Parse(time.RFC3339Nano, s) }

func conflictFrom(err error, detail string) error {
	switch Classify(err) {
	case ConflictNone, ConflictOther:
		return err
	case ConflictGatePending:
		return &ports.ConflictError{Kind: ports.ConflictGatePending, Detail: detail}
	case ConflictApprovalExists:
		return &ports.ConflictError{Kind: ports.ConflictApprovalExists, Detail: detail}
	case ConflictIdempotencyKey:
		return &ports.ConflictError{Kind: ports.ConflictIdempotency, Detail: detail}
	default:
		return err
	}
}

func notFound(detail string) error {
	return &ports.ConflictError{Kind: ports.ConflictNotFound, Detail: detail}
}

// --- gates -----------------------------------------------------------------

type gateRepo struct{ tx *sql.Tx }

// Open stores a pending gate.
//
// The features and runs rows a gate references are projections: the Python
// driver owns both, and a gate only needs them to exist for the foreign keys.
// A projected run is `external`, outside the live set, so it never competes
// with the one-live-run index.
func (g gateRepo) Open(ctx context.Context, gt gate.Gate, featureID string) error {
	now := stamp(gt.CreatedAt)
	if _, err := g.tx.ExecContext(ctx, `INSERT OR IGNORE INTO features
		(id, workspace, feature_key, stage, risk_tier, created_at, updated_at)
		VALUES (?, 'local', ?, 'external', ?, ?, ?)`,
		featureID, featureID, string(gt.Risk), now, now); err != nil {
		return fmt.Errorf("sqlite: projecting feature %s: %w", featureID, err)
	}
	var runID any
	if gt.RunID != "" {
		runID = gt.RunID
		if _, err := g.tx.ExecContext(ctx, `INSERT OR IGNORE INTO runs
			(id, workflow_id, feature_id, status, started_at, created_at)
			VALUES (?, 'external', ?, 'external', ?, ?)`,
			gt.RunID, featureID, now, now); err != nil {
			return fmt.Errorf("sqlite: projecting run %s: %w", gt.RunID, err)
		}
	}
	willWrite, err := json.Marshal(nonNil(gt.WillWrite))
	if err != nil {
		return err
	}
	keywords, err := json.Marshal(nonNil(gt.RequiredKeywords))
	if err != nil {
		return err
	}
	var revision any
	if gt.Subject.BaselineRevision > 0 {
		revision = gt.Subject.BaselineRevision
	}
	_, err = g.tx.ExecContext(ctx, `INSERT INTO gates
		(id, gate_type, run_id, step_id, feature_id, risk_tier, subject_kind,
		 subject_digest, baseline_revision, will_write_json, proof,
		 required_assurance, required_keywords_json, status, created_at, expires_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		gt.ID, string(gt.Type), runID, nullable(gt.StepID), featureID, string(gt.Risk),
		string(gt.Subject.Kind), gt.Subject.Digest, revision, string(willWrite),
		nullable(gt.Proof), string(gt.RequiredAssurance), string(keywords),
		string(gt.Status), now, stamp(gt.ExpiresAt))
	if err != nil {
		// The id of the question already open lets a retry write that id
		// back into the run instead of getting stuck with no handle on it.
		if Classify(err) == ConflictGatePending {
			if id := g.pendingID(ctx, gt.RunID, gt.StepID); id != "" {
				return conflictFrom(err, id+" already pending for "+gt.StepID)
			}
		}
		return conflictFrom(err, gt.StepID+" already has a pending gate")
	}
	return nil
}

func (g gateRepo) pendingID(ctx context.Context, runID, stepID string) string {
	if runID == "" || stepID == "" {
		return ""
	}
	var id string
	err := g.tx.QueryRowContext(ctx, `SELECT id FROM gates
		WHERE run_id = ? AND step_id = ? AND status = 'pending'`, runID, stepID).Scan(&id)
	if err != nil {
		return ""
	}
	return id
}

// BindSubject records the files a gate's digest covers, on the same
// transaction as Open.
func (g gateRepo) BindSubject(ctx context.Context, gateID, root string, paths []string) error {
	b, err := json.Marshal(nonNil(paths))
	if err != nil {
		return err
	}
	_, err = g.tx.ExecContext(ctx,
		`INSERT INTO gate_subjects (gate_id, root, paths_json) VALUES (?, ?, ?)`,
		gateID, root, string(b))
	return err
}

func (g gateRepo) Get(ctx context.Context, id string) (gate.Gate, error) {
	var (
		gt                          gate.Gate
		gType, risk, kind, status   string
		runID, stepID, proof        sql.NullString
		revision                    sql.NullInt64
		willWrite, keywords         string
		assurance, created, expires string
	)
	err := g.tx.QueryRowContext(ctx, `SELECT id, gate_type, run_id, step_id, feature_id,
		risk_tier, subject_kind, subject_digest, baseline_revision, will_write_json,
		proof, required_assurance, required_keywords_json, status, created_at, expires_at
		FROM gates WHERE id = ?`, id).Scan(
		&gt.ID, &gType, &runID, &stepID, &gt.Feature, &risk, &kind, &gt.Subject.Digest,
		&revision, &willWrite, &proof, &assurance, &keywords, &status, &created, &expires)
	if errors.Is(err, sql.ErrNoRows) {
		return gate.Gate{}, notFound("gate " + id)
	}
	if err != nil {
		return gate.Gate{}, err
	}
	gt.Type, gt.Risk, gt.Subject.Kind = gate.Type(gType), gate.RiskTier(risk), gate.SubjectKind(kind)
	gt.Status, gt.RequiredAssurance = gate.Status(status), gate.Assurance(assurance)
	gt.RunID, gt.StepID, gt.Proof = runID.String, stepID.String, proof.String
	gt.Subject.BaselineRevision = int(revision.Int64)
	if err := json.Unmarshal([]byte(willWrite), &gt.WillWrite); err != nil {
		return gate.Gate{}, err
	}
	if err := json.Unmarshal([]byte(keywords), &gt.RequiredKeywords); err != nil {
		return gate.Gate{}, err
	}
	if gt.CreatedAt, err = parseStamp(created); err != nil {
		return gate.Gate{}, err
	}
	if gt.ExpiresAt, err = parseStamp(expires); err != nil {
		return gate.Gate{}, err
	}
	return gt, nil
}

// Save writes back the only fields a decision changes. Everything the person
// was shown is fixed at Open.
func (g gateRepo) Save(ctx context.Context, gt gate.Gate) error {
	res, err := g.tx.ExecContext(ctx, `UPDATE gates SET status = ? WHERE id = ?`,
		string(gt.Status), gt.ID)
	if err != nil {
		return conflictFrom(err, "gate "+gt.ID)
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return notFound("gate " + gt.ID)
	}
	return nil
}

func (g gateRepo) RecordApproval(ctx context.Context, a ports.Approval) error {
	downgraded := 0
	if a.Downgraded {
		downgraded = 1
	}
	_, err := g.tx.ExecContext(ctx, `INSERT INTO approvals
		(id, gate_id, gate_type, decision, subject_digest, approver_handle,
		 approver_kind, assurance, downgraded, quote, channel, signature_json, decided_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		a.ID, a.GateID, a.GateType, a.Decision, string(a.SubjectDigest), a.Handle,
		a.Kind, a.Assurance, downgraded, a.Quote, nullable(a.Channel),
		string(a.Signature), stamp(a.DecidedAt))
	if err != nil {
		return conflictFrom(err, "gate "+a.GateID+" is already decided")
	}
	return nil
}

func (g gateRepo) Approval(ctx context.Context, id string) (ports.Approval, error) {
	return g.scanApproval(ctx, `WHERE id = ?`, id)
}

// ApprovalForGate is not on the port: the CLI's status command needs it, the
// services do not.
func (s *Store) ApprovalForGate(ctx context.Context, gateID string) (ports.Approval, error) {
	var a ports.Approval
	err := s.Tx(ctx, func(tx *sql.Tx) error {
		var err error
		a, err = gateRepo{tx}.scanApproval(ctx, `WHERE gate_id = ?`, gateID)
		return err
	})
	return a, err
}

// PutGateSubject records the files a gate's digest covers.
func (s *Store) PutGateSubject(ctx context.Context, gateID, root string, paths []string) error {
	b, err := json.Marshal(nonNil(paths))
	if err != nil {
		return err
	}
	return s.Tx(ctx, func(tx *sql.Tx) error {
		_, err := tx.ExecContext(ctx,
			`INSERT INTO gate_subjects (gate_id, root, paths_json) VALUES (?, ?, ?)`,
			gateID, root, string(b))
		return err
	})
}

// GateSubject returns the files a gate's digest covers; no row means the
// gate binds to the question itself (a run_step subject).
func (s *Store) GateSubject(ctx context.Context, gateID string) (root string, paths []string, err error) {
	err = s.Tx(ctx, func(tx *sql.Tx) error {
		var raw string
		err := tx.QueryRowContext(ctx,
			`SELECT root, paths_json FROM gate_subjects WHERE gate_id = ?`, gateID).Scan(&root, &raw)
		if errors.Is(err, sql.ErrNoRows) {
			return nil
		}
		if err != nil {
			return err
		}
		return json.Unmarshal([]byte(raw), &paths)
	})
	return root, paths, err
}

func (g gateRepo) scanApproval(ctx context.Context, where, arg string) (ports.Approval, error) {
	var (
		a                    ports.Approval
		digest, sig, decided string
		channel              sql.NullString
		downgraded           int
	)
	err := g.tx.QueryRowContext(ctx, `SELECT id, gate_id, gate_type, decision, subject_digest,
		approver_handle, approver_kind, assurance, downgraded, quote, channel,
		signature_json, decided_at FROM approvals `+where, arg).Scan(
		&a.ID, &a.GateID, &a.GateType, &a.Decision, &digest, &a.Handle, &a.Kind,
		&a.Assurance, &downgraded, &a.Quote, &channel, &sig, &decided)
	if errors.Is(err, sql.ErrNoRows) {
		return ports.Approval{}, notFound("approval for " + arg)
	}
	if err != nil {
		return ports.Approval{}, err
	}
	a.SubjectDigest, a.Signature, a.Channel = canonical.Digest(digest), []byte(sig), channel.String
	a.Downgraded = downgraded == 1
	if a.DecidedAt, err = parseStamp(decided); err != nil {
		return ports.Approval{}, err
	}
	return a, nil
}

// --- audit -----------------------------------------------------------------

type auditRepo struct{ tx *sql.Tx }

// Append seals against the stored head inside the caller's transaction.
// `_txlock=immediate` means the head cannot move between the read and the
// insert.
func (a auditRepo) Append(ctx context.Context, e audit.Event) (audit.Event, error) {
	prev, seq, err := a.Head(ctx)
	if err != nil {
		return audit.Event{}, err
	}
	e.Seq = seq + 1
	sealed, err := audit.Seal(e, prev)
	if err != nil {
		return audit.Event{}, err
	}
	var detail any
	if len(sealed.Detail) > 0 {
		b, err := canonical.JCS(sealed.Detail)
		if err != nil {
			return audit.Event{}, err
		}
		detail = string(b)
	}
	_, err = a.tx.ExecContext(ctx, `INSERT INTO audit_events
		(seq, at, action, actor_handle, actor_kind, on_behalf_of, via, run_id,
		 step_id, feature, subject, detail_json, prev_hash, hash)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		sealed.Seq, stamp(sealed.At), string(sealed.Action), sealed.Actor.Handle,
		sealed.Actor.Kind, nullable(sealed.Actor.OnBehalfOf), nullable(sealed.Actor.Via),
		nullable(sealed.RunID), nullable(sealed.StepID), nullable(sealed.Feature),
		nullable(sealed.Subject), detail, string(sealed.PrevHash), string(sealed.Hash))
	if err != nil {
		return audit.Event{}, fmt.Errorf("sqlite: appending audit event: %w", err)
	}
	return sealed, nil
}

func (a auditRepo) Head(ctx context.Context) (canonical.Digest, int64, error) {
	var (
		hash string
		seq  int64
	)
	err := a.tx.QueryRowContext(ctx,
		`SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1`).Scan(&seq, &hash)
	if errors.Is(err, sql.ErrNoRows) {
		return audit.Genesis, 0, nil
	}
	if err != nil {
		return "", 0, err
	}
	return canonical.Digest(hash), seq, nil
}

func (a auditRepo) Range(ctx context.Context, fromSeq int64, limit int) ([]audit.Event, error) {
	if limit <= 0 {
		limit = -1
	}
	rows, err := a.tx.QueryContext(ctx, `SELECT seq, at, action, actor_handle, actor_kind,
		on_behalf_of, via, run_id, step_id, feature, subject, detail_json, prev_hash, hash
		FROM audit_events WHERE seq >= ? ORDER BY seq LIMIT ?`, fromSeq, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []audit.Event
	for rows.Next() {
		var (
			e                                                audit.Event
			at, action, prev, hash                           string
			onBehalf, via, runID, stepID, feature, subj, det sql.NullString
		)
		if err := rows.Scan(&e.Seq, &at, &action, &e.Actor.Handle, &e.Actor.Kind, &onBehalf,
			&via, &runID, &stepID, &feature, &subj, &det, &prev, &hash); err != nil {
			return nil, err
		}
		if e.At, err = parseStamp(at); err != nil {
			return nil, err
		}
		e.Action, e.PrevHash, e.Hash = audit.Action(action), canonical.Digest(prev), canonical.Digest(hash)
		e.Actor.OnBehalfOf, e.Actor.Via = onBehalf.String, via.String
		e.RunID, e.StepID, e.Feature, e.Subject = runID.String, stepID.String, feature.String, subj.String
		if det.Valid {
			if err := json.Unmarshal([]byte(det.String), &e.Detail); err != nil {
				return nil, err
			}
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

func (a auditRepo) SaveCheckpoint(ctx context.Context, cp audit.Checkpoint) error {
	_, err := a.tx.ExecContext(ctx, `INSERT INTO audit_checkpoints (seq, hash, at, key_id, signature)
		VALUES (?, ?, ?, ?, ?)`, cp.Seq, string(cp.Hash), stamp(cp.At), cp.KeyID, cp.Signature)
	return err
}

func (a auditRepo) Checkpoint(ctx context.Context) (audit.Checkpoint, error) {
	var (
		cp       audit.Checkpoint
		hash, at string
	)
	err := a.tx.QueryRowContext(ctx, `SELECT seq, hash, at, key_id, signature
		FROM audit_checkpoints ORDER BY seq DESC LIMIT 1`).Scan(&cp.Seq, &hash, &at, &cp.KeyID, &cp.Signature)
	if errors.Is(err, sql.ErrNoRows) {
		return audit.Checkpoint{}, notFound("no checkpoint yet")
	}
	if err != nil {
		return audit.Checkpoint{}, err
	}
	cp.Hash = canonical.Digest(hash)
	if cp.At, err = parseStamp(at); err != nil {
		return audit.Checkpoint{}, err
	}
	return cp, nil
}

// --- idempotency -----------------------------------------------------------

type idempRepo struct{ tx *sql.Tx }

func (i idempRepo) Claim(ctx context.Context, key, scope string) ([]byte, bool, error) {
	if key == "" {
		return nil, false, nil
	}
	var result sql.NullString
	err := i.tx.QueryRowContext(ctx, `SELECT result_json FROM idempotency_keys WHERE key = ?`, key).Scan(&result)
	if err == nil {
		return []byte(result.String), true, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return nil, false, err
	}
	_, err = i.tx.ExecContext(ctx, `INSERT INTO idempotency_keys (key, scope, created_at) VALUES (?, ?, ?)`,
		key, scope, stamp(time.Now()))
	return nil, false, conflictFrom(err, key)
}

func (i idempRepo) Complete(ctx context.Context, key string, result []byte) error {
	if key == "" {
		return nil
	}
	_, err := i.tx.ExecContext(ctx, `UPDATE idempotency_keys SET result_json = ? WHERE key = ?`, string(result), key)
	return err
}

// --- runs (projections) --------------------------------------------------------

// ProjectedStep is one step of a run.yaml as the lease checks need it.
type ProjectedStep struct {
	ID     string
	Kind   string
	State  run.StepState
	Writer string
}

// ProjectedRun is a run.yaml reduced to what the Go services read.
type ProjectedRun struct {
	ID         string
	WorkflowID string
	Feature    string
	Risk       string
	Steps      []ProjectedStep
}

// ProjectRun writes the Python driver's view of a run, replacing each step's
// state. run.yaml stays the source of truth; this is the copy the lease
// service checks a delegation against.
func (s *Store) ProjectRun(ctx context.Context, r ProjectedRun) error {
	if r.ID == "" || r.Feature == "" {
		return fmt.Errorf("sqlite: a projected run needs an id and a feature")
	}
	now := stamp(time.Now())
	return s.Tx(ctx, func(tx *sql.Tx) error {
		if _, err := tx.ExecContext(ctx, `INSERT OR IGNORE INTO features
			(id, workspace, feature_key, stage, risk_tier, created_at, updated_at)
			VALUES (?, 'local', ?, 'external', ?, ?, ?)`, r.Feature, r.Feature, r.Risk, now, now); err != nil {
			return fmt.Errorf("sqlite: projecting feature %s: %w", r.Feature, err)
		}
		if _, err := tx.ExecContext(ctx, `INSERT INTO runs
			(id, workflow_id, feature_id, status, started_at, created_at)
			VALUES (?, ?, ?, 'external', ?, ?)
			ON CONFLICT(id) DO UPDATE SET workflow_id = excluded.workflow_id
			WHERE runs.status = 'external'`, r.ID, r.WorkflowID, r.Feature, now, now); err != nil {
			return fmt.Errorf("sqlite: projecting run %s: %w", r.ID, err)
		}
		for i, st := range r.Steps {
			if _, err := tx.ExecContext(ctx, `INSERT INTO steps
				(run_id, step_id, ordinal, kind, state, writer)
				VALUES (?, ?, ?, ?, ?, ?)
				ON CONFLICT(run_id, step_id) DO UPDATE SET
				  kind = excluded.kind, state = excluded.state, writer = excluded.writer`,
				r.ID, st.ID, i, st.Kind, string(st.State), nullable(st.Writer)); err != nil {
				return fmt.Errorf("sqlite: projecting step %s: %w", st.ID, err)
			}
		}
		return nil
	})
}

type runRepo struct{ tx *sql.Tx }

func (runRepo) Create(context.Context, run.Run, string) error { return errNotWired }
func (runRepo) FindLive(context.Context, string, string) (run.Run, int64, error) {
	return run.Run{}, 0, errNotWired
}
func (runRepo) Save(context.Context, run.Run, int64) error { return errNotWired }

func (r runRepo) Get(ctx context.Context, runID string) (run.Run, int64, error) {
	var (
		out     run.Run
		version int64
	)
	err := r.tx.QueryRowContext(ctx, `SELECT id, workflow_id, feature_id, version FROM runs WHERE id = ?`,
		runID).Scan(&out.ID, &out.WorkflowID, &out.Feature, &version)
	if errors.Is(err, sql.ErrNoRows) {
		return run.Run{}, 0, notFound("run " + runID)
	}
	if err != nil {
		return run.Run{}, 0, err
	}
	rows, err := r.tx.QueryContext(ctx, `SELECT step_id, kind, state, writer FROM steps
		WHERE run_id = ? ORDER BY ordinal`, runID)
	if err != nil {
		return run.Run{}, 0, err
	}
	defer rows.Close()
	for rows.Next() {
		var (
			st     run.Step
			state  string
			writer sql.NullString
		)
		if err := rows.Scan(&st.ID, &st.Kind, &state, &writer); err != nil {
			return run.Run{}, 0, err
		}
		st.State, st.Writer, st.IsGate = run.StepState(state), writer.String, st.Kind == "human.gate"
		out.Steps = append(out.Steps, st)
	}
	return out, version, rows.Err()
}

// --- leases --------------------------------------------------------------------

type leaseRepo struct{ tx *sql.Tx }

const leaseColumns = `id, purpose, feature_id, run_id, step_id, agent, fencing_token, write_paths_json, expires_at`

func (l leaseRepo) Issue(ctx context.Context, ls lease.Lease, tokenHash string) error {
	paths, err := json.Marshal(nonNil(ls.WritePaths))
	if err != nil {
		return err
	}
	_, err = l.tx.ExecContext(ctx, `INSERT INTO leases
		(id, purpose, feature_id, run_id, step_id, agent, token_sha256, fencing_token,
		 write_paths_json, status, issued_at, expires_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)`,
		ls.ID, string(ls.Purpose), nullable(ls.Feature), ls.RunID, ls.StepID, ls.Agent, tokenHash,
		int64(ls.Fencing), string(paths), stamp(time.Now()), stamp(ls.ExpiresAt))
	if err != nil {
		if c := Classify(err); c == ConflictWriteLeaseHeld {
			return &ports.ConflictError{Kind: ports.ConflictLeaseHeld,
				Detail: "another agent holds the write lease on " + ls.Feature}
		}
		return err
	}
	return nil
}

func (l leaseRepo) scan(row interface{ Scan(...any) error }) (lease.Lease, error) {
	var (
		ls             lease.Lease
		purpose, paths string
		expires        string
		feature        sql.NullString
		fencing        int64
	)
	if err := row.Scan(&ls.ID, &purpose, &feature, &ls.RunID, &ls.StepID, &ls.Agent, &fencing, &paths, &expires); err != nil {
		return lease.Lease{}, err
	}
	ls.Purpose, ls.Feature, ls.Fencing = lease.Purpose(purpose), feature.String, uint64(fencing)
	if err := json.Unmarshal([]byte(paths), &ls.WritePaths); err != nil {
		return lease.Lease{}, err
	}
	var err error
	ls.ExpiresAt, err = parseStamp(expires)
	return ls, err
}

func (l leaseRepo) one(ctx context.Context, what, where string, args ...any) (lease.Lease, error) {
	ls, err := l.scan(l.tx.QueryRowContext(ctx, `SELECT `+leaseColumns+` FROM leases `+where, args...))
	if errors.Is(err, sql.ErrNoRows) {
		return lease.Lease{}, notFound(what)
	}
	return ls, err
}

func (l leaseRepo) Get(ctx context.Context, id string) (lease.Lease, error) {
	return l.one(ctx, "lease "+id, `WHERE id = ?`, id)
}

func (l leaseRepo) ActiveFor(ctx context.Context, runID, stepID string) (lease.Lease, error) {
	return l.one(ctx, "no active lease", `WHERE status = 'active' AND run_id = ? AND step_id = ?`, runID, stepID)
}

func (l leaseRepo) status(ctx context.Context, id string) (string, string, error) {
	var status, hash string
	err := l.tx.QueryRowContext(ctx, `SELECT status, token_sha256 FROM leases WHERE id = ?`, id).Scan(&status, &hash)
	if errors.Is(err, sql.ErrNoRows) {
		return "", "", notFound("lease " + id)
	}
	return status, hash, err
}

func (l leaseRepo) Release(ctx context.Context, id string) error {
	res, err := l.tx.ExecContext(ctx, `UPDATE leases SET status = 'released' WHERE id = ?`, id)
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return notFound("lease " + id)
	}
	return nil
}

func (l leaseRepo) TokenHash(ctx context.Context, id string) (string, error) {
	_, hash, err := l.status(ctx, id)
	return hash, err
}

func (l leaseRepo) Extend(ctx context.Context, id, tokenHash string, now, until time.Time) (lease.Lease, error) {
	status, hash, err := l.status(ctx, id)
	if err != nil {
		return lease.Lease{}, err
	}
	if hash != tokenHash {
		return lease.Lease{}, &ports.ConflictError{Kind: ports.ConflictLeaseHeld, Detail: "token does not match lease " + id}
	}
	if status != "active" {
		return lease.Lease{}, &ports.ConflictError{Kind: ports.ConflictLeaseHeld,
			Detail: fmt.Sprintf("lease %s is %s, not active", id, status)}
	}
	ls, err := l.Get(ctx, id)
	if err != nil {
		return lease.Lease{}, err
	}
	if ls.Expired(now) {
		return lease.Lease{}, &ports.ConflictError{Kind: ports.ConflictLeaseHeld,
			Detail: fmt.Sprintf("lease %s ran out at %s; a late renewal cannot resurrect it",
				id, ls.ExpiresAt.Format(time.RFC3339))}
	}
	if _, err := l.tx.ExecContext(ctx, `UPDATE leases SET expires_at = ? WHERE id = ?`, stamp(until), id); err != nil {
		return lease.Lease{}, err
	}
	ls.ExpiresAt = until
	return ls, nil
}

// NextFencing is one past the highest token the feature has seen. Leases are
// never deleted, so the maximum only grows; the write lock taken at BEGIN
// keeps two acquirers from reading the same maximum.
func (l leaseRepo) NextFencing(ctx context.Context, featureID string) (uint64, error) {
	var max sql.NullInt64
	err := l.tx.QueryRowContext(ctx, `SELECT MAX(fencing_token) FROM leases WHERE feature_id = ?`, featureID).Scan(&max)
	if err != nil {
		return 0, err
	}
	return uint64(max.Int64) + 1, nil
}

func (l leaseRepo) Expire(ctx context.Context, now time.Time, limit int) ([]lease.Lease, error) {
	if limit <= 0 {
		limit = -1
	}
	rows, err := l.tx.QueryContext(ctx, `SELECT `+leaseColumns+` FROM leases
		WHERE status = 'active' AND expires_at < ? ORDER BY id LIMIT ?`, stamp(now), limit)
	if err != nil {
		return nil, err
	}
	var out []lease.Lease
	for rows.Next() {
		ls, err := l.scan(rows)
		if err != nil {
			rows.Close()
			return nil, err
		}
		out = append(out, ls)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return nil, err
	}
	for _, ls := range out {
		if _, err := l.tx.ExecContext(ctx, `UPDATE leases SET status = 'expired' WHERE id = ?`, ls.ID); err != nil {
			return nil, err
		}
	}
	return out, nil
}

// --- not wired ---------------------------------------------------------------

type unwiredDelegations struct{}

func (unwiredDelegations) Insert(context.Context, ports.Delegation) error { return errNotWired }
func (unwiredDelegations) Get(context.Context, string) (ports.Delegation, error) {
	return ports.Delegation{}, errNotWired
}
func (unwiredDelegations) Latest(context.Context, string, string) (ports.Delegation, error) {
	return ports.Delegation{}, errNotWired
}
func (unwiredDelegations) Update(context.Context, ports.Delegation) error { return errNotWired }
func (unwiredDelegations) RecordVerification(context.Context, string, string, string, []string, time.Time) error {
	return errNotWired
}

type unwiredBaselines struct{}

func (unwiredBaselines) Put(context.Context, string, baseline.Manifest, string) (string, error) {
	return "", errNotWired
}
func (unwiredBaselines) Sealed(context.Context, string) (baseline.Manifest, error) {
	return baseline.Manifest{}, errNotWired
}
func (unwiredBaselines) Get(context.Context, string) (baseline.Manifest, error) {
	return baseline.Manifest{}, errNotWired
}
func (unwiredBaselines) Seal(context.Context, string, time.Time) error { return errNotWired }
func (unwiredBaselines) Reopen(context.Context, string) error          { return errNotWired }

func nullable(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func nonNil(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}

var _ ports.Store = (*Store)(nil)
