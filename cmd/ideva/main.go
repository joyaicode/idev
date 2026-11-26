// Command ideva is the first-party agent CLI: the idev conductor in its
// own binary, model-agnostic through the OpenAI-compatible provider
// layer (ollama / JDCloud / local JCP), hosting the same five executors
// and the same kernel pages that Claude Code and Cursor host today.
//
// The conductor here has exactly one privilege it did not have as a
// guest: its tools enforce the boundaries in code (signoff fields, git
// push, engine fallbacks). And exactly one it still does not have:
// signing anything. The person's terminal keeps that, same as always.
//
// Model access resolves in this order: -model/-preset/-base-url/-api-key
// flags (and IDEVA_* env), then the channels file (-channels, default
// ~/.idev/channels.yaml: several named providers, each with its own
// models; /use and /model switch mid-session without losing history).
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

type runtime struct {
	// p is the live provider; swapped in place by /use and /model.
	p *provider.OpenAI
	// model is the current model name (loop providers carry it in cfg).
	model string
	// channels is nil when no channels file loaded — flag/env mode.
	channels *provider.ChannelSet
	// channelName is the active channel from the file, "" in flag mode.
	channelName string
}

func (rt *runtime) describe() string {
	return rt.p.Describe()
}

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(args []string) int {
	// `ideva fan ...` is the parallel wave executor — it needs the provider
	// and session wiring below but none of the REPL scaffolding, so it is
	// dispatched before the flag set parses anything else.
	if len(args) > 0 && args[0] == "fan" {
		return runFanDispatch(args[1:])
	}
	fs := flag.NewFlagSet("ideva", flag.ContinueOnError)
	prompt := fs.String("p", "", "one-shot prompt: run once, print the answer, exit")
	model := fs.String("model", os.Getenv("IDEVA_MODEL"), "model name (IDEVA_MODEL)")
	preset := fs.String("preset", os.Getenv("IDEVA_PRESET"), "provider preset: ollama | jdcloud | jcp (IDEVA_PRESET); fills base URL/key defaults, overridden by -base-url/-api-key")
	baseURL := fs.String("base-url", os.Getenv("IDEVA_BASE_URL"), "OpenAI-compatible base URL (IDEVA_BASE_URL)")
	apiKey := fs.String("api-key", os.Getenv("IDEVA_API_KEY"), "API key (IDEVA_API_KEY)")
	channelsPath := fs.String("channels", os.Getenv("IDEVA_CHANNELS"), "channels file with several providers/models (default ~/.idev/channels.yaml); /use and /model switch mid-session")
	kernel := fs.String("kernel", "", "kernel checkout root (default: resolve like the rest of idev)")
	dbPath := fs.String("db", "", "session database path (default: ~/.idev/agent.db)")
	if err := fs.Parse(args); err != nil {
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

	// Model access resolves in this order: explicit flags/env, then the
	// channels file, then hard requirements. A channels file with neither
	// -model nor -preset is self-sufficient (its default channel and
	// default model carry the session); flags still win when given.
	chPath := *channelsPath
	if chPath == "" {
		home, _ := os.UserHomeDir()
		chPath = filepath.Join(home, ".idev", "channels.yaml")
	}
	channels, chErr := provider.LoadChannels(chPath)
	if chErr != nil {
		// A present-but-broken channels file is a startup error, not a
		// silent flag-mode fallback: the person wrote the file to be
		// used; half-ignoring it lands /use on the wrong endpoint.
		fmt.Fprintf(os.Stderr, "ideva: %v\n", chErr)
		return 2
	}
	rt := &runtime{channels: channels}
	if *preset != "" || *baseURL != "" || *apiKey != "" || *model != "" {
		if *model == "" {
			fmt.Fprintln(os.Stderr, "ideva: -model is required with explicit provider flags (or IDEVA_MODEL); e.g. -model qwen3:14b")
			return 2
		}
		// A preset fills defaults; explicit flags and env win — that order
		// is what "preset is a default, not a lock" means in code.
		cfg := provider.Config{Model: *model}
		if *preset != "" {
			pre, err := provider.Preset(*preset)
			if err != nil {
				fmt.Fprintf(os.Stderr, "ideva: %v\n", err)
				return 2
			}
			if pre.BaseURL != "" {
				cfg.BaseURL = pre.BaseURL
			}
			if pre.APIKey != "" {
				cfg.APIKey = pre.APIKey
			}
		}
		if *baseURL != "" {
			cfg.BaseURL = *baseURL
		}
		if *apiKey != "" {
			cfg.APIKey = *apiKey
		}
		rt.p = provider.NewOpenAI(cfg)
		rt.model = *model
	} else if channels != nil {
		name := channels.DefaultChannel()
		if name == "" {
			name = channels.Names()[0]
		}
		cfg, err := channels.Build(name, "")
		if err != nil {
			fmt.Fprintf(os.Stderr, "ideva: %v\n", err)
			return 2
		}
		rt.p = provider.NewOpenAI(cfg)
		rt.model = cfg.Model
		rt.channelName = name
	} else {
		fmt.Fprintln(os.Stderr, "ideva: -model is required (or IDEVA_MODEL); or configure ~/.idev/channels.yaml with providers/models; e.g. -model qwen3:14b")
		return 2
	}
	p := rt.p
	cwd, _ := os.Getwd()
	toolSet := map[string]loop.Tool{
		"bash":  &tools.Bash{WorkDir: cwd, Deny: tools.DefaultDenyRules(), LogDir: filepath.Join(cwd, ".idev", "agent-logs")},
		"read":  &tools.Read{},
		"write": &tools.Write{},
		"grep":  &tools.Grep{},
		"glob":  &tools.Glob{},
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

	sess := session.Session{Kind: "main", Agent: "conductor", Provider: rt.describe(), Model: rt.model, Repo: cwd}
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
	fmt.Printf("ideva session %s — provider %s — /exit to quit\n", sess.ID, rt.describe())
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
		switch {
		case line == "/exit", line == "/quit":
			return 0
		case line == "/agents":
			listAgents(root)
			continue
		case line == "/help":
			printHelp(rt)
			continue
		case line == "/channels":
			listChannels(rt)
			continue
		case line == "/models":
			listModels(rt)
			continue
		case strings.HasPrefix(line, "/use"), strings.HasPrefix(line, "/model"):
			fields := strings.Fields(line)
			if len(fields) < 2 {
				fmt.Println("usage: /use <channel> | /model <name> — see /channels, /models")
				continue
			}
			switch fields[0] {
			case "/use":
				if err := switchChannel(rt, fields[1]); err != nil {
					fmt.Printf("not switched: %v\n", err)
				} else {
					fmt.Printf("switched to %s — %s\n", fields[1], rt.describe())
				}
			case "/model":
				if err := switchModel(rt, fields[1]); err != nil {
					fmt.Printf("not switched: %v\n", err)
				} else {
					fmt.Printf("model %s — %s\n", rt.model, rt.describe())
				}
			}
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

// switchChannel swaps the live provider to another channel from the
// loaded config. History is untouched: the same conversation continues on
// the new model, the way a person changes desks, not the topic.
func switchChannel(rt *runtime, name string) error {
	if rt.channels == nil {
		return fmt.Errorf("no channels file loaded (start ideva without provider flags and with a valid ~/.idev/channels.yaml)")
	}
	cfg, err := rt.channels.Build(name, "")
	if err != nil {
		return err
	}
	rt.p = provider.NewOpenAI(cfg)
	rt.model = cfg.Model
	rt.channelName = name
	return nil
}

// switchModel swaps only the model; the channel (base URL, key) stays.
// In flag mode there is no channel and no list — any model name is
// accepted, same as the -model flag itself; the new provider is built
// from the current one's config with the model replaced.
func switchModel(rt *runtime, name string) error {
	var cfg provider.Config
	if rt.channels == nil {
		cfg = rt.p.Config()
		cfg.Model = name
	} else {
		var err error
		cfg, err = rt.channels.Build(rt.channelName, name)
		if err != nil {
			return err
		}
	}
	rt.p = provider.NewOpenAI(cfg)
	rt.model = cfg.Model
	return nil
}

func printHelp(rt *runtime) {
	fmt.Println("/agents — list the five executors")
	fmt.Println("/channels — list configured model channels")
	fmt.Println("/models — list models of the active channel")
	fmt.Println("/use <channel> — switch provider/channel")
	fmt.Println("/model <name> — switch model within the channel")
	fmt.Println("/exit — quit")
}

func listChannels(rt *runtime) {
	if rt.channels == nil {
		fmt.Println("no channels file loaded — running from flags/env only")
		return
	}
	for _, name := range rt.channels.Names() {
		e, _ := rt.channels.Entry(name)
		mark := " "
		if name == rt.channelName {
			mark = "*"
		}
		def := ""
		if name == rt.channels.DefaultChannel() {
			def = " (default)"
		}
		fmt.Printf(" %s%-10s preset=%s base_url=%s models=%d%s\n", mark, name, e.Preset, e.BaseURL, len(e.Models), def)
	}
}

func listModels(rt *runtime) {
	if rt.channels == nil {
		fmt.Printf("active model: %s (no channels file; any /model <name> is accepted)\n", rt.model)
		return
	}
	e, ok := rt.channels.Entry(rt.channelName)
	if !ok {
		fmt.Printf("active model: %s (channel %q not in the loaded config)\n", rt.model, rt.channelName)
		return
	}
	if len(e.Models) == 0 {
		fmt.Printf("channel %s lists no models; any /model <name> is accepted (current: %s)\n", rt.channelName, rt.model)
		return
	}
	for _, m := range e.Models {
		mark := " "
		if m == rt.model {
			mark = "*"
		}
		fmt.Printf(" %s %s\n", mark, m)
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
