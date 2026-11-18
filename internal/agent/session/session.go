// Package session is the ideva conversation transcript: an append-only
// store plus the jsonl export the rest of the tooling already knows how to
// read. Until now idev owned no conversation storage — the transcript
// belonged to whichever host ran the conductor (session_transcript.py reads
// Claude Code's files). A first-party conductor gets a first-party
// transcript, and the DeepSeek-Harness rule the kernel already follows
// applies verbatim: what the model saw goes to the log first; the next
// attempt replays from the log, never from memory.
package session

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/idev/internal/agent/provider"
	"github.com/idev/internal/domain/ulid"
)

// Session is one conversation: a main ideva session, or one subagent
// session spawned by a delegation.
type Session struct {
	ID       string
	Kind     string // "main" or "subagent"
	ParentID string // set for subagent sessions
	Agent    string // conductor name or executor name
	Provider string
	Model    string
	Repo     string
}

// Store persists sessions and messages. SQLite behind it; the interface
// exists so tests and future stores (postgres) can swap in.
type Store interface {
	CreateSession(ctx context.Context, s *Session) error
	// AppendMessage appends one message with the next sequence number.
	// Append-only by design: there is no update, no delete, and no
	// second writer — the control plane's review finding §3.2 was exactly
	// two writers racing, and the answer is the same here.
	AppendMessage(ctx context.Context, sessionID string, m provider.Message) error
	// Messages replays the whole session in order, for resume and for the
	// loop's history.
	Messages(ctx context.Context, sessionID string) ([]provider.Message, error)
}

// SQLiteStore is Store over the shared sqlite database.
type SQLiteStore struct {
	db *sql.DB
	mu sync.Mutex
}

// NewSQLiteStore binds to an open database (the one migrations maintain).
func NewSQLiteStore(db *sql.DB) *SQLiteStore {
	return &SQLiteStore{db: db}
}

func now() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}

// newID is ulid.New with the clock wired in — the two-value return of the
// domain helper is right for the control plane's explicit error paths;
// a transcript id that cannot be minted is unrecoverable anyway.
func newID() string {
	id, err := ulid.New(uint64(time.Now().UnixMilli()))
	if err != nil {
		// Unreachable in practice (48-bit clock); a transcript row without
		// an id would be worse than a panic here.
		panic(fmt.Sprintf("session: ulid: %v", err))
	}
	return id
}

// CreateSession implements Store.
func (s *SQLiteStore) CreateSession(ctx context.Context, sess *Session) error {
	if sess.ID == "" {
		sess.ID = newID()
	}
	kind := sess.Kind
	if kind == "" {
		kind = "main"
	}
	// Go's empty string is not SQL's NULL: a "" parent would violate the
	// self-referencing foreign key. The driver's sql.NullString is the
	// honest translation of "no parent".
	var parent any
	if sess.ParentID != "" {
		parent = sess.ParentID
	}
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO agent_sessions (id, kind, parent_session_id, agent, provider, model, repo, created_at, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		sess.ID, kind, parent, sess.Agent, sess.Provider, sess.Model, sess.Repo, now(), now())
	if err != nil {
		return fmt.Errorf("session: create: %w", err)
	}
	return nil
}

// AppendMessage implements Store. Sequence numbers are allocated under the
// same lock across sessions sharing this handle, which is what makes the
// UNIQUE(session_id, seq) constraint a backstop rather than the only
// serialization point.
func (s *SQLiteStore) AppendMessage(ctx context.Context, sessionID string, m provider.Message) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	var seq int
	if err := s.db.QueryRowContext(ctx, `SELECT COALESCE(MAX(seq), -1) + 1 FROM agent_messages WHERE session_id = ?`, sessionID).Scan(&seq); err != nil {
		return fmt.Errorf("session: next seq: %w", err)
	}
	toolCallsJSON := ""
	if len(m.ToolCalls) > 0 {
		rows := make([]struct {
			ID   string `json:"id"`
			Name string `json:"name"`
			Args string `json:"args"`
		}, 0, len(m.ToolCalls))
		for _, tc := range m.ToolCalls {
			rows = append(rows, struct {
				ID   string `json:"id"`
				Name string `json:"name"`
				Args string `json:"args"`
			}{ID: tc.ID, Name: tc.Name, Args: string(tc.ArgsJSON)})
		}
		blob, err := json.Marshal(rows)
		if err != nil {
			return fmt.Errorf("session: marshal tool calls: %w", err)
		}
		toolCallsJSON = string(blob)
	}
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO agent_messages (id, session_id, seq, role, content, tool_calls_json, tool_call_id, tool_name, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		newID(), sessionID, seq, m.Role, m.Content, toolCallsJSON, m.ToolCallID, m.Name, now())
	if err != nil {
		return fmt.Errorf("session: append: %w", err)
	}
	_, _ = s.db.ExecContext(ctx, `UPDATE agent_sessions SET updated_at = ? WHERE id = ?`, now(), sessionID)
	return nil
}

// Messages implements Store.
func (s *SQLiteStore) Messages(ctx context.Context, sessionID string) ([]provider.Message, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT role, content, tool_calls_json, tool_call_id, tool_name
		FROM agent_messages WHERE session_id = ? ORDER BY seq`, sessionID)
	if err != nil {
		return nil, fmt.Errorf("session: list: %w", err)
	}
	defer rows.Close()
	var out []provider.Message
	for rows.Next() {
		var m provider.Message
		var toolCallsJSON, toolCallID, toolName sql.NullString
		if err := rows.Scan(&m.Role, &m.Content, &toolCallsJSON, &toolCallID, &toolName); err != nil {
			return nil, fmt.Errorf("session: scan: %w", err)
		}
		m.ToolCallID = toolCallID.String
		m.Name = toolName.String
		if toolCallsJSON.Valid && toolCallsJSON.String != "" {
			var rows []struct {
				ID   string `json:"id"`
				Name string `json:"name"`
				Args string `json:"args"`
			}
			if err := json.Unmarshal([]byte(toolCallsJSON.String), &rows); err != nil {
				return nil, fmt.Errorf("session: unmarshal tool calls: %w", err)
			}
			for _, r := range rows {
				m.ToolCalls = append(m.ToolCalls, provider.ToolCall{ID: r.ID, Name: r.Name, ArgsJSON: json.RawMessage(r.Args)})
			}
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// JSONL appends one message to the session's jsonl transcript. The
// database is the queryable copy; the jsonl is the replay copy that
// session_transcript.py-style tooling can read line by line. Write
// failures are returned but callers may downgrade them: the database is
// the source of truth and a jsonl miss is a WARN, not a lost conversation.
func JSONL(dir, sessionID string, m provider.Message) error {
	row := struct {
		SessionID string             `json:"session_id"`
		Role      string             `json:"role"`
		Content   string             `json:"content"`
		ToolCalls []provider.ToolCall `json:"tool_calls,omitempty"`
		ToolCallID string            `json:"tool_call_id,omitempty"`
		Name      string             `json:"name,omitempty"`
		At        string             `json:"at"`
	}{
		SessionID: sessionID,
		Role:      m.Role,
		Content:   m.Content,
		ToolCalls: m.ToolCalls,
		ToolCallID: m.ToolCallID,
		Name:       m.Name,
		At:         now(),
	}
	blob, err := json.Marshal(row)
	if err != nil {
		return fmt.Errorf("session: jsonl marshal: %w", err)
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("session: jsonl dir: %w", err)
	}
	path := filepath.Join(dir, sessionID+".jsonl")
	fh, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("session: jsonl open: %w", err)
	}
	defer fh.Close()
	if _, err := fh.Write(append(blob, '\n')); err != nil {
		return fmt.Errorf("session: jsonl write: %w", err)
	}
	return nil
}
