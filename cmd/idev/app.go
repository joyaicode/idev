package main

import (
	"bufio"
	"context"
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
	"github.com/idev/internal/adapters/store/sqlite"
	"github.com/idev/internal/app/gatesvc"
	"github.com/idev/internal/app/leasesvc"
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
		fmt.Fprintln(a.stderr, "usage: idev gate request|approve|reject|status ... | idev lease acquire|release|check ... | idev audit downgrades | idev token init --handle H")
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
	case "audit downgrades":
		err = a.auditDowngrades(ctx, args[2:])
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
			Policy: gate.Policy{AllowLowForHigh: true},
		},
		// Kinds 决定每个 step 领什么用途的租约、谁有权验证；不接的话 verify 租约会
		// 发给先到者（delegated 态只绑定 agent）。见 review A1。
		leases: leasesvc.Service{Store: store, Clock: local.Clock{}, IDs: local.IDs{}, Kinds: kindreg.MustLoad()},
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
		}
		if subj.Digest, err = filesDigest(absRoot, subject); err != nil {
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
	if g.Subject.Kind == gate.SubjectArtifactSet || g.Subject.Kind == gate.SubjectBaseline {
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
	if !a.isTTY() {
		return errors.New("an answer comes from a person's own terminal, and this is not one (stdin and stdout must both be a TTY); an agent's shell cannot answer a gate")
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
	a.show(g, digest)

	in := bufio.NewReader(a.stdin)
	fmt.Fprintf(a.stdout, "type the last %d characters of the gate id to answer as %s: ", shortLen, cred.Handle)
	typed, _ := in.ReadString('\n')
	if strings.TrimSpace(typed) != short(g.ID) {
		return errors.New("the short code does not match; nothing was recorded")
	}
	q := strings.TrimSpace(*quote)
	if q == "" {
		fmt.Fprint(a.stdout, "your words, verbatim: ")
		line, _ := in.ReadString('\n')
		q = strings.TrimSpace(line)
	}
	if reject && !signoff.IsReject(q) {
		return errors.New("a rejection's words are 驳回; say why in the chat, where the agent can act on it")
	}
	if !reject && signoff.IsReject(q) {
		return errors.New("these words reject; use `idev gate reject`")
	}

	d, err := e.svc.Decide(ctx, gatesvc.DecisionParams{
		GateID: id, Quote: q, Channel: gatesvc.ChannelLocalTokenTTY,
		RecomputedDigest: digest, Actor: cred.Principal(),
	})
	if err != nil {
		return err
	}
	fmt.Fprintf(a.stdout, "%s %s by %s (approval %s, assurance %s", d.Gate.Status, id, d.Approval.Handle, d.Approval.ID, d.Approval.Assurance)
	if d.Approval.Downgraded {
		fmt.Fprintf(a.stdout, ", downgraded from %s", g.RequiredAssurance)
	}
	fmt.Fprintln(a.stdout, ")")
	return nil
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
		ID        string `yaml:"id"`
		Kind      string `yaml:"kind"`
		Status    string `yaml:"status"`
		Delegated *struct {
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
	agent := ""
	for _, st := range rf.Steps {
		if st.ID == *step && st.Delegated != nil {
			agent = st.Delegated.Agent
		}
	}
	if agent == "" {
		return fmt.Errorf("%s is not delegated in %s; delegate it first", *step, *runPath)
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
		// I-2: the ticket directory fences a verify lease; grant the whole
		// tree so the verifier may append evidence inside it.
		acq.TicketDir = *ticketDir
		acq.WritePaths = append(append([]string{}, paths...), *ticketDir+"/**")
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

// --- audit -------------------------------------------------------------------

type downgradeWeek struct {
	Week  string `json:"week"`
	Count int    `json:"count"`
}

type downgradesOut struct {
	Total int             `json:"total"`
	Weeks []downgradeWeek `json:"weeks"`
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
