// Package delegate gives the ideva conductor its one distinctive tool:
// handing a step to one of the five executors, in a fresh session, and
// getting the report back through the same checks the Python kernel runs.
//
// The packet protocol is the kernel's, unchanged: the 9-line brief
// (references/agents.md「委派包」), the frontmatter tool whitelist
// (enforced by THIS host — the thing a third-party host cannot do), and
// the return contract (STATUS/EVIDENCE/…, validated as shapes, never
// scored). A subagent session is a session: own transcript, own history,
// parent link, and exactly one input — the brief.
package delegate

import (
	"context"
	"os"
	"fmt"
	"strings"

	"github.com/idev/internal/agent/loop"
	"github.com/idev/internal/agent/provider"
	"github.com/idev/internal/agent/session"
	"github.com/idev/internal/agent/skill"
)

// Executor is one of the five, as the host sees it.
type Executor struct {
	Name        string
	System      string      // the definition body, frontmatter stripped
	Tools       []string    // frontmatter whitelist — enforced below
	Frontmatter string
	SHA256      string
}

// Registry loads all executors from the kernel checkout.
type Registry struct {
	Root      string
	Executors map[string]*Executor
}

// Load reads the five definitions. A missing or unparsable definition is
// an error: a delegation to an executor the host cannot mount must fail
// at mount time, not mid-task.
func Load(root string, names []string) (*Registry, error) {
	r := &Registry{Root: root, Executors: map[string]*Executor{}}
	for _, name := range names {
		cs, front, tools, err := skill.AssembleExecutor(root, name)
		if err != nil {
			return nil, err
		}
		if len(tools) == 0 {
			// The kernel's own agents all declare a tools line; an empty
			// one here means the file drifted and the host must not
			// silently run an executor with every tool.
			return nil, fmt.Errorf("delegate: %s declares no tools whitelist; refusing full access", name)
		}
		r.Executors[name] = &Executor{
			Name:        name,
			System:      cs.SystemPrompt,
			Tools:       tools,
			Frontmatter: front,
			SHA256:      cs.Pages[0].SHA256,
		}
	}
	return r, nil
}

// Pool builds the tool map an executor is allowed to use: the registry's
// full tool set minus everything its frontmatter does not name. This is
// the enforcement agents.md describes as prompt-level on Cursor — in this
// host it is code, because the host owns the map.
func (r *Registry) Pool(name string, full map[string]loop.Tool) (map[string]loop.Tool, error) {
	ex, ok := r.Executors[name]
	if !ok {
		return nil, fmt.Errorf("delegate: unknown executor %q", name)
	}
	pool := map[string]loop.Tool{}
	for _, t := range ex.Tools {
		if tool, ok := full[t]; ok {
			pool[t] = tool
		}
	}
	if len(pool) == 0 {
		return nil, fmt.Errorf("delegate: %s tools (%s) match nothing the host provides", name, strings.Join(ex.Tools, ","))
	}
	return pool, nil
}

// Run executes one delegation: fresh subagent session, brief as the only
// user message, loop until a plain-text report, transcript persisted, and
// the report's return-contract lines checked for presence (shape, never
// semantics — the kernel's「机检查的是诚实性和形态」rule).
func Run(ctx context.Context, opts Options) (Report, error) {
	ex, ok := opts.Registry.Executors[opts.Executor]
	if !ok {
		return Report{}, fmt.Errorf("delegate: unknown executor %q", opts.Executor)
	}
	_ = ex
	pool, err := opts.Registry.Pool(opts.Executor, opts.Tools)
	if err != nil {
		return Report{}, err
	}
	sess := session.Session{
		Kind:     "subagent",
		ParentID: opts.ParentSession,
		Agent:    opts.Executor,
		Provider: opts.Provider.Describe(),
		Model:    opts.Model,
		Repo:     opts.Repo,
	}
	if err := opts.Sessions.CreateSession(ctx, &sess); err != nil {
		return Report{}, fmt.Errorf("delegate: session: %w", err)
	}
	history := []provider.Message{
		{Role: provider.RoleSystem, Content: ex.System},
		{Role: provider.RoleUser, Content: opts.Brief},
	}
	l := &loop.Loop{
		Provider:        opts.Provider,
		Tools:           pool,
		MaxTurns:        opts.MaxTurns,
		MaxHistoryChars: 100000,
	}
	res, runErr := l.Run(ctx, &history, "")
	// The transcript of a failed delegation is the evidence for why it
	// failed; persist what exists whether the run ended clean or not.
	persistAll(opts.Sessions, sess.ID, history)
	if runErr != nil {
		return Report{Text: res.Text}, runErr
	}
	rep := ParseReport(res.Text)
	rep.SessionID = sess.ID
	return rep, nil
}

func persistAll(sessions session.Store, id string, history []provider.Message) {
	for _, m := range history {
		if err := sessions.AppendMessage(context.Background(), id, m); err != nil {
			// Transcript append failing is a WARN, never a task killer:
			// the store is the replay copy, the report is the result.
			fmt.Fprintf(os.Stderr, "ideva delegate: transcript: %v\n", err)
		}
	}
}

// Options binds one delegation run.
type Options struct {
	Registry      *Registry
	Executor     string
	Provider      provider.Provider
	Sessions      session.Store
	Tools         map[string]loop.Tool
	ParentSession string
	Brief         string
	Model         string
	Repo          string
	MaxTurns      int
}

// Report is the executor's plain-text answer, parsed the way
// delegation.py parses: lines starting with the contract markers are
// lifted into fields; everything else stays in Text. Presence of the
// mandatory lines is a shape check (ReportOK), not a quality judgment.
type Report struct {
	Status   string
	Evidence string
	Text     string
	SessionID string
}

// ParseReport lifts STATUS and EVIDENCE lines (the two the kernel marks
// 必填). The rest of the contract lines stay in Text — the caller that
// needs them reads them there, unchanged.
func ParseReport(text string) Report {
	rep := Report{Text: text}
	for _, line := range strings.Split(text, "\n") {
		trimmed := strings.TrimSpace(line)
		if rep.Status == "" {
			if after, ok := strings.CutPrefix(trimmed, "STATUS:"); ok {
				rep.Status = strings.TrimSpace(after)
				continue
			}
		}
		if rep.Evidence == "" {
			if after, ok := strings.CutPrefix(trimmed, "EVIDENCE:"); ok {
				rep.Evidence = strings.TrimSpace(after)
				continue
			}
		}
	}
	return rep
}

// Complete is the shape check: the mandatory lines exist and STATUS is
// one of the real values. It mirrors delegation.py's return-schema
// stance: a report without these is BLOCKED back to the executor, never
// accepted on trust. EVIDENCE is mandatory for PASS; BLOCKED's evidence
// is its own explanation (the "BLOCKED(logic)" convention), so a
// BLOCKED shape passes without a separate EVIDENCE line.
func (r Report) Complete() bool {
	upper := strings.ToUpper(strings.TrimSpace(r.Status))
	switch upper {
	case "PASS", "FAIL", "UNPROVEN":
		return r.Evidence != "" || strings.Contains(strings.ToUpper(r.Text), "EVIDENCE")
	case "BLOCKED":
		return true
	default:
		return false
	}
}
