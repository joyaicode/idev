// Package delegsvc issues delegations, accepts reports and runs the machine
// checks on them.
//
// The checks are the port of `delegation.run_checks`. Their names are
// deliberately unchanged: they appear in stored records, in the weekly
// audit's counts and in the agent definitions' prose, so renaming one would
// silently break every comparison across the migration boundary.
//
// What they are for is worth stating plainly, because it is easy to read
// them as bureaucracy. Each one is a way a delegation can come back looking
// finished without being finished: a PASS nobody can open, a scope that
// grew during the work, a change with no way back, an agent claiming it
// signed something. The old implementation parsed these out of free text
// with regexes; this one validates a structured report and then checks the
// claims against evidence the server gathers itself — `git diff` rather
// than the agent's own CHANGED list, because the interesting failure is an
// agent that under-reports.
package delegsvc

import (
	"context"
	"fmt"
	"regexp"
	"sort"
	"strings"

	"github.com/idev/internal/domain/lease"
	"github.com/idev/internal/ports"
)

// Verdict is one check's outcome. The three levels are the old ones: PASS,
// WARN (worth saying, not worth stopping for) and FAIL.
type Verdict string

// The verdicts.
const (
	VerdictPASS Verdict = "PASS"
	VerdictWARN Verdict = "WARN"
	VerdictFAIL Verdict = "FAIL"
)

// Result is one check's name, verdict and explanation.
//
// The message is not decoration. These used to answer with a bare "FAIL",
// and an agent could not tell whether it had written the wrong thing or
// done the wrong thing — so every failure here says which, and what to do.
type Result struct {
	Name    string
	Verdict Verdict
	Message string
	// Blame is "agent" or "conductor". brief-complete is the conductor's
	// fault; re-delegating without fixing the brief wastes a round.
	Blame string
}

// Blame values.
const (
	BlameAgent     = "agent"
	BlameConductor = "conductor"
)

// The check names, unchanged from scripts/delegation.py.
//
// These names are not labels, they are identifiers: they sit in stored
// records, in the weekly audit's counts and in the agent definitions'
// prose. Renaming one would silently break every comparison across the
// migration boundary, so where the design document's §6.3 table and the
// Python implementation disagree — and they do, on five of them — the
// implementation wins.
const (
	CheckBriefComplete  = "brief-complete"
	CheckReportParsed   = "report-parsed"
	CheckEvidence       = "evidence-present"
	CheckNoSignoffWrite = "no-signoff-write"
	// scope-declared and scope-held are two checks, not one: whether the
	// scope was stated up front, and whether the work stayed inside it.
	// Collapsing them would lose the distinction between "never said" and
	// "said and exceeded".
	CheckScopeDeclared = "scope-declared"
	CheckScopeHeld     = "scope-held"
	CheckReadBefore    = "read-before-change"
	CheckRevertAnchor  = "revert-anchor"
	CheckRedFirst      = "red-first"
	CheckAssumption    = "assumption-declared"
	CheckAssumedTagged = "assumption-tagged"
	CheckFactsFirst    = "facts-first"
	CheckS0Declared    = "s0-declared"
	// Added by the design (§6.3): the server checks these against evidence
	// it gathered itself rather than against the agent's claims.
	CheckLeasePaths     = "lease-paths"
	CheckBaselineIntact = "baseline-intact"
)

// Packet is the delegation as issued, reduced to what the checks need.
type Packet struct {
	Kind       string
	Agent      string
	Attempt    int
	TicketHome string
	RepoRoot   string
	Stage      string
	MustRead   []string
	IdevRoot   string
	Artifact   string
	// BaselineRoot is the manifest root the work was supposed to be against.
	BaselineRoot string
}

// Report is the agent's structured return.
type Report struct {
	Status        string
	Evidence      []string
	Conclusion    string
	Assumed       string
	Scope         []string
	Read          []string
	Changed       []string
	RevertBaseRef string
	SignoffWrites []string
	Facts         []Fact
	ChangeKind    string
	CanonTrigger  string
	TableHit      string
	RedFirstLog   string
}

// Fact is one first-hand source.
type Fact struct {
	Source string
	Ref    string
}

// Evidence is what the server gathered itself, rather than what the agent
// claimed. The distinction is the point of several checks.
type Evidence struct {
	// GitChanged is `git diff --name-only` against the revert base.
	GitChanged []string
	// EvidenceExists reports, per evidence path, whether the file is there.
	EvidenceExists map[string]bool
	// BaselineRoot is the manifest root recomputed now.
	BaselineRoot string
	// Lease bounds what the agent was allowed to write.
	Lease lease.Lease
	// HasLease is false for steps that take no lease.
	HasLease bool
}

// Outcome bundles the results.
type Outcome struct {
	Results []Result
	// Failed lists the checks that came back FAIL, in run order.
	Failed []string
	// Stop is true when the run must halt rather than retry: an agent
	// claiming to have signed something is not a retryable mistake.
	Stop bool
}

// ExitCode maps an outcome to the old CLI's exit codes, which the golden
// files and every caller script depend on (delegation.py:605-617).
func (o Outcome) ExitCode() int {
	switch {
	case o.Stop:
		return 2
	case len(o.Failed) > 0:
		return 1
	default:
		return 0
	}
}

// briefRequired is BRIEF_REQUIRED from delegation.py, unchanged.
var briefRequired = []string{"ticket_home", "repo", "stage", "must_read"}

// Checker runs the machine checks.
//
// Registry is an interface rather than the concrete registry so this
// package does not import an adapter: cmd decides which one is wired in.
type Checker struct {
	Registry ports.KindRegistry
}

// Run executes every applicable check, in a fixed order so two runs over
// the same input produce the same record.
func (c Checker) Run(_ context.Context, p Packet, r Report, ev Evidence) Outcome {
	var out []Result

	out = append(out, c.briefComplete(p))
	out = append(out, c.reportParsed(r))
	out = append(out, c.evidencePresent(r, ev))
	out = append(out, c.noSignoffWrite(r))
	out = append(out, c.assumptionDeclared(p, r))
	out = append(out, c.assumptionTagged(p, r))
	out = append(out, c.scopeDeclared(r))
	out = append(out, c.scopeHeld(r))
	out = append(out, c.readBeforeChange(r))
	out = append(out, c.revertAnchor(r))
	if res, ok := c.redFirst(p, r); ok {
		out = append(out, res)
	}
	if res, ok := c.factsFirst(p, r); ok {
		out = append(out, res)
	}
	if res, ok := c.s0Declared(p, r); ok {
		out = append(out, res)
	}
	if res, ok := c.leasePaths(r, ev); ok {
		out = append(out, res)
	}
	if res, ok := c.baselineIntact(p, ev); ok {
		out = append(out, res)
	}

	o := Outcome{Results: out}
	for _, res := range out {
		if res.Verdict == VerdictFAIL {
			o.Failed = append(o.Failed, res.Name)
			if res.Name == CheckNoSignoffWrite {
				o.Stop = true
			}
		}
	}
	return o
}

func pass(name string) Result {
	return Result{Name: name, Verdict: VerdictPASS, Message: "PASS"}
}

func fail(name, blame, msg string) Result {
	return Result{Name: name, Verdict: VerdictFAIL, Message: msg, Blame: blame}
}

func warn(name, msg string) Result {
	return Result{Name: name, Verdict: VerdictWARN, Message: msg, Blame: BlameAgent}
}

// briefComplete points at the conductor. An agent that was never told which
// artefact is running can only come back BLOCKED, so failing here saves a
// round instead of spending one.
func (c Checker) briefComplete(p Packet) Result {
	have := map[string]string{
		"ticket_home": p.TicketHome,
		"repo":        p.RepoRoot,
		"stage":       p.Stage,
		"must_read":   strings.Join(p.MustRead, ","),
		"artifact":    p.Artifact,
		"idev_root":   p.IdevRoot,
	}
	required := append([]string{}, briefRequired...)
	if p.Kind == "ops.classify" {
		required = append(required, "artifact")
	}
	if c.Registry != nil && c.Registry.IsBoost(p.Agent) {
		required = append(required, "idev_root")
	}

	var missing []string
	for _, k := range required {
		if strings.TrimSpace(have[k]) == "" {
			missing = append(missing, k)
		}
	}
	if len(missing) == 0 {
		return pass(CheckBriefComplete)
	}
	return fail(CheckBriefComplete, BlameConductor, fmt.Sprintf(
		"委派包缺 %s —— **这是导体的问题,不是执行者的**。格式照抄 "+
			"references/agents.md「委派包(固定格式)」;重派前用 "+
			"`delegation.py replay` 取回上次那份,别凭记忆重组",
		strings.Join(missing, ",")))
}

func (c Checker) reportParsed(r Report) Result {
	if strings.TrimSpace(r.Status) == "" {
		return fail(CheckReportParsed, BlameAgent,
			"回报里找不到 STATUS 行 —— 第一行写 "+
				"`STATUS: PASS|FAIL|UNPROVEN|BLOCKED(brief|env|logic)`。"+
				"没有它,导体无法机读这次委派的结果")
	}
	return pass(CheckReportParsed)
}

// evidencePresent is the oldest rule in the kernel: a PASS has to be
// openable by someone else.
func (c Checker) evidencePresent(r Report, ev Evidence) Result {
	if !strings.HasPrefix(r.Status, "PASS") {
		return pass(CheckEvidence)
	}
	paths := nonEmpty(r.Evidence)
	if len(paths) == 0 {
		return fail(CheckEvidence, BlameAgent,
			"STATUS 是 PASS 却没有 EVIDENCE 路径 —— PASS 要能被别人打开看。"+
				"写产出文件的路径(报告 / 日志 / plan),不是一句话描述")
	}
	// A path that does not resolve is a warning, not a failure: the file may
	// be outside the checkout the server can see.
	var missing []string
	for _, p := range paths {
		if ev.EvidenceExists != nil && !ev.EvidenceExists[p] {
			missing = append(missing, p)
		}
	}
	if len(missing) > 0 {
		return warn(CheckEvidence, fmt.Sprintf(
			"EVIDENCE 指向 %s,但找不到 —— 路径写错了,还是文件没真的产出?",
			strings.Join(missing, ", ")))
	}
	return pass(CheckEvidence)
}

// noSignoffWrite is the one check that stops the run. An agent claiming to
// have signed is not a retryable mistake.
func (c Checker) noSignoffWrite(r Report) Result {
	claims := nonEmpty(r.SignoffWrites)
	if len(claims) == 0 {
		return pass(CheckNoSignoffWrite)
	}
	return fail(CheckNoSignoffWrite, BlameAgent, fmt.Sprintf(
		"回报里出现「%s」—— 签字字段只有导体能写,而且要有人本轮的确认用语。"+
			"你要做的是把事实回报上去,由导体请人签。"+
			"改成陈述(如「已满足 accepted 的条件,待人确认」)",
		truncate(strings.Join(claims, ","), 30)))
}

// assumptionDeclared applies to the agents that reach a judgement. Saying
// "I assumed X" costs one line and saves the conductor re-verifying the
// whole report; writing 无 counts as declaring.
func (c Checker) assumptionDeclared(p Packet, r Report) Result {
	if c.Registry != nil && !c.Registry.IsFacts(p.Agent) {
		return pass(CheckAssumption)
	}
	if strings.TrimSpace(r.Assumed) == "" {
		return fail(CheckAssumption, BlameAgent,
			"没有 ASSUMED —— 「无」也要显式写出来。沉默和「没有假设」不是一回事")
	}
	return pass(CheckAssumption)
}

// The tags on an ASSUMED line, and the values that declare "nothing".
const (
	LoadBearing    = "[承重]"
	NotLoadBearing = "[非承重]"
)

var noneValue = regexp.MustCompile(`(?i)^\s*(?:无|none|-|n/?a|不适用|0)\s*(?:[(（].*)?$`)

// assumptionTagged: every assumption says whether the conclusion rests on
// it, because only a load-bearing one stops the run for a person.
func (c Checker) assumptionTagged(p Packet, r Report) Result {
	if c.Registry != nil && !c.Registry.IsFacts(p.Agent) {
		return pass(CheckAssumedTagged)
	}
	var untagged []string
	for _, line := range strings.Split(r.Assumed, "\n") {
		v := strings.TrimSpace(line)
		if v == "" || noneValue.MatchString(v) ||
			strings.HasPrefix(v, LoadBearing) || strings.HasPrefix(v, NotLoadBearing) {
			continue
		}
		untagged = append(untagged, v)
	}
	if len(untagged) == 0 {
		return pass(CheckAssumedTagged)
	}
	return fail(CheckAssumedTagged, BlameAgent, fmt.Sprintf(
		"ASSUMED 没标 [承重] / [非承重]:%s —— 一行一条,结论依赖它就标 [承重]"+
			"(会停下请人决定),否则标 [非承重]",
		truncate(strings.Join(untagged, ";"), 120)))
}

// scopeDeclared: was the scope stated before the work started.
func (c Checker) scopeDeclared(r Report) Result {
	if len(nonEmpty(r.Scope)) == 0 {
		return fail(CheckScopeDeclared, BlameAgent,
			"没有 SCOPE 行 —— 动手前先写明这轮打算改哪些 file:symbol。"+
				"它和 CHANGED 对照,挡的是「顺手又改了三处」")
	}
	return pass(CheckScopeDeclared)
}

// scopeHeld: did the work stay inside it. This is the one that catches
// scope creep — "while I was in there I also fixed...".
func (c Checker) scopeHeld(r Report) Result {
	if len(nonEmpty(r.Scope)) == 0 {
		// Nothing to compare against. A WARN rather than a FAIL because
		// scope-declared already reported the real problem.
		return warn(CheckScopeHeld, "没有 SCOPE 可对照 —— 先补 SCOPE 行,这项才有意义")
	}
	if len(nonEmpty(r.Changed)) == 0 {
		return pass(CheckScopeHeld)
	}
	outside := notCovered(r.Changed, r.Scope)
	if len(outside) == 0 {
		return pass(CheckScopeHeld)
	}
	return fail(CheckScopeHeld, BlameAgent, fmt.Sprintf(
		"改了 SCOPE 之外的 %s —— 要么把它们写进 SCOPE 并说明为什么本轮必须一起改,"+
			"要么撤掉这部分改动另开一轮。顺手改的那几处,正是别人假设没变的地方",
		strings.Join(outside, ",")))
}

func (c Checker) readBeforeChange(r Report) Result {
	if len(nonEmpty(r.Changed)) == 0 {
		return pass(CheckReadBefore)
	}
	if len(nonEmpty(r.Read)) == 0 {
		return fail(CheckReadBefore, BlameAgent,
			"改了文件却没有 READ 行 —— 列出动手前读过的 file:symbol。"+
				"改一个没读过的地方,多半是按名字猜它在干什么")
	}
	unread := notCovered(r.Changed, r.Read)
	if len(unread) == 0 {
		return pass(CheckReadBefore)
	}
	return fail(CheckReadBefore, BlameAgent, fmt.Sprintf(
		"改了没读过的 %s —— 先读再改,然后把 file:symbol 补进 READ。"+
			"名字和文档都不可信,只有读过那段代码才知道它在干什么",
		strings.Join(unread, ",")))
}

// revertAnchor is a checkpoint, so undoing a delegation is one command.
func (c Checker) revertAnchor(r Report) Result {
	if len(nonEmpty(r.Changed)) == 0 {
		return pass(CheckRevertAnchor)
	}
	if strings.TrimSpace(r.RevertBaseRef) == "" {
		return fail(CheckRevertAnchor, BlameAgent,
			"改了东西却没有 REVERT 锚点 —— 退不回去的改动没法评审。"+
				"给出动手前的 ref")
	}
	return pass(CheckRevertAnchor)
}

// redFirst applies to review.fix: a fix with no failing run behind it has
// not been shown to fix anything.
func (c Checker) redFirst(p Packet, r Report) (Result, bool) {
	if p.Kind != "review.fix" {
		return Result{}, false
	}
	if strings.TrimSpace(r.RedFirstLog) == "" {
		return fail(CheckRedFirst, BlameAgent,
			"review.fix 没有 RED_FIRST —— 先给出失败的那次运行(附日志路径),"+
				"否则无法确认这个修复修的是真问题"), true
	}
	return pass(CheckRedFirst), true
}

// factsFirst applies to the agents that reach a judgement. The document is
// not a first-hand source for the agent that writes documents.
func (c Checker) factsFirst(p Packet, r Report) (Result, bool) {
	if c.Registry == nil || !c.Registry.IsFacts(p.Agent) {
		return Result{}, false
	}
	for _, f := range r.Facts {
		switch f.Source {
		case "codegraph", "source", "command", "git":
			if strings.TrimSpace(f.Ref) != "" {
				return pass(CheckFactsFirst), true
			}
		}
	}
	return fail(CheckFactsFirst, BlameAgent,
		"FACTS 里没有第一手来源 —— 至少一条 codegraph / 源码 / 命令 / git,"+
			"并带上具体位置。「文档里说」对写文档的人是循环论证"), true
}

// s0Declared is coding.md §0, and applies to one agent.
func (c Checker) s0Declared(p Packet, r Report) (Result, bool) {
	if c.Registry == nil || c.Registry.S0Agent() != p.Agent {
		return Result{}, false
	}
	var missing []string
	if strings.TrimSpace(r.ChangeKind) == "" {
		missing = append(missing, "CHANGE_KIND")
	}
	if strings.TrimSpace(r.CanonTrigger) == "" {
		missing = append(missing, "CANON_TRIGGER")
	}
	if strings.TrimSpace(r.TableHit) == "" {
		missing = append(missing, "TABLE_HIT")
	}
	if len(missing) == 0 {
		return pass(CheckS0Declared), true
	}
	return fail(CheckS0Declared, BlameAgent, fmt.Sprintf(
		"§0 交代不全,缺 %s —— conventions/coding.md 第零节三项都要答,"+
			"「无」和「零命中」也要写出来", strings.Join(missing, ","))), true
}

// leasePaths checks the agent's claim against what git actually says. An
// agent that under-reports what it changed is the case worth catching, so
// both lists go through the lease.
func (c Checker) leasePaths(r Report, ev Evidence) (Result, bool) {
	if !ev.HasLease {
		return Result{}, false
	}
	claimed := ev.Lease.Outside(r.Changed)
	actual := ev.Lease.Outside(ev.GitChanged)

	merged := map[string]bool{}
	for _, p := range append(claimed, actual...) {
		merged[p] = true
	}
	if len(merged) == 0 {
		return pass(CheckLeasePaths), true
	}
	outside := make([]string, 0, len(merged))
	for p := range merged {
		outside = append(outside, p)
	}
	sort.Strings(outside)

	hint := ""
	if len(actual) > 0 && len(claimed) == 0 {
		// The sharper case: the report did not mention these at all.
		hint = "(git 里有、回报里没有)"
	}
	return fail(CheckLeasePaths, BlameAgent, fmt.Sprintf(
		"改到了租约之外的文件%s: %s —— 用 revert 锚点退回去,"+
			"需要扩范围就请人批准 lease_extend_paths",
		hint, strings.Join(outside, ", "))), true
}

// baselineIntact catches work done against a baseline that has since moved.
func (c Checker) baselineIntact(p Packet, ev Evidence) (Result, bool) {
	if p.BaselineRoot == "" || ev.BaselineRoot == "" {
		return Result{}, false
	}
	if p.BaselineRoot == ev.BaselineRoot {
		return pass(CheckBaselineIntact), true
	}
	return fail(CheckBaselineIntact, BlameAgent, fmt.Sprintf(
		"基线在这次委派期间变了(委派时 %s,现在 %s) —— "+
			"这次的工作对的是旧需求。重新密封或 reopen 后再派一次",
		short(p.BaselineRoot), short(ev.BaselineRoot))), true
}

// --- helpers --------------------------------------------------------------

func nonEmpty(xs []string) []string {
	out := make([]string, 0, len(xs))
	for _, x := range xs {
		if s := strings.TrimSpace(x); s != "" && s != "-" {
			out = append(out, s)
		}
	}
	return out
}

// notCovered returns the members of `changed` that no entry of `covering`
// accounts for. Comparison is per file: symbols are for display only, which
// is what the design says and what keeps this from guessing.
func notCovered(changed, covering []string) []string {
	have := map[string]bool{}
	for _, c := range nonEmpty(covering) {
		have[filePart(c)] = true
	}
	var out []string
	for _, c := range nonEmpty(changed) {
		if !have[filePart(c)] {
			out = append(out, c)
		}
	}
	sort.Strings(out)
	return out
}

// filePart drops a trailing `:symbol`, which the report format allows.
func filePart(s string) string {
	if i := strings.IndexByte(s, ':'); i > 0 {
		return s[:i]
	}
	return s
}

func truncate(s string, n int) string {
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[:n])
}

func short(digest string) string {
	d := strings.TrimPrefix(digest, "sha256:")
	if len(d) > 12 {
		return d[:12]
	}
	return d
}
