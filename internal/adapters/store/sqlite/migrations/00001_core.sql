-- +goose Up
-- The tables that carry the invariants. Everything interesting here is a
-- constraint, not a column: the review's §3.2 findings were all "two writers
-- raced and the second one won silently", and the fix is for the database to
-- refuse rather than for the application to remember.
--
-- SQLite specifics: STRICT tables so a type error is an error, and partial
-- unique indexes (supported since 3.8) for the "at most one live X" rules.

CREATE TABLE features (
    id              TEXT    PRIMARY KEY,
    workspace       TEXT    NOT NULL,
    feature_key     TEXT    NOT NULL,
    stage           TEXT    NOT NULL,
    risk_tier       TEXT    NOT NULL DEFAULT 'P1',
    baseline_id     TEXT,
    revision        INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
) STRICT;
CREATE UNIQUE INDEX features_key_uq ON features(workspace, feature_key);

CREATE TABLE runs (
    id              TEXT    PRIMARY KEY,
    workflow_id     TEXT    NOT NULL,
    feature_id      TEXT    NOT NULL REFERENCES features(id),
    recipe_digest   TEXT,
    bundle_version  TEXT,
    status          TEXT    NOT NULL,
    track           TEXT,
    params_json     TEXT    NOT NULL DEFAULT '{}',
    policy_json     TEXT    NOT NULL DEFAULT '{}',
    drift           INTEGER NOT NULL DEFAULT 0,
    -- Optimistic concurrency: a writer that read version N may only write
    -- N+1, so two concurrent step records cannot both land.
    version         INTEGER NOT NULL DEFAULT 1,
    started_at      TEXT    NOT NULL,
    ended_at        TEXT,
    created_at      TEXT    NOT NULL
) STRICT;

-- One live run per (feature, workflow). `workflow.py` enforced this by
-- reading the file first and refusing; between the read and the write there
-- was nothing stopping a second start.
CREATE UNIQUE INDEX runs_live_uq ON runs(feature_id, workflow_id)
    WHERE status IN ('pending', 'running', 'awaiting_human', 'blocked');

CREATE TABLE steps (
    run_id          TEXT    NOT NULL REFERENCES runs(id),
    step_id         TEXT    NOT NULL,
    ordinal         INTEGER NOT NULL,
    kind            TEXT    NOT NULL,
    label           TEXT,
    with_json       TEXT    NOT NULL DEFAULT '{}',
    state           TEXT    NOT NULL,
    status          TEXT,
    attempt         INTEGER NOT NULL DEFAULT 0,
    evidence        TEXT,
    note            TEXT,
    writer          TEXT,
    verifier        TEXT,
    approval_id     TEXT,
    at              TEXT,
    PRIMARY KEY (run_id, step_id)
) STRICT;
CREATE UNIQUE INDEX steps_ordinal_uq ON steps(run_id, ordinal);

CREATE TABLE step_revisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL REFERENCES runs(id),
    step_id         TEXT,
    from_status     TEXT,
    to_status       TEXT,
    note            TEXT    NOT NULL,
    at              TEXT    NOT NULL
) STRICT;

CREATE TABLE leases (
    id              TEXT    PRIMARY KEY,
    purpose         TEXT    NOT NULL,
    feature_id      TEXT    REFERENCES features(id),
    run_id          TEXT    NOT NULL REFERENCES runs(id),
    step_id         TEXT    NOT NULL,
    agent           TEXT    NOT NULL,
    token_sha256    TEXT    NOT NULL,
    -- Monotonic per feature. A report carrying an older token is a report
    -- from a holder that has already been superseded.
    fencing_token   INTEGER NOT NULL,
    write_paths_json TEXT   NOT NULL DEFAULT '[]',
    status          TEXT    NOT NULL,
    issued_at       TEXT    NOT NULL,
    expires_at      TEXT    NOT NULL
) STRICT;

-- Invariant I-1. The application also checks; this is what makes it true
-- under concurrency.
CREATE UNIQUE INDEX leases_single_writer_feature ON leases(feature_id)
    WHERE status = 'active' AND purpose = 'write' AND feature_id IS NOT NULL;
CREATE UNIQUE INDEX leases_single_writer_run ON leases(run_id)
    WHERE status = 'active' AND purpose = 'write';
CREATE INDEX leases_sweep_idx ON leases(status, expires_at);

CREATE TABLE delegations (
    id              TEXT    PRIMARY KEY,
    run_id          TEXT    NOT NULL REFERENCES runs(id),
    step_id         TEXT    NOT NULL,
    attempt         INTEGER NOT NULL,
    agent           TEXT    NOT NULL,
    lease_id        TEXT    REFERENCES leases(id),
    packet_json     TEXT    NOT NULL,
    return_json     TEXT,
    checks_json     TEXT,
    state           TEXT    NOT NULL,
    outcome         TEXT,
    submitted_via   TEXT,
    issued_at       TEXT    NOT NULL,
    returned_at     TEXT,
    accepted_at     TEXT
) STRICT;

-- Invariant I-5. `delegation.py write` named records by filename and
-- defaulted attempt to 1, so a second write replaced the first and reported
-- OK — taking the reason for the retry with it.
CREATE UNIQUE INDEX delegations_attempt_uq ON delegations(run_id, step_id, attempt);

CREATE TABLE verifications (
    id              TEXT    PRIMARY KEY,
    delegation_id   TEXT    NOT NULL REFERENCES delegations(id),
    verifier        TEXT    NOT NULL,
    verdict         TEXT    NOT NULL,
    evidence_json   TEXT    NOT NULL DEFAULT '[]',
    at              TEXT    NOT NULL
) STRICT;
CREATE UNIQUE INDEX verifications_one_per_delegation ON verifications(delegation_id);

CREATE TABLE baselines (
    id              TEXT    PRIMARY KEY,
    feature_id      TEXT    NOT NULL REFERENCES features(id),
    revision        INTEGER NOT NULL,
    status          TEXT    NOT NULL,
    manifest_json   TEXT    NOT NULL,
    manifest_root   TEXT    NOT NULL,
    raw_root        TEXT    NOT NULL,
    repo_head       TEXT,
    dirty           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    sealed_at       TEXT
) STRICT;
CREATE UNIQUE INDEX baselines_revision_uq ON baselines(feature_id, revision);
-- At most one sealed baseline per feature: two would make "what was agreed"
-- ambiguous.
CREATE UNIQUE INDEX baselines_one_sealed ON baselines(feature_id)
    WHERE status = 'sealed';

CREATE TABLE gates (
    id                 TEXT    PRIMARY KEY,
    gate_type          TEXT    NOT NULL,
    run_id             TEXT    REFERENCES runs(id),
    step_id            TEXT,
    feature_id         TEXT    NOT NULL REFERENCES features(id),
    risk_tier          TEXT    NOT NULL,
    subject_kind       TEXT    NOT NULL,
    subject_digest     TEXT    NOT NULL,
    baseline_revision  INTEGER,
    will_write_json    TEXT    NOT NULL DEFAULT '[]',
    proof              TEXT,
    required_assurance TEXT    NOT NULL,
    required_keywords_json TEXT NOT NULL DEFAULT '[]',
    challenge          TEXT,
    status             TEXT    NOT NULL,
    created_at         TEXT    NOT NULL,
    expires_at         TEXT    NOT NULL
) STRICT;
-- One open question per step, so a conductor cannot ask twice and apply
-- whichever answer it prefers.
CREATE UNIQUE INDEX gates_one_pending_per_step ON gates(run_id, step_id)
    WHERE status = 'pending' AND run_id IS NOT NULL AND step_id IS NOT NULL;

CREATE TABLE approvals (
    id              TEXT    PRIMARY KEY,
    gate_id         TEXT    NOT NULL REFERENCES gates(id),
    gate_type       TEXT    NOT NULL,
    decision        TEXT    NOT NULL,
    subject_digest  TEXT    NOT NULL,
    approver_handle TEXT    NOT NULL,
    approver_kind   TEXT    NOT NULL,
    assurance       TEXT    NOT NULL,
    downgraded      INTEGER NOT NULL DEFAULT 0,
    quote           TEXT    NOT NULL,
    channel         TEXT,
    credential_json TEXT,
    signature_json  TEXT    NOT NULL,
    decided_at      TEXT    NOT NULL,
    -- Invariant I-3, at the storage layer. The RBAC check and the domain
    -- check both say this; a CHECK constraint says it even if someone
    -- writes SQL by hand.
    CHECK (approver_kind = 'human')
) STRICT;
CREATE UNIQUE INDEX approvals_one_per_gate ON approvals(gate_id);

CREATE TABLE idempotency_keys (
    key             TEXT    PRIMARY KEY,
    scope           TEXT    NOT NULL,
    result_json     TEXT,
    created_at      TEXT    NOT NULL
) STRICT;

CREATE TABLE audit_events (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    at              TEXT    NOT NULL,
    action          TEXT    NOT NULL,
    actor_handle    TEXT    NOT NULL,
    actor_kind      TEXT    NOT NULL,
    on_behalf_of    TEXT,
    via             TEXT,
    run_id          TEXT,
    step_id         TEXT,
    feature         TEXT,
    subject         TEXT,
    detail_json     TEXT,
    prev_hash       TEXT    NOT NULL,
    hash            TEXT    NOT NULL
) STRICT;
CREATE INDEX audit_run_idx ON audit_events(run_id, seq);

CREATE TABLE audit_checkpoints (
    seq             INTEGER PRIMARY KEY,
    hash            TEXT    NOT NULL,
    at              TEXT    NOT NULL,
    key_id          TEXT    NOT NULL,
    signature       TEXT    NOT NULL
) STRICT;

-- +goose StatementBegin
-- Append-only, enforced by the database. The hash chain detects tampering
-- after the fact; this stops the easy case outright, and the two are
-- independent on purpose.
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;
-- +goose StatementEnd

-- +goose StatementBegin
-- An approval is a record of something a person said. Editing one is not a
-- correction, it is a forgery; a new gate is the way to change a decision.
CREATE TRIGGER approvals_no_update BEFORE UPDATE ON approvals
BEGIN
    SELECT RAISE(ABORT, 'approvals are immutable; open a new gate instead');
END;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE TRIGGER approvals_no_delete BEFORE DELETE ON approvals
BEGIN
    SELECT RAISE(ABORT, 'approvals are immutable; open a new gate instead');
END;
-- +goose StatementEnd

-- +goose Down
DROP TRIGGER IF EXISTS approvals_no_delete;
DROP TRIGGER IF EXISTS approvals_no_update;
DROP TRIGGER IF EXISTS audit_no_delete;
DROP TRIGGER IF EXISTS audit_no_update;
DROP TABLE IF EXISTS audit_checkpoints;
DROP TABLE IF EXISTS audit_events;
DROP TABLE IF EXISTS idempotency_keys;
DROP TABLE IF EXISTS approvals;
DROP TABLE IF EXISTS gates;
DROP TABLE IF EXISTS baselines;
DROP TABLE IF EXISTS verifications;
DROP TABLE IF EXISTS delegations;
DROP TABLE IF EXISTS leases;
DROP TABLE IF EXISTS step_revisions;
DROP TABLE IF EXISTS steps;
DROP TABLE IF EXISTS runs;
DROP TABLE IF EXISTS features;
