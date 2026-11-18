// Command ideva is the first-party agent CLI: the idev conductor in its
// own binary, model-agnostic through the OpenAI-compatible provider
// layer (ollama / JDCloud / local JCP), hosting the same five executors
// and the same kernel pages that Claude Code and Cursor host today.
//
// The conductor here has exactly one privilege it did not have as a
// guest: its tools enforce the boundaries in code (signoff fields, git
// push, engine fallbacks). And exactly one it still does not have:
// signing anything. The person's terminal keeps that, same as always.
package main

import (
	"bufio"
	"context"
	"os/exec"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/idev/internal/agent/loop"
	"github.com/idev/internal/agent/mcpclient"
	"github.com/idev/internal/agent/provider"
	"github.com/idev/internal/agent/session"
	"github.com/idev/internal/agent/skill"
	"github.com/idev/internal/agent/tools"
	"github.com/idev/internal/adapters/store/sqlite"
)

// findIdevd locates the idevd binary for MCP mounting: the kernel's bin/
// next to the checkout (same place go build -o bin/idevd puts it), else
// PATH. Empty string means "no control plane mounted" — not an error, a
// degraded mode the banner names.
func findIdevd(kernel string, binDir string) string {
	if binDir != "" {
		candidate := filepath.Join(binDir, "idevd")
		if st, err := os.Stat(candidate); err == nil && !st.IsDir() {
			return candidate
		}
	}
	if kernel != "" {
		candidate := filepath.Join(kernel, "bin", "idevd")
		if st, err := os.Stat(candidate); err == nil && !st.IsDir() {
			return candidate
		}
	}
	if path, err := exec.LookPath("idevd"); err == nil {
		return path
	}
	return ""
}

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	fs := flag.NewFlagSet("ideva", flag.ContinueOnError)
	prompt := fs.String("p", "", "one-shot prompt: run once, print the answer, exit")
	model := fs.String("model", os.Getenv("IDEVA_MODEL"), "model name (IDEVA_MODEL)")
	baseURL := fs.String("base-url", os.Getenv("IDEVA_BASE_URL"), "OpenAI-compatible base URL (IDEVA_BASE_URL)")
	apiKey := fs.String("api-key", os.Getenv("IDEVA_API_KEY"), "API key (IDEVA_API_KEY)")
	kernel := fs.String("kernel", "", "kernel checkout root (default: resolve like the rest of idev)")
	dbPath := fs.String("db", "", "session database path (default: ~/.idev/agent.db)")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *model == "" {
		fmt.Fprintln(os.Stderr, "ideva: -model is required (or IDEVA_MODEL); e.g. -model qwen3:14b")
		return 2
	}
	root := *kernel
	if root == "" {
		home, _ := os.UserHomeDir()
		root = filepath.Join(home, ".cursor", "skills", "idev")
	}
	if _, err := os.Stat(filepath.Join(root, "SKILL.md")); err != nil {
		fmt.Fprintf(os.Stderr, "ideva: kernel checkout not found at %s (pass -kernel)\n", root)
		return 1
	}
	db := *dbPath
	if db == "" {
		home, _ := os.UserHomeDir()
		db = filepath.Join(home, ".idev", "agent.db")
	}
	if err := os.MkdirAll(filepath.Dir(db), 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "ideva: db dir: %v\n", err)
		return 1
	}
	store, err := sqlite.Open(context.Background(), db)
	if err != nil {
		fmt.Fprintf(os.Stderr, "ideva: open db: %v\n", err)
		return 1
	}
	defer store.Close()
	sessions := session.NewSQLiteStore(store.DB())

	cs, err := skill.AssembleConductor(root)
	if err != nil {
		fmt.Fprintf(os.Stderr, "ideva: %v\n", err)
		return 1
	}

	p := provider.NewOpenAI(provider.Config{BaseURL: *baseURL, APIKey: *apiKey, Model: *model})
	cwd, _ := os.Getwd()
	toolSet := map[string]loop.Tool{
		"bash":  &tools.Bash{WorkDir: cwd, Deny: tools.DefaultDenyRules(), LogDir: filepath.Join(cwd, ".idev", "agent-logs")},
		"read":  &tools.Read{},
		"write": &tools.Write{},
		"grep":  &tools.Grep{},
	}
	// Mount the control plane over MCP: idevd's tools become callable by
	// the conductor (run/lease/baseline/delegation surfaces), prefixed so
	// they cannot shadow the built-ins. A failed mount degrades to the
	// built-in set — the conductor says why and carries on.
	mcpMgr := &mcpclient.Manager{}
	defer mcpMgr.Close()
	mounts := []mcpclient.ServerSpec{}
	if idevd := findIdevd(root, ""); idevd != "" {
		mounts = append(mounts, mcpclient.ServerSpec{Name: "idev", Command: idevd + " mcp"})
	}
	if len(mounts) > 0 {
		mcpTools, errs := mcpMgr.ConnectAll(context.Background(), mounts)
		for _, e := range errs {
			fmt.Fprintf(os.Stderr, "ideva: mcp mount: %v\n", e)
		}
		for name, t := range mcpTools {
			toolSet[name] = t
		}
		if len(mcpTools) > 0 {
			fmt.Fprintf(os.Stderr, "ideva: mounted %d control-plane tools over MCP\n", len(mcpTools))
		}
	}
	l := &loop.Loop{Provider: p, Tools: toolSet, MaxTurns: 40, MaxHistoryChars: 200000}
	l.OnDelta = func(d provider.Delta) {
		if d.Text != "" {
			fmt.Print(d.Text)
			fmt.Print("\x1b[0m") //nolint:stylecheck — terminal reset, harmless in pipes
		}
	}

	sess := session.Session{Kind: "main", Agent: "conductor", Provider: p.Describe(), Model: *model, Repo: cwd}
	if err := sessions.CreateSession(context.Background(), &sess); err != nil {
		fmt.Fprintf(os.Stderr, "ideva: session: %v\n", err)
		return 1
	}
	history := []provider.Message{{Role: provider.RoleSystem, Content: cs.SystemPrompt}}
	persisted := 0

	if *prompt != "" {
		res, err := l.Run(context.Background(), &history, *prompt)
		if err != nil {
			fmt.Fprintf(os.Stderr, "ideva: %v\n", err)
			return 1
		}
		persisted = persistNew(sessions, sess.ID, history, persisted)
		if !strings.HasSuffix(res.Text, "\n") {
			fmt.Println()
		}
		return 0
	}

	// REPL: the conversation continues until the person says exit.
	// Slash commands are host conveniences; everything else is a prompt.
	fmt.Printf("ideva session %s — provider %s — /exit to quit\n", sess.ID, p.Describe())
	sc := bufio.NewScanner(os.Stdin)
	sc.Buffer(make([]byte, 0, 64*1024), 1<<20)
	for {
		fmt.Print("\n> ")
		if !sc.Scan() {
			fmt.Println()
			return 0
		}
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		switch line {
		case "/exit", "/quit":
			return 0
		case "/agents":
			listAgents(root)
			continue
		case "/help":
			fmt.Println("/agents — list the five executors; /exit — quit")
			continue
		}
		res, err := l.Run(context.Background(), &history, line)
		persisted = persistNew(sessions, sess.ID, history, persisted)
		if err != nil {
			fmt.Fprintf(os.Stderr, "ideva: %v\n", err)
			continue
		}
		if res.Text == "" {
			fmt.Println("(no text answer)")
		}
	}
}

// persistNew appends the messages the store has not seen yet. The caller
// owns the count: the loop's in-memory history is the working copy, the
// store is the replay copy, and a store failure prints rather than kills —
// but per-message errors are surfaced because a silent transcript gap is
// how a resume lies to the next session.
func persistNew(sessions session.Store, id string, history []provider.Message, from int) int {
	for _, m := range history[from:] {
		if err := sessions.AppendMessage(context.Background(), id, m); err != nil {
			fmt.Fprintf(os.Stderr, "ideva: transcript: %v\n", err)
		}
	}
	return len(history)
}

func listAgents(root string) {
	for _, name := range []string{"idev-coder", "idev-deliver", "idev-reviewer", "idev-verifier", "idev-ops"} {
		_, _, _, err := skill.AssembleExecutor(root, name)
		if err != nil {
			fmt.Printf("  %-14s (definition unreadable: %v)\n", name, err)
			continue
		}
		fmt.Printf("  %-14s mounted (frontmatter honored by this host)\n", name)
	}
}
