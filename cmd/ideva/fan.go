package main

// fan: the true-parallel executor for a fanout wave. It walks the same
// chain the conductor walks by hand — assess → PREP → step --shard →
// delegate → land --shard → merge — in code. Nothing bypasses a gate the
// kernel owns: each shard's lease comes from `workflow.py step --shard`
// (the command the conductor runs), each report returns through
// `workflow.py land --shard` (whose write path is delegation.py's five
// honesty checks), and record/签字 stay with the conductor. fan never
// calls record.
import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/idev/internal/agent/delegate"
	"github.com/idev/internal/agent/loop"
	"github.com/idev/internal/agent/parallel"
	"github.com/idev/internal/agent/provider"
	"github.com/idev/internal/agent/session"
	"github.com/idev/internal/agent/tools"
	"github.com/idev/internal/adapters/store/sqlite"
)

const fanMaxWaves = 4

// fanPlan is what the assess line protocol said, parsed.
type fanPlan struct {
	serial  bool
	merge   bool
	prep    []string
	shardID []string
	queued  []string
	reason  string
}

// parseFanLines reads fanout.py render output. The protocol is lines:
// SERIAL/MERGE verdicts, PREP commands, SHARD/QUEUED ids. Everything else
// (DOCK, HINT, SCOPE, LEASE) is for a person's eyes and ignored here.
func parseFanLines(out string) fanPlan {
	var p fanPlan
	for _, raw := range strings.Split(out, "\n") {
		line := strings.TrimSpace(raw)
		switch {
		case strings.HasPrefix(line, "SERIAL "):
			p.serial = true
			p.reason = strings.TrimPrefix(line, "SERIAL ")
		case strings.HasPrefix(line, "MERGE ") && strings.Contains(line, "shard drafts are in"):
			p.merge = true
		case strings.HasPrefix(line, "PREP "):
			p.prep = append(p.prep, strings.TrimSpace(strings.TrimPrefix(line, "PREP ")))
		case strings.HasPrefix(line, "SHARD "):
			fields := strings.Fields(strings.TrimPrefix(line, "SHARD "))
			if len(fields) > 0 {
				p.shardID = append(p.shardID, fields[0])
			}
		case strings.HasPrefix(line, "QUEUED "):
			fields := strings.Fields(strings.TrimPrefix(line, "QUEUED "))
			if len(fields) > 0 {
				p.queued = append(p.queued, fields[0])
			}
		}
	}
	return p
}

// fanRunner carries the pieces one wave needs.
type fanRunner struct {
	feature  string
	step     string
	cap      int
	kernel   string
	repo     string
	registry *delegate.Registry
	provider *provider.OpenAI
	sessions session.Store
	tools    map[string]loop.Tool
	model    string
}

func (fr *fanRunner) py(script string, args ...string) (string, error) {
	cmd := exec.Command("python3", append([]string{filepath.Join(fr.kernel, "scripts", script)}, args...)...)
	cmd.Dir = fr.repo
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func (fr *fanRunner) pyStdin(script string, stdin string, args ...string) (string, error) {
	cmd := exec.Command("python3", append([]string{filepath.Join(fr.kernel, "scripts", script)}, args...)...)
	cmd.Dir = fr.repo
	cmd.Stdin = strings.NewReader(stdin)
	out, err := cmd.CombinedOutput()
	return string(out), err
}

// prepLog runs the PREP lines and writes one shared log. The PREPs are
// kernel scripts the conductor would have run before delegating; the
// shards share the output, so it lands beside the ticket as one file —
// the same place drive's _auto_prep puts it.
func (fr *fanRunner) prepLog(prep []string) (string, error) {
	if len(prep) == 0 {
		return "", nil
	}
	work, err := fr.py("lib/doc_home.py", "--repo", fr.repo, "--feature", fr.feature, "--key", "work")
	if err != nil {
		return "", fmt.Errorf("fan: doc_home: %v", err)
	}
	dir := strings.TrimSpace(work)
	if err := os.MkdirAll(filepath.Join(dir, "workflow"), 0o755); err != nil {
		return "", err
	}
	logPath := filepath.Join(dir, "workflow", "prep-report.log")
	var log strings.Builder
	for _, line := range prep {
		fmt.Fprintf(&log, "$ %s\n", line)
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		cmd := exec.Command(fields[0], fields[1:]...)
		cmd.Dir = fr.repo
		out, err := cmd.CombinedOutput()
		log.Write(out)
		if err != nil {
			fmt.Fprintf(&log, "\n(prep exited: %v)\n", err)
		}
		log.WriteString("\n")
	}
	if err := os.WriteFile(logPath, []byte(log.String()), 0o644); err != nil {
		return "", err
	}
	return logPath, nil
}

// briefFor leases the shard and captures the brief `workflow.py step`
// prints. The lease, the brief file, the LAND instruction — exactly what
// the conductor would have run; fan only removes the copy-paste between
// the commands and the agent conversations.
func (fr *fanRunner) briefFor(shard string, prepLogPath string) (string, error) {
	args := []string{"step", fr.step, "--feature", fr.feature, "--shard", shard}
	if prepLogPath != "" {
		args = append(args, "--prep-log", prepLogPath)
	}
	out, err := fr.py("workflow.py", args...)
	if err != nil {
		return "", fmt.Errorf("fan: step %s: %v\n%s", shard, err, out)
	}
	return out, nil
}

// landFor hands the report back through the kernel's own land path.
func (fr *fanRunner) landFor(shard string, report string) (string, error) {
	return fr.pyStdin("workflow.py", report, "land", fr.step,
		"--feature", fr.feature, "--shard", shard, "--report", "-")
}

// errDone marks the two clean early exits (already merged / nothing to
// delegate) without inventing a third state in the wave loop.
type errDone struct {
	merged bool
	reason string
}

func (e errDone) Error() string {
	if e.merged {
		return "merged"
	}
	return "serial: " + e.reason
}

func asDone(err error, done *errDone) bool {
	if err == nil {
		return false
	}
	d, ok := err.(errDone)
	if !ok {
		return false
	}
	*done = d
	return true
}

// wave runs one assess-plan-execute-land cycle. Returns the count of
// shards that failed (no auto-retry — the conductor decides).
func (fr *fanRunner) wave(ctx context.Context) (int, error) {
	out, err := fr.py("fanout.py", "assess", "--feature", fr.feature, "--activity", "report")
	if err != nil {
		return 0, fmt.Errorf("fan: assess: %v\n%s", err, out)
	}
	plan := parseFanLines(out)
	if plan.merge {
		if _, err := fr.py("fanout.py", "merge", "--feature", fr.feature, "--activity", "report"); err != nil {
			return 0, fmt.Errorf("fan: merge: %v", err)
		}
		return 0, errDone{merged: true}
	}
	if plan.serial && len(plan.shardID) == 0 {
		return 0, errDone{reason: plan.reason}
	}
	prepPath, err := fr.prepLog(plan.prep)
	if err != nil {
		return 0, err
	}
	if prepPath != "" {
		fmt.Printf("fan: PREP log %s (shared by every shard)\n", prepPath)
	}

	type shardWork struct {
		id    string
		brief string
	}
	works := make([]shardWork, 0, len(plan.shardID))
	for _, id := range plan.shardID {
		brief, err := fr.briefFor(id, prepPath)
		if err != nil {
			return 0, err
		}
		works = append(works, shardWork{id: id, brief: brief})
	}

	tasks := make([]parallel.Task, len(works))
	for i, w := range works {
		tasks[i] = parallel.Task{Executor: "idev-reviewer", Brief: w.brief}
	}
	fmt.Printf("fan: wave of %d shard(s) (cap %d, queued %d)\n", len(tasks), fr.cap, len(plan.queued))

	results := parallel.Batch(ctx, fr.cap, tasks, func(ctx context.Context, t parallel.Task) delegate.Report {
		rep, err := delegate.Run(ctx, delegate.Options{
			Registry: fr.registry,
			Executor: t.Executor,
			Provider: fr.provider,
			Sessions: fr.sessions,
			Tools:    fr.tools,
			Brief:    t.Brief,
			Model:    fr.model,
			Repo:     fr.repo,
			MaxTurns: 60,
		})
		if err != nil {
			return delegate.Report{Text: "STATUS: FAIL\nEVIDENCE: fan: " + err.Error()}
		}
		return rep
	}, nil)

	failed := 0
	for i, res := range results {
		id := works[i].id
		if res.Err != nil {
			fmt.Fprintf(os.Stderr, "fan: shard %s: %v (no report to land)\n", id, res.Err)
			failed++
			continue
		}
		if !res.Report.Complete() {
			fmt.Fprintf(os.Stderr, "fan: shard %s: report shape incomplete; not landing it\n%s\n", id, res.Report.Text)
			failed++
			continue
		}
		out, err := fr.landFor(id, res.Report.Text)
		if err != nil {
			fmt.Fprintf(os.Stderr, "fan: land %s: %v\n%s\n", id, err, out)
			failed++
			continue
		}
		fmt.Printf("fan: shard %s landed\n", id)
		if strings.Contains(out, "record the step once") || strings.Contains(out, "MERGE report") {
			fmt.Println("fan: all shards landed; merge done — review.md is current")
		}
	}
	return failed, nil
}

// runFanDispatch resolves provider/session wiring the same way main does
// (flags/env, then channels), then hands off to runFanCmd. It exists so
// the `ideva fan` entry point shares the main path's resolution order
// without the REPL.
func runFanDispatch(args []string) int {
	fs := flag.NewFlagSet("ideva-fan", flag.ContinueOnError)
	model := fs.String("model", os.Getenv("IDEVA_MODEL"), "model name (IDEVA_MODEL)")
	preset := fs.String("preset", os.Getenv("IDEVA_PRESET"), "provider preset: ollama | jdcloud | jcp")
	baseURL := fs.String("base-url", os.Getenv("IDEVA_BASE_URL"), "OpenAI-compatible base URL")
	apiKey := fs.String("api-key", os.Getenv("IDEVA_API_KEY"), "API key")
	channelsPath := fs.String("channels", os.Getenv("IDEVA_CHANNELS"), "channels file (default ~/.idev/channels.yaml)")
	kernel := fs.String("kernel", "", "kernel checkout root (default: resolve like the rest of idev)")
	dbPath := fs.String("db", "", "session database path (default: ~/.idev/agent.db)")
	fanArgs := []string{}
	rest := args
	// Split the leading provider flags from the trailing fan flags
	// (-feature/-step/-cap): flag.Parse would choke on the mixed set.
	for i := 0; i < len(rest); i++ {
		switch rest[i] {
		case "-feature", "-step", "-cap":
			fanArgs = append(fanArgs, rest[i])
			if i+1 < len(rest) {
				i++
				fanArgs = append(fanArgs, rest[i])
			}
		default:
			_ = fs.Parse(rest[i : i+1])
		}
	}
	_ = fanArgs
	if err := fs.Parse(args); err != nil {
		return 2
	}
	root := *kernel
	if root == "" {
		home, _ := os.UserHomeDir()
		root = filepath.Join(home, ".cursor", "skills", "idev")
	}
	if _, err := os.Stat(filepath.Join(root, "SKILL.md")); err != nil {
		fmt.Fprintf(os.Stderr, "ideva fan: kernel checkout not found at %s (pass -kernel)\n", root)
		return 1
	}
	db := *dbPath
	if db == "" {
		home, _ := os.UserHomeDir()
		db = filepath.Join(home, ".idev", "agent.db")
	}
	if err := os.MkdirAll(filepath.Dir(db), 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "ideva fan: db dir: %v\n", err)
		return 1
	}
	store, err := sqlite.Open(context.Background(), db)
	if err != nil {
		fmt.Fprintf(os.Stderr, "ideva fan: open db: %v\n", err)
		return 1
	}
	defer store.Close()
	sessions := session.NewSQLiteStore(store.DB())

	rt := &runtime{}
	switch {
	case *model != "" || *preset != "" || *baseURL != "" || *apiKey != "":
		if *model == "" {
			fmt.Fprintln(os.Stderr, "ideva fan: -model is required with explicit provider flags; e.g. -model qwen3:14b")
			return 2
		}
		cfg := provider.Config{Model: *model}
		if *preset != "" {
			pre, err := provider.Preset(*preset)
			if err != nil {
				fmt.Fprintf(os.Stderr, "ideva fan: %v\n", err)
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
	default:
		chPath := *channelsPath
		if chPath == "" {
			home, _ := os.UserHomeDir()
			chPath = filepath.Join(home, ".idev", "channels.yaml")
		}
		channels, err := provider.LoadChannels(chPath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "ideva fan: %v\n", err)
			return 2
		}
		if channels == nil {
			fmt.Fprintln(os.Stderr, "ideva fan: -model is required; or configure ~/.idev/channels.yaml")
			return 2
		}
		name := channels.DefaultChannel()
		if name == "" {
			name = channels.Names()[0]
		}
		cfg, err := channels.Build(name, "")
		if err != nil {
			fmt.Fprintf(os.Stderr, "ideva fan: %v\n", err)
			return 2
		}
		rt.p = provider.NewOpenAI(cfg)
		rt.model = cfg.Model
	}
	return runFanCmd(fanArgs, rt, sessions, root, "")
}

func runFanCmd(args []string, rt *runtime, sessions session.Store, kernel string, repo string) int {
	fs := flag.NewFlagSet("fan", flag.ContinueOnError)
	feature := fs.String("feature", "", "the ticket's feature slug (required)")
	step := fs.String("step", "report", "the review.report step id in the current run")
	capFlag := fs.Int("cap", parallel.DefaultCap, "shards per wave (max 8, fanout's ceiling)")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *feature == "" {
		fmt.Fprintln(os.Stderr, "ideva fan: -feature is required")
		return 2
	}
	registry, err := delegate.Load(kernel, []string{"idev-reviewer"})
	if err != nil {
		fmt.Fprintf(os.Stderr, "ideva fan: %v\n", err)
		return 1
	}
	cwd, _ := os.Getwd()
	if repo == "" {
		repo = cwd
	}
	fr := &fanRunner{
		feature:  *feature,
		step:     *step,
		cap:      *capFlag,
		kernel:   kernel,
		repo:     repo,
		registry: registry,
		provider: rt.p,
		sessions: sessions,
		model:    rt.model,
	}
	// The tool pool mirrors the host's own set; delegate.Run narrows it by
	// the executor's frontmatter whitelist.
	pool, err := registry.Pool("idev-reviewer", map[string]loop.Tool{
		"bash":  &tools.Bash{WorkDir: repo, Deny: tools.DefaultDenyRules(), LogDir: filepath.Join(repo, ".idev", "agent-logs")},
		"read":  &tools.Read{},
		"write": &tools.Write{},
		"grep":  &tools.Grep{},
		"glob":  &tools.Glob{},
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "ideva fan: %v\n", err)
		return 1
	}
	fr.tools = pool

	ctx := context.Background()
	for wave := 0; wave < fanMaxWaves; wave++ {
		failed, err := fr.wave(ctx)
		var done errDone
		if asDone(err, &done) {
			if done.merged {
				fmt.Println("fan: merged — review.md is current; the conductor records the step")
			} else {
				fmt.Printf("fan: SERIAL — %s\nthe conductor delegates this one step itself\n", done.reason)
			}
			return 0
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "ideva fan: %v\n", err)
			return 1
		}
		if failed > 0 {
			fmt.Fprintln(os.Stderr, "ideva fan: shards failed; fix and re-run — v1 does not auto-retry")
			return 1
		}
		// One clean wave: assess again — a MERGE follows (drafts all in),
		// the queued tail becomes the next wave, or SERIAL ends it.
		out, err := fr.py("fanout.py", "assess", "--feature", fr.feature, "--activity", "report")
		if err != nil {
			fmt.Fprintf(os.Stderr, "ideva fan: %v\n", err)
			return 1
		}
		next := parseFanLines(out)
		if next.merge {
			if _, err := fr.py("fanout.py", "merge", "--feature", fr.feature, "--activity", "report"); err != nil {
				fmt.Fprintf(os.Stderr, "ideva fan: merge: %v\n", err)
				return 1
			}
			fmt.Println("fan: wave complete — review.md current; the conductor records the step and the person reviews it")
			return 0
		}
		if next.serial && len(next.shardID) == 0 {
			fmt.Println("fan: wave complete — review.md current; the conductor records the step and the person reviews it")
			return 0
		}
		fmt.Println("fan: next wave (queued tail)")
	}
	fmt.Fprintln(os.Stderr, "ideva fan: wave cap reached; re-run to continue the queued tail")
	return 1
}
