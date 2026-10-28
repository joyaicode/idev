package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/idev/internal/adapters/kindreg"
	"github.com/idev/internal/adapters/local"
	"github.com/idev/internal/adapters/runyaml"
	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/adapters/workspace"
	"github.com/idev/internal/app/auditsvc"
	"github.com/idev/internal/app/gatesvc"
	"github.com/idev/internal/app/leasesvc"
	"github.com/idev/internal/app/runsvc"
	"github.com/idev/internal/domain/audit"
	"github.com/idev/internal/domain/gate"
	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/domain/run"
	"github.com/idev/internal/domain/signoff"
	"github.com/idev/internal/ports"
	"github.com/idev/pkg/canonical"

	"go.yaml.in/yaml/v3"
)

// Exit codes: 0 done, 1 refused (the answer is no, or the state forbids it),
// 2 usage.
const (
	exitOK      = 0
	exitRefused = 1
	exitUsage   = 2
)

// shortLen is how many trailing characters of the gate id the person types.
const shortLen = 4

type app struct {
	stdin          io.Reader
	stdout, stderr io.Writer
	isTTY          func() bool
	// peopleFiles overrides the whitelist lookup; nil means peopleSearch().
	peopleFiles []string
}

func (a app) run(args []string) int {
	if len(args) < 2 {
		fmt.Fprintln(a.stderr, "usage: idev gate request|approve|reject|status ... | idev lease acquire|release|check ... | idev run start|apply|record|write ... | idev baseline seal|adopt|verify|sealed ... | idev delegation allocate|verify|accept ... | idev audit downgrades|export|verify ... | idev workspace locate|manifest|diff|head ... | idev token init --handle H")
		return exitUsage
	}
	ctx := context.Background()
	var err error
	switch args[0] + " " + args[1] {
	case "gate request":
		err = a.request(ctx, args[2:])
	case "gate approve":
		err = a.answer(ctx, args[2:], false)
	case "gate reject":
		err = a.answer(ctx, args[2:], true)
	case "gate status":
		err = a.status(ctx, args[2:])
	case "token init":
		err = a.tokenInit(args[2:])
	case "lease acquire":
		err = a.leaseAcquire(ctx, args[2:])
	case "lease release":
		err = a.leaseRelease(ctx, args[2:])
	case "lease check":
		err = a.leaseCheck(ctx, args[2:])
	case "run start":
		err = a.runStart(args[2:])
	case "run apply":
		err = a.runApply(args[2:])
	case "run record":
		err = a.runRecord(args[2:])
	case "run write":
		err = a.runWrite(args[2:])
	case "baseline seal":
		err = a.baselineSeal(ctx, args[2:])
	case "baseline adopt":
		err = a.baselineAdopt(ctx, args[2:])
	case "baseline verify":
		err = a.baselineVerify(ctx, args[2:])
	case "baseline sealed":
		err = a.baselineSealed(ctx, args[2:])
	case "delegation allocate":
		err = a.delegationAllocate(ctx, args[2:])
	case "delegation verify":
		err = a.delegationVerify(ctx, args[2:])
	case "delegation accept":
		err = a.delegationAccept(ctx, args[2:])
	case "audit downgrades":
		err = a.auditDowngrades(ctx, args[2:])
	case "audit export":
		err = a.auditExport(ctx, args[2:])
	case "audit verify":
		err = a.auditVerify(ctx, args[2:])
	case "workspace locate":
		err = a.workspaceLocate(args[2:])
	case "workspace manifest":
		err = a.workspaceManifest(args[2:])
	case "workspace diff":
		err = a.workspaceDiff(args[2:])
	case "workspace head":
		err = a.workspaceHead(args[2:])
	default:
		fmt.Fprintf(a.stderr, "idev: unknown command %q\n", strings.Join(args[:2], " "))
		return exitUsage
	}
	var ue usageError
	switch {
	case err == nil:
		return exitOK
	case errors.As(err, &ue):
		fmt.Fprintln(a.stderr, "idev:", err)
		return exitUsage
	default:
		fmt.Fprintln(a.stderr, "idev:", err)
		return exitRefused
	}
}

type usageError struct{ msg string }

func (u usageError) Error() string { return u.msg }

type multi []string

func (m *multi) String() string     { return strings.Join(*m, ",") }
func (m *multi) Set(v string) error { *m = append(*m, v); return nil }

// --- wiring ------------------------------------------------------------------

type env struct {
	store  *sqlite.Store
	svc    gatesvc.Service
	leases leasesvc.Service
	runs   runsvc.Service
	data   string
}

func (a app) open(ctx context.Context) (env, error) {
	data, err := local.DataDir()
	if err != nil {
		return env{}, err
	}
	if err := os.MkdirAll(data, 0o700); err != nil {
		return env{}, err
	}
	store, err := sqlite.Open(ctx, filepath.Join(data, "idev.db"))
	if err != nil {
		return env{}, err
	}
	signer, err := local.LoadOrCreateSigner(filepath.Join(data, "secrets", "signing.ed25519"))
	if err != nil {
		_ = store.Close()
		return env{}, err
	}
	files := a.peopleFiles
	if files == nil {
		files = peopleSearch()
	}
	identity, _, err := local.LoadPeople(files)
	if err != nil {
		_ = store.Close()
		return env{}, err
	}
	return env{
		store: store,
		data:  data,
		svc: gatesvc.Service{
			Store: store, Clock: local.Clock{}, IDs: local.IDs{}, Signer: signer,
			Authorizer: local.People{Identity: identity},
			// Passkeys are not wired, so every local answer is low. The
			// transition switch lets a high requirement complete at low and
			// the audit chain records each one as assurance_downgraded.
			// E6.1: passkey/high assurance turns off the local low-for-high downgrade.
			Policy: gate.Policy{AllowLowForHigh: os.Getenv("IDEV_REQUIRE_PASSKEY") == ""},
		},
		// Kinds 决定每个 step 领什么用途的租约、谁有权验证；不接的话 verify 租约会
		// 发给先到者（delegated 态只绑定 agent）。见 review A1。
		leases: leasesvc.Service{Store: store, Clock: local.Clock{}, IDs: local.IDs{}, Kinds: kindreg.MustLoad()},
		runs: runsvc.Service{
			Store: store, Clock: local.Clock{}, IDs: local.IDs{}, Registry: kindreg.MustLoad(),
		},
	}, nil
}

// peopleSearch mirrors workflow_spec._people_files: $IDEV_ROOT (and its
// kernel/), the kernel this binary was built into, then the product checkout.
func peopleSearch() []string {
	var out []string
	if root := strings.TrimSpace(os.Getenv("IDEV_ROOT")); root != "" {
		out = append(out,
			filepath.Join(root, "config", "people.yaml"),
			filepath.Join(root, "kernel", "config", "people.yaml"))
	}
	if exe, err := os.Executable(); err == nil {
		out = append(out, filepath.Join(filepath.Dir(filepath.Dir(exe)), "config", "people.yaml"))
	}
	if wd, err := os.Getwd(); err == nil {
		out = append(out, filepath.Join(wd, ".idev", "people.yaml"))
	}
	return out
}

// --- request -----------------------------------------------------------------

type requestOut struct {
	GateID            string   `json:"gate_id"`
	Short             string   `json:"short"`
	Type              string   `json:"type"`
	Risk              string   `json:"risk"`
	SubjectKind       string   `json:"subject_kind"`
	SubjectDigest     string   `json:"subject_digest"`
	Subject           []string `json:"subject,omitempty"`
	RequiredAssurance string   `json:"required_assurance"`
	ExpiresAt         string   `json:"expires_at"`
	Approve           string   `json:"approve"`
}

func (a app) request(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("gate request", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	var subject, willWrite multi
	feature := fs.String("feature", "", "feature id")
	typ := fs.String("type", "", "gate type")
	risk := fs.String("risk", "", "P0|P1|P2")
	runID := fs.String("run-id", "", "run id")
	step := fs.String("step", "", "step id")
	root := fs.String("root", "", "directory the subject paths are relative to")
	revision := fs.Int("revision", 0, "baseline revision (sealed, reopen_baseline)")
	origin := fs.String("origin", "", "origin (defect_origin)")
	proof := fs.String("proof", "", "evidence shown with the question")
	ttl := fs.Duration("ttl", 0, "how long the question stays open")
	fs.Var(&subject, "subject", "file the approval binds to (repeatable)")
	fs.Var(&willWrite, "will-write", "field the approval writes (repeatable)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *feature == "" || *typ == "" || *risk == "" {
		return usageError{"gate request needs --feature, --type and --risk"}
	}
	if len(subject) > 0 && *root == "" {
		return usageError{"--subject needs --root"}
	}

	t := gate.Type(*typ)
	subj := gate.Subject{Kind: gate.SubjectRunStep, BaselineRevision: *revision}
	var absRoot string
	if len(subject) > 0 {
		var err error
		if absRoot, err = filepath.Abs(*root); err != nil {
			return err
		}
		subj.Kind = gate.SubjectArtifactSet
		if t == gate.TypeSealed || t == gate.TypeReopenBaseline {
			subj.Kind = gate.SubjectBaseline
			// I-4: a seal binds the manifest_root, not a raw-file tree digest.
			// --revision stays mandatory (domain refuses revision 0).
			// absRoot is the ticket; workspace hashes baseline.yaml + details[].
			m, err := workspace.FromTicket(*feature, absRoot, "", *revision, time.Now().UTC())
			if err != nil {
				return err
			}
			subj.Digest = string(m.ManifestRoot)
		} else if subj.Digest, err = filesDigest(absRoot, subject); err != nil {
			return err
		}
	} else {
		subj.Digest = questionDigest(*feature, *runID, *step, *typ, willWrite, *proof)
	}

	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	g, err := e.svc.Ask(ctx, gatesvc.AskParams{
		Type: t, RunID: *runID, StepID: *step, Feature: *feature,
		Risk: gate.RiskTier(*risk), Subject: subj, Origin: *origin,
		WillWrite: willWrite, Proof: *proof, TTL: *ttl,
		SubjectRoot: absRoot, SubjectPaths: subject,
		Actor: ports.Principal{Handle: "workflow.py", Kind: "service"},
	})
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(requestOut{
		GateID: g.ID, Short: short(g.ID), Type: string(g.Type), Risk: string(g.Risk),
		SubjectKind: string(g.Subject.Kind), SubjectDigest: g.Subject.Digest, Subject: subject,
		RequiredAssurance: string(g.RequiredAssurance),
		ExpiresAt:         g.ExpiresAt.Format(time.RFC3339),
		Approve:           "idev gate approve " + g.ID,
	})
}

// filesDigest is canonical.Root over the subject files, so a person can
// reproduce it with sha256sum and sort.
func filesDigest(root string, paths []string) (string, error) {
	lines := make([]canonical.Line, 0, len(paths))
	for _, p := range paths {
		clean := filepath.ToSlash(filepath.Clean(p))
		if filepath.IsAbs(p) || clean == ".." || strings.HasPrefix(clean, "../") {
			return "", usageError{fmt.Sprintf("subject %q must be relative to --root and stay inside it", p)}
		}
		raw, err := os.ReadFile(filepath.Join(root, clean))
		if err != nil {
			return "", fmt.Errorf("subject %s: %w", clean, err)
		}
		lines = append(lines, canonical.Line{Path: clean, Digest: canonical.HashText(raw)})
	}
	return string(canonical.Root(lines)), nil
}

// questionDigest binds a gate with no files to the question itself: what is
// being confirmed, where, and on what evidence.
func questionDigest(feature, runID, step, typ string, willWrite []string, proof string) string {
	d, err := canonical.HashJCS(map[string]any{
		"feature": feature, "run_id": runID, "step_id": step, "type": typ,
		"will_write": []string(nonNil(willWrite)), "proof": proof,
	})
	if err != nil {
		panic(err) // strings only; JCS cannot fail on them
	}
	return string(d)
}

func nonNil(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}

func short(id string) string {
	if len(id) <= shortLen {
		return id
	}
	return id[len(id)-shortLen:]
}

// currentDigest recomputes what the gate binds to, as it is now.
func currentDigest(ctx context.Context, e env, g gate.Gate) (string, error) {
	root, paths, err := e.store.GateSubject(ctx, g.ID)
	if err != nil {
		return "", err
	}
	// A file gate with no binding row is not a question-only gate. Treating
	// the missing row as "binds to the question" would compare a different
	// digest and report a content change, which hides that the binding write
	// was lost.
	if g.Subject.Kind == gate.SubjectBaseline {
		if root == "" {
			return "", fmt.Errorf("subject binding missing for %s (%s)", g.ID, g.Subject.Kind)
		}
		m, err := workspace.FromTicket(g.Feature, root, "", g.Subject.BaselineRevision, time.Now().UTC())
		if err != nil {
			return "", err
		}
		return string(m.ManifestRoot), nil
	}
	if g.Subject.Kind == gate.SubjectArtifactSet {
		if len(paths) == 0 {
			return "", fmt.Errorf("subject binding missing for %s (%s)", g.ID, g.Subject.Kind)
		}
		return filesDigest(root, paths)
	}
	if len(paths) == 0 {
		return questionDigest(g.Feature, g.RunID, g.StepID, string(g.Type), g.WillWrite, g.Proof), nil
	}
	return filesDigest(root, paths)
}

// --- approve / reject --------------------------------------------------------

func (a app) answer(ctx context.Context, args []string, reject bool) error {
	verb := "approve"
	if reject {
		verb = "reject"
	}
	fs := flag.NewFlagSet("gate "+verb, flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	quote := fs.String("quote", "", "your words, verbatim")
	id, rest := splitID(args)
	if err := fs.Parse(rest); err != nil {
		return usageError{err.Error()}
	}
	if id == "" {
		return usageError{"gate " + verb + " needs a gate id"}
	}
	q := strings.TrimSpace(*quote)
	decision := gate.DecisionApprove
	if reject {
		decision = gate.DecisionReject
	}

	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	cred, err := local.ReadCredential(filepath.Join(e.data, "secrets", "human.yaml"))
	if err != nil {
		return err
	}
	g, err := e.svc.Get(ctx, id)
	if err != nil {
		return err
	}
	if g.Status == gate.StatusPending && !time.Now().Before(g.ExpiresAt) {
		if _, err := e.svc.Expire(ctx, id); err != nil {
			return err
		}
		return fmt.Errorf("gate %s expired at %s; ask again", id, g.ExpiresAt.Format(time.RFC3339))
	}
	if g.Status != gate.StatusPending {
		return fmt.Errorf("gate %s is %s, not pending", id, g.Status)
	}
	digest, err := currentDigest(ctx, e, g)
	if err != nil {
		return err
	}
	if digest != g.Subject.Digest {
		a.show(g, digest)
	}

	d, err := e.svc.Decide(ctx, gatesvc.DecisionParams{
		GateID: id, Quote: q, Decision: decision, Channel: gatesvc.ChannelChat,
		RecomputedDigest: digest, Actor: cred.Principal(),
	})
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"status":      string(d.Gate.Status),
		"gate_id":     id,
		"by":          d.Approval.Handle,
		"approval_id": d.Approval.ID,
		"assurance":   d.Approval.Assurance,
		"channel":     d.Approval.Channel,
		"downgraded":  d.Approval.Downgraded,
		"quote":       d.Approval.Quote,
	})
}

// quoteFromConversation refuses a quote the person did not say, once this
// session is logging prompts. With the check forced off, or with no log yet,
// the words themselves are the record — the same rule workflow.py uses.
func quoteFromConversation(quote string) error {
	flag := strings.ToLower(strings.TrimSpace(os.Getenv("IDEV_PROMPT_LOG_CHECK")))
	switch flag {
	case "0", "false", "no", "off":
		return nil
	case "1", "true", "yes":
		if !quoteInPromptsLog(quote) {
			return errors.New("the quote is not in this session's prompts.log; an answer is the person's own words")
		}
		return nil
	}
	if promptsLogActive() && !quoteInPromptsLog(quote) {
		return errors.New("the quote is not in this session's prompts.log; an answer is the person's own words")
	}
	return nil
}

func promptsLogFile() string {
	data, err := local.DataDir()
	if err != nil {
		return ""
	}
	return filepath.Join(data, "prompts.log")
}

func quoteInPromptsLog(quote string) bool {
	path := promptsLogFile()
	if path == "" {
		return false
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return false
	}
	needle := strings.TrimSpace(quote)
	if needle == "" {
		return false
	}
	for _, line := range strings.Split(string(body), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var row struct {
			Text string `json:"text"`
		}
		if json.Unmarshal([]byte(line), &row) != nil {
			if strings.Contains(line, needle) {
				return true
			}
			continue
		}
		text := strings.TrimSpace(row.Text)
		if needle == text || strings.Contains(text, needle) {
			return true
		}
	}
	return false
}

func promptsLogActive() bool {
	path := promptsLogFile()
	if path == "" {
		return false
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return false
	}
	cwd, err := os.Getwd()
	if err != nil {
		return false
	}
	lines := strings.Split(string(body), "\n")
	if len(lines) > 50 {
		lines = lines[len(lines)-50:]
	}
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if line == "" {
			continue
		}
		var row struct {
			Cwd string `json:"cwd"`
		}
		if json.Unmarshal([]byte(line), &row) != nil {
			continue
		}
		logged := strings.TrimSpace(row.Cwd)
		if logged == "" {
			continue
		}
		if logged == cwd || strings.HasPrefix(cwd, logged+string(os.PathSeparator)) || strings.HasPrefix(logged, cwd+string(os.PathSeparator)) {
			return true
		}
	}
	return false
}

// splitID takes the first non-flag argument as the gate id, so both
// `approve <id> --quote q` and `approve --quote q <id>` work.
func splitID(args []string) (string, []string) {
	var rest []string
	id := ""
	for i := 0; i < len(args); i++ {
		arg := args[i]
		switch {
		case strings.HasPrefix(arg, "-"):
			rest = append(rest, arg)
			if !strings.Contains(arg, "=") && i+1 < len(args) {
				rest = append(rest, args[i+1])
				i++
			}
		case id == "":
			id = arg
		default:
			rest = append(rest, arg)
		}
	}
	return id, rest
}

func (a app) show(g gate.Gate, digest string) {
	w := a.stdout
	fmt.Fprintf(w, "gate      %s (%s, %s, needs %s)\n", g.ID, g.Type, g.Risk, g.RequiredAssurance)
	fmt.Fprintf(w, "feature   %s", g.Feature)
	if g.RunID != "" {
		fmt.Fprintf(w, "  run %s  step %s", g.RunID, g.StepID)
	}
	fmt.Fprintln(w)
	for _, ww := range g.WillWrite {
		fmt.Fprintf(w, "will write %s\n", ww)
	}
	if g.Proof != "" {
		fmt.Fprintf(w, "proof     %s\n", g.Proof)
	}
	for _, kw := range g.RequiredKeywords {
		fmt.Fprintf(w, "keyword   %s\n", kw)
	}
	fmt.Fprintf(w, "subject   %s %s\n", g.Subject.Kind, g.Subject.Digest)
	if digest != g.Subject.Digest {
		fmt.Fprintf(w, "CHANGED   the content is now %s; answering will be refused\n", digest)
	}
}

// --- status ------------------------------------------------------------------

type statusOut struct {
	GateID            string       `json:"gate_id"`
	Status            string       `json:"status"`
	Type              string       `json:"type"`
	Risk              string       `json:"risk"`
	Feature           string       `json:"feature"`
	RunID             string       `json:"run_id,omitempty"`
	StepID            string       `json:"step_id,omitempty"`
	SubjectDigest     string       `json:"subject_digest"`
	DigestNow         string       `json:"digest_now"`
	DigestMatch       bool         `json:"digest_match"`
	RequiredAssurance string       `json:"required_assurance,omitempty"`
	ExpiresAt         string       `json:"expires_at"`
	Approval          *approvalOut `json:"approval,omitempty"`
}

type approvalOut struct {
	ID          string `json:"id"`
	Decision    string `json:"decision"`
	Handle      string `json:"handle"`
	Quote       string `json:"quote"`
	Assurance   string `json:"assurance"`
	Downgraded  bool   `json:"downgraded"`
	Channel     string `json:"channel"`
	DecidedAt   string `json:"decided_at"`
	SignatureOK bool   `json:"signature_ok"`
}

func (a app) status(ctx context.Context, args []string) error {
	id, _ := splitID(args)
	if id == "" {
		return usageError{"gate status needs a gate id"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	g, err := e.svc.Get(ctx, id)
	if err != nil {
		return err
	}
	if g.Status == gate.StatusPending && !time.Now().Before(g.ExpiresAt) {
		if g, err = e.svc.Expire(ctx, id); err != nil {
			return err
		}
	}
	digest, err := currentDigest(ctx, e, g)
	if err != nil {
		// A subject file that is gone is a mismatch, not a crash.
		digest = "unreadable: " + err.Error()
	}
	out := statusOut{
		GateID: g.ID, Status: string(g.Status), Type: string(g.Type), Risk: string(g.Risk),
		Feature: g.Feature, RunID: g.RunID, StepID: g.StepID,
		SubjectDigest: g.Subject.Digest, DigestNow: digest, DigestMatch: digest == g.Subject.Digest,
		RequiredAssurance: string(g.RequiredAssurance),
		ExpiresAt:         g.ExpiresAt.Format(time.RFC3339),
	}
	if g.Status == gate.StatusApproved || g.Status == gate.StatusRejected {
		ap, err := e.store.ApprovalForGate(ctx, id)
		if err != nil {
			return err
		}
		out.Approval = &approvalOut{
			ID: ap.ID, Decision: ap.Decision, Handle: ap.Handle, Quote: ap.Quote,
			Assurance: ap.Assurance, Downgraded: ap.Downgraded, Channel: ap.Channel,
			DecidedAt:   ap.DecidedAt.Format(time.RFC3339),
			SignatureOK: e.svc.VerifyApproval(ctx, ap) == nil,
		}
	}
	return json.NewEncoder(a.stdout).Encode(out)
}

// --- lease -------------------------------------------------------------------

// runFile is the part of run.yaml a lease is checked against.
type runFile struct {
	RunID      string `yaml:"run_id"`
	WorkflowID string `yaml:"workflow_id"`
	Feature    string `yaml:"feature"`
	Steps      []struct {
		ID     string `yaml:"id"`
		Kind   string `yaml:"kind"`
		Status string `yaml:"status"`
		// MachineState carries open domain states (verifying, …) that are
		// not STEP_STATUS values, so check_run stays quiet while ProjectRun
		// still sees the independent-verify window (E3.1).
		MachineState string `yaml:"machine_state"`
		Delegated    *struct {
			Agent string `yaml:"agent"`
		} `yaml:"delegated"`
		Group  string   `yaml:"group"`
		Writes []string `yaml:"writes"`
	} `yaml:"steps"`
}

// finished are the recorded statuses that close a step. A FAIL or BLOCKED
// step that carries a delegation is being retried, so it projects as
// delegated rather than as its last outcome.
var finished = map[string]bool{"PASS": true, "SKIPPED": true, "UNPROVEN": true, "AUTO": true}

// projection turns run.yaml into the states the lease service checks.
func (r runFile) projection(risk string) sqlite.ProjectedRun {
	out := sqlite.ProjectedRun{ID: r.RunID, WorkflowID: r.WorkflowID, Feature: r.Feature, Risk: risk}
	for _, st := range r.Steps {
		ps := sqlite.ProjectedStep{ID: st.ID, Kind: st.Kind, State: run.StepPending, Group: st.Group, Writes: append([]string(nil), st.Writes...)}
		switch {
		case st.Status == string(run.StepVerifying) || st.MachineState == string(run.StepVerifying):
			// Independent verification in progress (E5); keep writer for audit.
			ps.State = run.StepVerifying
			if st.Delegated != nil {
				ps.Writer = st.Delegated.Agent
			}
		case st.Delegated != nil && st.Delegated.Agent != "" && !finished[st.Status]:
			ps.State, ps.Writer = run.StepDelegated, st.Delegated.Agent
		case st.Status != "":
			ps.State = run.StepState(st.Status)
		}
		out.Steps = append(out.Steps, ps)
	}
	return out
}

type leaseOut struct {
	LeaseID    string   `json:"lease_id"`
	Token      string   `json:"token,omitempty"`
	Agent      string   `json:"agent"`
	Fencing    uint64   `json:"fencing"`
	WritePaths []string `json:"write_paths"`
	ExpiresAt  string   `json:"expires_at"`
	Outside    []string `json:"outside,omitempty"`
}

func (a app) leaseAcquire(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("lease acquire", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	var paths multi
	runPath := fs.String("run", "", "run.yaml the step belongs to")
	featureID := fs.String("feature-id", "", "the single-writer key; default run.yaml's feature")
	step := fs.String("step", "", "step id")
	agentFlag := fs.String("agent", "", "holder; default the step's delegated writer (override for independent verify)")
	risk := fs.String("risk", "P1", "the ticket's risk tier")
	ttl := fs.Duration("ttl", 2*time.Hour, "how long the lease runs")
	purpose := fs.String("purpose", "write", "what the step will do with it: write or verify")
	ticketDir := fs.String("ticket-dir", "", "repo-relative directory a verify lease is fenced to (I-2)")
	fs.Var(&paths, "write-path", "repo-relative glob the holder may write (repeatable)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *runPath == "" || *step == "" {
		return usageError{"lease acquire needs --run and --step"}
	}
	if *ticketDir != "" && *purpose != string(lease.PurposeVerify) {
		return usageError{"lease acquire: --ticket-dir fences a verify lease (--purpose verify)"}
	}
	raw, err := os.ReadFile(*runPath)
	if err != nil {
		return err
	}
	var rf runFile
	if err := yaml.Unmarshal(raw, &rf); err != nil {
		return fmt.Errorf("%s: %w", *runPath, err)
	}
	if rf.RunID == "" || rf.Feature == "" || rf.Feature == "-" {
		return fmt.Errorf("%s has no run_id or no feature; a lease is keyed by the feature", *runPath)
	}
	if *featureID != "" {
		rf.Feature = *featureID
	}
	agent := strings.TrimSpace(*agentFlag)
	if agent == "" {
		for _, st := range rf.Steps {
			if st.ID == *step && st.Delegated != nil {
				agent = st.Delegated.Agent
			}
		}
	}
	if agent == "" {
		return fmt.Errorf("%s needs a holder: pass --agent, or delegate the step first", *step)
	}

	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	if err := e.store.ProjectRun(ctx, rf.projection(*risk)); err != nil {
		return err
	}
	// Expired leases free their slot only once swept; sweeping here means a
	// holder that died does not block the next delegation until someone
	// remembers to run a sweeper.
	if _, err := e.leases.Sweep(ctx); err != nil {
		return err
	}
	e.leases.TTL = *ttl
	acq := leasesvc.AcquireParams{
		Purpose: lease.Purpose(*purpose), Feature: rf.Feature, RunID: rf.RunID, StepID: *step,
		Agent: agent, WritePaths: paths,
		Actor: ports.Principal{Handle: "workflow.py", Kind: "service"},
	}
	if *ticketDir != "" {
		// I-2: a verify lease stays inside the ticket. With no --write-path
		// the holder gets the whole tree. A fanout shard passes its own
		// paths and must not be widened to the rest of the ticket.
		acq.TicketDir = *ticketDir
		if len(paths) == 0 {
			acq.WritePaths = []string{*ticketDir + "/**"}
		} else {
			acq.WritePaths = append([]string{}, paths...)
		}
	}
	held, err := e.leases.Acquire(ctx, acq)
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(leaseOut{
		LeaseID: held.Lease.ID, Token: held.Token, Agent: held.Lease.Agent, Fencing: held.Lease.Fencing,
		WritePaths: nonNil(held.Lease.WritePaths), ExpiresAt: held.Lease.ExpiresAt.Format(time.RFC3339),
	})
}

func (a app) leaseRelease(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("lease release", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	token := fs.String("token", "", "the token acquire returned")
	id, rest := splitID(args)
	if err := fs.Parse(rest); err != nil {
		return usageError{err.Error()}
	}
	if id == "" || *token == "" {
		return usageError{"lease release needs a lease id and --token"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	return e.leases.Release(ctx, id, *token, ports.Principal{Handle: "workflow.py", Kind: "service"})
}

// leaseCheck reports which of the paths fall outside the lease. It answers;
// the caller decides.
func (a app) leaseCheck(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("lease check", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	var paths multi
	fs.Var(&paths, "path", "a path the holder changed (repeatable)")
	id, rest := splitID(args)
	if err := fs.Parse(rest); err != nil {
		return usageError{err.Error()}
	}
	if id == "" {
		return usageError{"lease check needs a lease id"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	var l lease.Lease
	if err := e.store.InTx(ctx, func(tx ports.Tx) error {
		var err error
		l, err = tx.Leases().Get(ctx, id)
		return err
	}); err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(leaseOut{
		LeaseID: l.ID, Agent: l.Agent, Fencing: l.Fencing, WritePaths: nonNil(l.WritePaths),
		ExpiresAt: l.ExpiresAt.Format(time.RFC3339), Outside: l.Outside(paths),
	})
}

// --- run truth (E2) ----------------------------------------------------------

func (a app) runStart(args []string) error {
	fs := flag.NewFlagSet("run start", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	file := fs.String("file", "", "path to write the exported run.yaml")
	workflow := fs.String("workflow", "", "workflow id")
	feature := fs.String("feature", "", "feature id")
	var steps multi
	fs.Var(&steps, "step", "step as id:kind (repeatable)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *file == "" || *workflow == "" || *feature == "" || len(steps) == 0 {
		return usageError{"run start needs --file, --workflow, --feature and at least one --step id:kind"}
	}
	parsed := make([]run.Step, 0, len(steps))
	for _, raw := range steps {
		id, kind, ok := strings.Cut(raw, ":")
		if !ok || id == "" || kind == "" {
			return usageError{fmt.Sprintf("step %q wants id:kind", raw)}
		}
		parsed = append(parsed, run.Step{ID: id, Kind: kind})
	}
	ctx := context.Background()
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	out, err := e.runs.Start(ctx, runsvc.StartParams{
		WorkflowID: *workflow, FeatureID: *feature, Feature: *feature,
		Steps: parsed,
		Actor: ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "system"},
	})
	if err != nil {
		return err
	}
	existing, _ := os.ReadFile(*file)
	expect, err := runyaml.SHA256Hex(*file)
	if err != nil {
		return err
	}
	if err := runyaml.WriteExport(*file, existing, out, expect); err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]string{
		"run_id": out.ID, "file": *file, "status": string(out.Status()), "truth": "sqlite",
	})
}

func (a app) runApply(args []string) error {
	fs := flag.NewFlagSet("run apply", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	file := fs.String("file", "", "optional run.yaml to re-export after Apply")
	runID := fs.String("run-id", "", "live run id")
	step := fs.String("step", "", "step id")
	event := fs.String("event", "", "domain event kind, e.g. DelegationReturned")
	agent := fs.String("agent", "", "agent handle for return/verify events")
	fencing := fs.Uint64("fencing", 0, "lease fencing token from acquire")
	outcome := fs.String("outcome", "", "PASS|FAIL|… when the event records one")
	evidence := fs.String("evidence", "", "evidence path")
	note := fs.String("note", "", "optional note")
	approval := fs.String("approval-id", "", "recorded approval id for GateApproved / skip")
	by := fs.String("by", "", "human handle for gate events (must match the approval)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *runID == "" || *step == "" || *event == "" {
		return usageError{"run apply needs --run-id, --step and --event"}
	}
	ev := run.Event{
		Kind: run.EventKind(*event), StepID: *step,
		Agent: *agent, Fencing: *fencing, Evidence: *evidence, Note: *note,
		ApprovalID: *approval,
	}
	if *outcome != "" {
		ev.Outcome = run.StepState(*outcome)
	}
	switch ev.Kind {
	case run.EvDelegationReturned, run.EvVerificationRecorded:
		ev.Actor = run.ActorAgent
	case run.EvStepActivated, run.EvLeaseExpired:
		ev.Actor = run.ActorSystem
	case run.EvGateApproved, run.EvGateRejected:
		ev.Actor = run.ActorHuman
	default:
		ev.Actor = run.ActorConductor
	}
	actor := ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "system"}
	if ev.Actor == run.ActorAgent {
		if *agent == "" {
			return usageError{"agent events need --agent"}
		}
		actor = ports.Principal{Handle: *agent, Kind: "agent", OwnerHandle: "system"}
	}
	if ev.Actor == run.ActorHuman {
		handle := strings.TrimSpace(*by)
		if handle == "" {
			return usageError{"gate events need --by <handle> matching the approval"}
		}
		actor = ports.Principal{Handle: handle, Kind: "human"}
	}
	ctx := context.Background()
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	next, err := e.runs.Apply(ctx, *runID, ev, actor)
	if err != nil {
		return err
	}
	if *file != "" {
		raw, _ := os.ReadFile(*file)
		expect, err := runyaml.SHA256Hex(*file)
		if err != nil {
			return err
		}
		if err := runyaml.WriteExport(*file, raw, next, expect); err != nil {
			return err
		}
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"run_id": next.ID, "step": *step, "event": *event,
		"status": string(next.Status()), "truth": "sqlite",
	})
}

func (a app) runRecord(args []string) error {
	fs := flag.NewFlagSet("run record", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	file := fs.String("file", "", "path to the ticket's workflow/run.yaml")
	step := fs.String("step", "", "step id")
	status := fs.String("status", "", "PASS|FAIL|UNPROVEN|SKIPPED|BLOCKED|AUTO")
	evidence := fs.String("evidence", "", "evidence path")
	note := fs.String("note", "", "optional note")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *file == "" || *step == "" || *status == "" {
		return usageError{"run record needs --file, --step and --status"}
	}
	raw, _ := os.ReadFile(*file)
	doc, _ := runyaml.ParseDoc(raw)
	ctx := context.Background()
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	if doc.ID != "" {
		stored, err := e.store.RunStoredStatus(ctx, doc.ID)
		if err != nil {
			return err
		}
		if stored != "" && stored != "external" {
			err := a.applyRecord(ctx, e, *file, raw, doc.ID, *step, *status, *evidence, *note)
			if err == nil {
				return json.NewEncoder(a.stdout).Encode(map[string]string{
					"file": *file, "step": *step, "status": *status, "truth": "sqlite",
				})
			}
			var useYAML *errUseYAML
			if !errors.As(err, &useYAML) {
				return err
			}
			// Agent / gate steps still ride the YAML driver (acceptance: Python
			// path); fall through so record does not refuse mid-migration.
		}
	}
	if err := runyaml.Record(*file, *step, *status, *evidence, *note); err != nil {
		return err
	}
	_ = a.projectYAML(*file, raw) // external projection; YAML remains driver until Start migrates
	return json.NewEncoder(a.stdout).Encode(map[string]string{
		"file": *file, "step": *step, "status": *status, "truth": "yaml",
	})
}

func (a app) applyRecord(
	ctx context.Context, e env, path string, raw []byte,
	runID, stepID, status, evidence, note string,
) error {
	rn, err := e.runs.Get(ctx, runID)
	if err != nil {
		return err
	}
	events, err := conductorRecordEvents(rn, stepID, status, evidence, note)
	if err != nil {
		return err
	}
	actor := ports.Principal{Handle: "conductor@claude", Kind: "agent", OwnerHandle: "system"}
	var next run.Run
	for _, ev := range events {
		next, err = e.runs.Apply(ctx, runID, ev, actor)
		if err != nil {
			return err
		}
	}
	expect, err := runyaml.SHA256Hex(path)
	if err != nil {
		return err
	}
	if err := runyaml.WriteExport(path, raw, next, expect); err != nil {
		return err
	}
	// Audit JSONL beside run.yaml is a projection (design §14). Failure must
	// not undo Apply — the chain in SQLite is already committed (E5.4).
	_ = a.projectAuditJSONL(ctx, e, runID, path)
	return nil
}

// projectAuditJSONL writes workflow/audit-<run_id>.jsonl next to run.yaml.
func (a app) projectAuditJSONL(ctx context.Context, e env, runID, runYAML string) error {
	if runID == "" || runYAML == "" {
		return nil
	}
	dir := filepath.Dir(runYAML)
	out := filepath.Join(dir, "audit-"+runID+".jsonl")
	f, err := os.Create(out)
	if err != nil {
		fmt.Fprintf(a.stderr, "WARN  audit export projection: %v\n", err)
		return nil
	}
	defer f.Close()
	svc := auditsvc.Service{Store: e.store, Clock: local.Clock{}}
	if _, err := svc.Export(ctx, runID, f); err != nil {
		fmt.Fprintf(a.stderr, "WARN  audit export projection: %v\n", err)
		return nil
	}
	return nil
}

// errUseYAML tells runRecord to keep the external YAML mutation path.
type errUseYAML struct{ why string }

func (e *errUseYAML) Error() string { return e.why }

// conductorRecordEvents builds the Apply sequence for a conductor-owned step.
// Agent / gate paths stay on the YAML driver until their event wiring lands.
func conductorRecordEvents(rn run.Run, stepID, status, evidence, note string) ([]run.Event, error) {
	var step *run.Step
	for i := range rn.Steps {
		if rn.Steps[i].ID == stepID {
			step = &rn.Steps[i]
			break
		}
	}
	if step == nil {
		return nil, fmt.Errorf("no step %q in run %s", stepID, rn.ID)
	}
	if step.Executor != run.ByConductor || step.IsGate {
		return nil, &errUseYAML{why: fmt.Sprintf(
			"step %s (%s) still uses the YAML driver", stepID, step.Kind)}
	}
	outcome := run.StepState(status)
	base := run.Event{
		Actor: run.ActorConductor, StepID: stepID,
		Outcome: outcome, Evidence: evidence, Note: note,
	}
	switch step.State {
	case run.StepReady:
		return []run.Event{
			{Kind: run.EvConductorStepStarted, Actor: run.ActorConductor, StepID: stepID},
			{Kind: run.EvConductorStepRecorded, Actor: base.Actor, StepID: stepID,
				Outcome: outcome, Evidence: evidence, Note: note},
		}, nil
	case run.StepConductorActive:
		base.Kind = run.EvConductorStepRecorded
		return []run.Event{base}, nil
	default:
		if note == "" {
			return nil, fmt.Errorf("step %s is %s; amending it needs --note", stepID, step.State)
		}
		base.Kind = run.EvStepAmended
		return []run.Event{base}, nil
	}
}

func (a app) runWrite(args []string) error {
	fs := flag.NewFlagSet("run write", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	file := fs.String("file", "", "path to the ticket's workflow/run.yaml")
	expect := fs.String("expect-sha256", "", "refuse if the on-disk file's sha256 differs")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *file == "" {
		return usageError{"run write needs --file"}
	}
	body, err := io.ReadAll(a.stdin)
	if err != nil {
		return err
	}
	if len(body) == 0 {
		return usageError{"run write needs the new YAML on stdin"}
	}
	// Write refuses unless the file still has --expect-sha256, so these are
	// the bytes it replaces.
	prior, _ := os.ReadFile(*file)
	if err := runyaml.Write(*file, body, *expect); err != nil {
		var stale *runyaml.ErrStale
		if errors.As(err, &stale) {
			return err
		}
		return err
	}
	_ = a.projectYAML(*file, prior)
	sum := sha256Hex(body)
	return json.NewEncoder(a.stdout).Encode(map[string]string{
		"file": *file, "sha256": sum,
	})
}

func sha256Hex(body []byte) string {
	sum := sha256.Sum256(body)
	return fmt.Sprintf("%x", sum)
}

// projectYAML refreshes the SQLite view of a run.yaml that was just written
// over `prior` (empty for a new file).
func (a app) projectYAML(path string, prior []byte) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	doc, err := runyaml.ParseDoc(raw)
	if err != nil || doc.ID == "" || doc.Feature == "" {
		return err
	}
	var prev runyaml.Doc
	if len(prior) > 0 {
		prev, _ = runyaml.ParseDoc(prior)
	}
	ctx := context.Background()
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	steps := make([]sqlite.ProjectedStep, 0, len(doc.Steps))
	for _, st := range doc.Steps {
		steps = append(steps, sqlite.ProjectedStep{
			ID: st.ID, Kind: st.Kind, State: run.StepState(st.State),
			Writer: st.Writer, Group: st.Group, Writes: st.Writes,
		})
	}
	projected := sqlite.ProjectedRun{
		ID: doc.ID, WorkflowID: doc.WorkflowID, Feature: doc.Feature,
		Risk: doc.Risk, Steps: steps,
	}
	// Same SQLite TX as the audit append (phase 1 §6). Live domain runs use
	// Apply + Export; this path keeps the external (YAML-driven) projection.
	events := yamlAuditEvents(ctx, e, path, sha256Hex(raw), len(prior) > 0, prev, doc)
	return e.store.ProjectRunWithAudit(ctx, projected, events...)
}

// yamlAuditEvents says what one run.yaml write did: one event per step whose
// record changed, so the chain can be replayed step by step without the file.
// Each carries the sha256 of the file it was read from.
func yamlAuditEvents(ctx context.Context, e env, path, sum string, existed bool, prev, doc runyaml.Doc) []audit.Event {
	event := func(action audit.Action, step string, detail map[string]any) audit.Event {
		detail["source"], detail["sha256"] = "run.yaml", sum
		return audit.Event{
			At: time.Now().UTC(), Action: action, Actor: audit.Actor{Handle: "idev", Kind: "system"},
			RunID: doc.ID, StepID: step, Feature: doc.Feature, Subject: path, Detail: detail,
		}
	}
	var events []audit.Event
	if !existed {
		events = append(events, event(audit.ActionRunStarted, "",
			map[string]any{"workflow_id": doc.WorkflowID, "steps": len(doc.Steps)}))
	}
	for _, c := range runyaml.StepChanges(prev, doc) {
		s := c.Step
		detail := map[string]any{"kind": s.Kind}
		for key, value := range map[string]string{
			"outcome": s.Status, "from": c.From, "evidence": clip(s.Evidence), "note": clip(s.Note),
			"agent": s.Writer, "lease_id": s.LeaseID, "verified_by": s.VerifiedBy,
			"signed_by": s.SignedBy, "assurance": s.Assurance,
		} {
			if value != "" {
				detail[key] = value
			}
		}
		if s.Auto {
			detail["auto"] = true
		}
		if len(s.Accepted) > 0 {
			detail["accepted_findings"] = s.Accepted
		}
		if s.Writer != "" {
			_ = e.store.InTx(ctx, func(tx ports.Tx) error {
				d, err := tx.Delegations().Latest(ctx, doc.ID, s.ID)
				if err == nil && d.ID != "" {
					detail["delegation_id"] = d.ID
				}
				return nil
			})
		}
		events = append(events, event(stepAction[c.Verb], s.ID, detail))
	}
	if doc.Status != prev.Status {
		switch doc.Status {
		case "done":
			events = append(events, event(audit.ActionRunCompleted, "", map[string]any{"from": prev.Status}))
		case "aborted":
			events = append(events, event(audit.ActionRunAborted, "", map[string]any{"from": prev.Status}))
		}
	}
	return events
}

var stepAction = map[runyaml.Verb]audit.Action{
	runyaml.VerbRecorded: audit.ActionStepRecorded,
	runyaml.VerbAmended:  audit.ActionStepAmended,
	runyaml.VerbSkipped:  audit.ActionStepSkipped,
	runyaml.VerbRetried:  audit.ActionStepRetried,
}

// clip keeps an audit detail readable; the file named by sha256 has the rest.
func clip(s string) string {
	const limit = 240
	if r := []rune(s); len(r) > limit {
		return string(r[:limit]) + "…"
	}
	return s
}

// --- audit -------------------------------------------------------------------

type downgradeWeek struct {
	Week  string `json:"week"`
	Count int    `json:"count"`
}

type downgradesOut struct {
	Total int             `json:"total"`
	Weeks []downgradeWeek `json:"weeks"`
}

// auditExport writes the audit chain as JSONL. Optional --run filters to one
// run. Export is a read: failing to write the file cannot undo committed
// transitions (E5.4).
func (a app) auditExport(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("audit export", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	runID := fs.String("run", "", "only events for this run id")
	format := fs.String("format", "jsonl", "jsonl")
	outPath := fs.String("out", "", "write to this path instead of stdout")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *format != "jsonl" {
		return usageError{"audit export only supports --format jsonl"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	svc := auditsvc.Service{Store: e.store, Clock: local.Clock{}}
	w := a.stdout
	var f *os.File
	if *outPath != "" {
		f, err = os.Create(*outPath)
		if err != nil {
			return err
		}
		defer f.Close()
		w = f
	}
	n, err := svc.Export(ctx, *runID, w)
	if err != nil {
		return err
	}
	if *outPath != "" {
		fmt.Fprintf(a.stderr, "wrote %d events to %s\n", n, *outPath)
	}
	return nil
}

type verifyOut struct {
	AnchoredOn        int64 `json:"anchored_on"`
	From              int64 `json:"from"`
	To                int64 `json:"to"`
	CheckedCheckpoint bool  `json:"checked_checkpoint"`
}

// auditVerify recomputes the chain's hashes and names the first broken seq.
// --from 1 walks from genesis; the default starts after the last checkpoint
// once its signature holds, which is genesis while there is none.
func (a app) auditVerify(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("audit verify", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	from := fs.Int64("from", 0, "1 walks from genesis; 0 starts after the last checkpoint")
	to := fs.Int64("to", 0, "last seq to check (0: the head)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	svc := auditsvc.Service{Store: e.store, Clock: local.Clock{}, Signer: e.svc.Signer}
	res, err := svc.Verify(ctx, *from, *to)
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(verifyOut{
		AnchoredOn: res.AnchoredOn, From: res.From, To: res.To, CheckedCheckpoint: res.CheckedCheckpoint,
	})
}

// auditDowngrades answers one question: how often a high ask was answered at
// low. gatesvc.Decide appends one assurance.downgraded event per downgraded
// approval, so the weekly count is a walk down the chain — a read, and the
// chain is a public record (no gate, no TTY).
func (a app) auditDowngrades(ctx context.Context, args []string) error {
	if len(args) > 0 {
		return usageError{"audit downgrades takes no arguments"}
	}
	e, err := a.open(ctx)
	if err != nil {
		return err
	}
	defer e.store.Close()
	perWeek := map[string]int{}
	const page = 100
	var from int64 = 1
	for {
		var events []audit.Event
		if err := e.store.InTx(ctx, func(tx ports.Tx) error {
			var err error
			events, err = tx.Audit().Range(ctx, from, page)
			return err
		}); err != nil {
			return err
		}
		if len(events) == 0 {
			break
		}
		for _, ev := range events {
			if ev.Action != audit.ActionAssuranceDowngraded {
				continue
			}
			y, w := ev.At.UTC().ISOWeek()
			perWeek[fmt.Sprintf("%04d-W%02d", y, w)]++
		}
		from = events[len(events)-1].Seq + 1
		if len(events) < page {
			break
		}
	}
	weeks := make([]string, 0, len(perWeek))
	for wk := range perWeek {
		weeks = append(weeks, wk)
	}
	sort.Strings(weeks) // "YYYY-Www" sorts as dates
	out := downgradesOut{Weeks: make([]downgradeWeek, 0, len(weeks))}
	for _, wk := range weeks {
		out.Total += perWeek[wk]
		out.Weeks = append(out.Weeks, downgradeWeek{Week: wk, Count: perWeek[wk]})
	}
	return json.NewEncoder(a.stdout).Encode(out)
}

// --- token -------------------------------------------------------------------

func (a app) tokenInit(args []string) error {
	fs := flag.NewFlagSet("token init", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	handle := fs.String("handle", "", "your handle, as listed in people.yaml")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if strings.TrimSpace(*handle) == "" {
		return usageError{"token init needs --handle"}
	}
	if !a.isTTY() {
		return errors.New("the credential is issued to a person at their own terminal, and this is not one")
	}
	if !(signoff.Identity{}).IsHuman(*handle) {
		return fmt.Errorf("%q names an agent or a model, not a person", *handle)
	}
	data, err := local.DataDir()
	if err != nil {
		return err
	}
	path := filepath.Join(data, "secrets", "human.yaml")
	c, err := local.WriteCredential(path, *handle)
	if err != nil {
		return err
	}
	fmt.Fprintf(a.stdout, "credential for %s written to %s (0600)\n", c.Handle, path)
	return nil
}
