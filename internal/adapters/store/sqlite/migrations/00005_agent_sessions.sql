-- +goose Up
-- Sessions and messages for the ideva agent CLI. idev owned no conversation
-- storage before this: the transcript belonged to whichever host (Claude
-- Code / Cursor) ran the conductor. A first-party conductor gets a
-- first-party transcript, and the same rules the control plane learned the
-- hard way apply here too — append-only, no silent overwrite, ids that sort.

CREATE TABLE agent_sessions (
    id          TEXT    PRIMARY KEY,
    kind        TEXT    NOT NULL CHECK (kind IN ('main', 'subagent')),
    -- parent_session_id is set for subagent sessions: which main session
    -- delegated this one. The delegation trail lives in the control plane;
    -- this column is for transcript navigation, not enforcement.
    parent_session_id TEXT REFERENCES agent_sessions(id),
    agent       TEXT    NOT NULL,
    provider    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    repo        TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
) STRICT;

CREATE INDEX agent_sessions_parent ON agent_sessions(parent_session_id);

CREATE TABLE agent_messages (
    id          TEXT    PRIMARY KEY,
    session_id  TEXT    NOT NULL REFERENCES agent_sessions(id),
    seq         INTEGER NOT NULL,
    role        TEXT    NOT NULL CHECK (role IN ('system','user','assistant','tool')),
    content     TEXT    NOT NULL,
    -- tool_calls_json: assistant messages that asked for tools carry the
    -- array here (name, id, raw args). Raw, not re-marshalled: re-marshalling
    -- reorders keys and hides duplicates from any schema check downstream.
    tool_calls_json TEXT,
    tool_call_id    TEXT,
    tool_name      TEXT,
    created_at  TEXT    NOT NULL,
    UNIQUE (session_id, seq)
) STRICT;

CREATE INDEX agent_messages_session ON agent_messages(session_id, seq);
