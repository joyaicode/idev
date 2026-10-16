package delegsvc_test

import (
	"context"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/kindreg"
	"github.com/idev/internal/app/delegsvc"
	"github.com/idev/internal/domain/lease"
)

func checker(t *testing.T) delegsvc.Checker {
	t.Helper()
	return delegsvc.Checker{Registry: kindreg.MustLoad()}
}

// A packet and report that pass everything, so each test can break exactly
// one thing. Independent generation would mean most cases fail for a reason
// the test is not about.
func goodPacket() delegsvc.Packet {
	return delegsvc.Packet{
		Kind:       "deliver.code_pass",
		Agent:      "idev-coder",
		Attempt:    1,
		TicketHome: "/repo/.idev/task/demo",
		RepoRoot:   "/repo",
		Stage:      "code",
		MustRead:   []string{"/idev/deliver/SKILL.md"},
		IdevRoot:   "/idev",
	}
}

func goodReport() delegsvc.Report {
	return delegsvc.Report{
		Status:        "PASS",
		Evidence:      []string{".idev/task/demo/review.md"},
		Conclusion:    "零命中,写了具体类型",
		Assumed:       "无",
		Scope:         []string{"src/export.go"},
		Read:          []string{"src/export.go", "src/export_test.go"},
		Changed:       []string{"src/export.go"},
		RevertBaseRef: "a1b2c3d",
		Facts:         []delegsvc.Fact{{Source: "source", Ref: "src/export.go:42"}},
		ChangeKind:    "追加行为",
		CanonTrigger:  "无",
		TableHit:      "零命中",
	}
}

func goodEvidence() delegsvc.Evidence {
	return delegsvc.Evidence{
		GitChanged:     []string{"src/export.go"},
		EvidenceExists: map[string]bool{".idev/task/demo/review.md": true},
		HasLease:       true,
		Lease: lease.Lease{
			ID: "l-1", Purpose: lease.PurposeWrite, Agent: "idev-coder",
			WritePaths: []string{"src/**"}, Fencing: 1,
			ExpiresAt: time.Now().Add(time.Hour),
		},
	}
}

func run(t *testing.T, p delegsvc.Packet, r delegsvc.Report, ev delegsvc.Evidence) delegsvc.Outcome {
	t.Helper()
	return checker(t).Run(context.Background(), p, r, ev)
}

func verdictOf(o delegsvc.Outcome, name string) (delegsvc.Verdict, string, bool) {
	for _, res := range o.Results {
		if res.Name == name {
			return res.Verdict, res.Message, true
		}
	}
	return "", "", false
}

func mustFail(t *testing.T, o delegsvc.Outcome, name string) string {
	t.Helper()
	v, msg, ok := verdictOf(o, name)
	if !ok {
		t.Fatalf("%s did not run", name)
	}
	if v != delegsvc.VerdictFAIL {
		t.Fatalf("%s = %s, want FAIL", name, v)
	}
	// Every failure has to say what to do. These used to answer with a bare
	// "FAIL" and the agent could not tell what it had got wrong.
	if len(msg) < 20 {
		t.Errorf("%s failed with an unhelpful message: %q", name, msg)
	}
	return msg
}

func mustPass(t *testing.T, o delegsvc.Outcome, name string) {
	t.Helper()
	v, _, ok := verdictOf(o, name)
	if !ok {
		t.Fatalf("%s did not run", name)
	}
	if v != delegsvc.VerdictPASS {
		t.Fatalf("%s = %s, want PASS", name, v)
	}
}

func TestACleanReportPassesEverything(t *testing.T) {
	o := run(t, goodPacket(), goodReport(), goodEvidence())
	for _, res := range o.Results {
		if res.Verdict != delegsvc.VerdictPASS {
			t.Errorf("%s = %s: %s", res.Name, res.Verdict, res.Message)
		}
	}
	if len(o.Failed) != 0 || o.Stop {
		t.Errorf("a clean report produced failures: %v", o.Failed)
	}
	if o.ExitCode() != 0 {
		t.Errorf("exit code = %d, want 0", o.ExitCode())
	}
}

func TestEveryCheckRunsOnTheHappyPath(t *testing.T) {
	// A check that silently does not run is worse than one that fails: it
	// reports PASS by omission.
	o := run(t, goodPacket(), goodReport(), goodEvidence())
	want := []string{
		delegsvc.CheckBriefComplete,
		delegsvc.CheckReportParsed,
		delegsvc.CheckEvidence,
		delegsvc.CheckNoSignoffWrite,
		delegsvc.CheckAssumption,
		delegsvc.CheckScopeDeclared,
		delegsvc.CheckScopeHeld,
		delegsvc.CheckReadBefore,
		delegsvc.CheckRevertAnchor,
		delegsvc.CheckFactsFirst,
		delegsvc.CheckS0Declared,
		delegsvc.CheckLeasePaths,
	}
	got := map[string]bool{}
	for _, res := range o.Results {
		got[res.Name] = true
	}
	for _, name := range want {
		if !got[name] {
			t.Errorf("%s did not run for a coder write step", name)
		}
	}
}

// --- one test per check ---------------------------------------------------

func TestBriefCompleteBlamesTheConductor(t *testing.T) {
	p := goodPacket()
	p.Stage = ""
	o := run(t, p, goodReport(), goodEvidence())
	msg := mustFail(t, o, delegsvc.CheckBriefComplete)
	if !strings.Contains(msg, "stage") {
		t.Errorf("the message does not name the missing field: %q", msg)
	}
	// Re-delegating without fixing the brief wastes a round, so the blame
	// has to be explicit.
	for _, res := range o.Results {
		if res.Name == delegsvc.CheckBriefComplete && res.Blame != delegsvc.BlameConductor {
			t.Errorf("blame = %q, want conductor", res.Blame)
		}
	}
}

func TestOpsClassifyNeedsItsArtifact(t *testing.T) {
	p := goodPacket()
	p.Kind = "ops.classify"
	p.Agent = "idev-ops"
	// Classifying a symptom against the wrong build is worse than not
	// classifying it.
	mustFail(t, run(t, p, goodReport(), goodEvidence()), delegsvc.CheckBriefComplete)

	p.Artifact = "/opt/app/app-1.2.3.jar"
	mustPass(t, run(t, p, goodReport(), goodEvidence()), delegsvc.CheckBriefComplete)
}

func TestBoostAgentsNeedIdevRoot(t *testing.T) {
	p := goodPacket()
	p.IdevRoot = ""
	// idev-coder reads convention pages from the kernel, so without a root
	// it cannot do the step at all.
	mustFail(t, run(t, p, goodReport(), goodEvidence()), delegsvc.CheckBriefComplete)

	// A non-boost agent does not need it.
	p.Agent = "idev-deliver"
	p.Kind = "deliver.advance"
	mustPass(t, run(t, p, goodReport(), goodEvidence()), delegsvc.CheckBriefComplete)
}

func TestReportParsedNeedsAStatus(t *testing.T) {
	r := goodReport()
	r.Status = ""
	mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckReportParsed)
}

func TestEvidencePresentIsTheOldestRule(t *testing.T) {
	r := goodReport()
	r.Evidence = nil
	msg := mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckEvidence)
	if !strings.Contains(msg, "打开") {
		t.Errorf("the message should say a PASS must be openable: %q", msg)
	}

	// "-" is the old placeholder for nothing, and counts as nothing.
	r.Evidence = []string{"-"}
	mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckEvidence)

	// A non-PASS needs no evidence.
	r = goodReport()
	r.Status = "BLOCKED(env)"
	r.Evidence = nil
	mustPass(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckEvidence)
}

func TestAMissingEvidenceFileWarnsRatherThanFails(t *testing.T) {
	// The file may be outside the checkout the server can see, so this is
	// worth saying and not worth stopping for.
	ev := goodEvidence()
	ev.EvidenceExists = map[string]bool{".idev/task/demo/review.md": false}
	o := run(t, goodPacket(), goodReport(), ev)
	v, msg, _ := verdictOf(o, delegsvc.CheckEvidence)
	if v != delegsvc.VerdictWARN {
		t.Fatalf("verdict = %s, want WARN", v)
	}
	if !strings.Contains(msg, "review.md") {
		t.Errorf("the warning should name the path: %q", msg)
	}
	if len(o.Failed) != 0 {
		t.Error("a WARN must not count as a failure")
	}
}

func TestNoSignoffWriteStopsTheRun(t *testing.T) {
	r := goodReport()
	r.SignoffWrites = []string{"baseline.sealed"}
	o := run(t, goodPacket(), r, goodEvidence())
	mustFail(t, o, delegsvc.CheckNoSignoffWrite)

	// This is the one check that halts rather than inviting a retry: an
	// agent claiming to have signed is not a retryable mistake.
	if !o.Stop {
		t.Error("a signoff claim must stop the run")
	}
	if o.ExitCode() != 2 {
		t.Errorf("exit code = %d, want 2", o.ExitCode())
	}
}

func TestAssumedMustBeWrittenOut(t *testing.T) {
	r := goodReport()
	r.Assumed = ""
	mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckAssumption)

	// "无" is a real answer.
	r.Assumed = "无"
	mustPass(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckAssumption)
}

func TestScopeMustCoverWhatChanged(t *testing.T) {
	r := goodReport()
	r.Changed = append(r.Changed, "src/unexpected.go")
	r.Read = append(r.Read, "src/unexpected.go")
	msg := mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckScopeHeld)
	if !strings.Contains(msg, "src/unexpected.go") {
		t.Errorf("the message should name the file: %q", msg)
	}
}

func TestChangingAFileNobodyReadIsCaught(t *testing.T) {
	r := goodReport()
	r.Scope = append(r.Scope, "src/blind.go")
	r.Changed = append(r.Changed, "src/blind.go")
	mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckReadBefore)
}

func TestScopeComparisonIsPerFileNotPerSymbol(t *testing.T) {
	// The report format allows `path:symbol`; symbols are for display.
	r := goodReport()
	r.Scope = []string{"src/export.go:ExportUsers"}
	r.Read = []string{"src/export.go:ExportUsers"}
	r.Changed = []string{"src/export.go:writeHeader"}
	o := run(t, goodPacket(), r, goodEvidence())
	mustPass(t, o, delegsvc.CheckScopeHeld)
	mustPass(t, o, delegsvc.CheckReadBefore)
}

func TestRevertAnchorRequiredOnceAnythingChanged(t *testing.T) {
	r := goodReport()
	r.RevertBaseRef = ""
	mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckRevertAnchor)

	// Nothing changed, nothing to revert.
	r.Changed = nil
	ev := goodEvidence()
	ev.GitChanged = nil
	mustPass(t, run(t, goodPacket(), r, ev), delegsvc.CheckRevertAnchor)
}

func TestRedFirstAppliesToFixes(t *testing.T) {
	p := goodPacket()
	p.Kind = "review.fix"
	// A fix with no failing run behind it has not been shown to fix
	// anything.
	mustFail(t, run(t, p, goodReport(), goodEvidence()), delegsvc.CheckRedFirst)

	r := goodReport()
	r.RedFirstLog = "target/verify/red.log"
	mustPass(t, run(t, p, r, goodEvidence()), delegsvc.CheckRedFirst)

	// It does not apply to other kinds.
	if _, _, ok := verdictOf(run(t, goodPacket(), goodReport(), goodEvidence()),
		delegsvc.CheckRedFirst); ok {
		t.Error("red-first ran for a kind it does not apply to")
	}
}

func TestFactsMustBeFirstHand(t *testing.T) {
	r := goodReport()
	// A document is not a first-hand source for the agents that reach a
	// judgement.
	r.Facts = []delegsvc.Fact{{Source: "doc", Ref: "references/agents.md"}}
	mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckFactsFirst)

	// A first-hand source with no location is not one either.
	r.Facts = []delegsvc.Fact{{Source: "source", Ref: ""}}
	mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckFactsFirst)

	for _, src := range []string{"codegraph", "source", "command", "git"} {
		r.Facts = []delegsvc.Fact{{Source: src, Ref: "somewhere:1"}}
		mustPass(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckFactsFirst)
	}
}

func TestFactsDoNotApplyToTheDocumentWriter(t *testing.T) {
	// idev-deliver's output *is* the document, so requiring it to cite one
	// would be circular.
	p := goodPacket()
	p.Agent = "idev-deliver"
	p.Kind = "deliver.advance"
	r := goodReport()
	r.Facts = nil
	if _, _, ok := verdictOf(run(t, p, r, goodEvidence()), delegsvc.CheckFactsFirst); ok {
		t.Error("facts-first ran for idev-deliver")
	}
}

func TestS0AppliesToOneAgent(t *testing.T) {
	r := goodReport()
	r.TableHit = ""
	msg := mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckS0Declared)
	if !strings.Contains(msg, "TABLE_HIT") {
		t.Errorf("the message should name the missing declaration: %q", msg)
	}

	// Not for anyone else.
	p := goodPacket()
	p.Agent = "idev-reviewer"
	p.Kind = "review.report"
	if _, _, ok := verdictOf(run(t, p, goodReport(), goodEvidence()),
		delegsvc.CheckS0Declared); ok {
		t.Error("s0-declared ran for idev-reviewer")
	}
}

// --- the checks that use evidence the server gathered itself -------------

func TestLeasePathsUsesGitNotTheReport(t *testing.T) {
	// The interesting failure is an agent that changed something and did
	// not mention it. The report says one file; git says two.
	ev := goodEvidence()
	ev.GitChanged = []string{"src/export.go", "docs/secret.md"}
	o := run(t, goodPacket(), goodReport(), ev)
	msg := mustFail(t, o, delegsvc.CheckLeasePaths)
	if !strings.Contains(msg, "docs/secret.md") {
		t.Errorf("the message should name the unreported file: %q", msg)
	}
	if !strings.Contains(msg, "git 里有") {
		t.Errorf("the message should say the report omitted it: %q", msg)
	}
}

func TestLeasePathsAlsoChecksTheReportsOwnClaim(t *testing.T) {
	r := goodReport()
	r.Scope = append(r.Scope, "docs/notes.md")
	r.Read = append(r.Read, "docs/notes.md")
	r.Changed = append(r.Changed, "docs/notes.md")
	// Declared honestly, still outside the lease.
	mustFail(t, run(t, goodPacket(), r, goodEvidence()), delegsvc.CheckLeasePaths)
}

func TestLeasePathsSkippedWithoutALease(t *testing.T) {
	ev := goodEvidence()
	ev.HasLease = false
	if _, _, ok := verdictOf(run(t, goodPacket(), goodReport(), ev),
		delegsvc.CheckLeasePaths); ok {
		t.Error("lease-paths ran for a step that takes no lease")
	}
}

func TestBaselineIntactCatchesAMovedBaseline(t *testing.T) {
	p := goodPacket()
	p.BaselineRoot = "sha256:" + strings.Repeat("a", 64)
	ev := goodEvidence()
	ev.BaselineRoot = "sha256:" + strings.Repeat("b", 64)

	msg := mustFail(t, run(t, p, goodReport(), ev), delegsvc.CheckBaselineIntact)
	if !strings.Contains(msg, "旧需求") {
		t.Errorf("the message should say the work was against an old requirement: %q", msg)
	}

	ev.BaselineRoot = p.BaselineRoot
	mustPass(t, run(t, p, goodReport(), ev), delegsvc.CheckBaselineIntact)
}

func TestBaselineIntactSkippedWhenUnsealed(t *testing.T) {
	if _, _, ok := verdictOf(run(t, goodPacket(), goodReport(), goodEvidence()),
		delegsvc.CheckBaselineIntact); ok {
		t.Error("baseline-intact ran with no sealed baseline to compare against")
	}
}

// --- exit codes, which every caller script depends on --------------------

func TestExitCodesMatchTheOldCLI(t *testing.T) {
	clean := run(t, goodPacket(), goodReport(), goodEvidence())
	if clean.ExitCode() != 0 {
		t.Errorf("clean = %d, want 0", clean.ExitCode())
	}

	r := goodReport()
	r.Assumed = ""
	if got := run(t, goodPacket(), r, goodEvidence()).ExitCode(); got != 1 {
		t.Errorf("a FAIL = %d, want 1", got)
	}

	r = goodReport()
	r.SignoffWrites = []string{"sealed"}
	if got := run(t, goodPacket(), r, goodEvidence()).ExitCode(); got != 2 {
		t.Errorf("a STOP = %d, want 2", got)
	}
}

func TestResultsAreInAStableOrder(t *testing.T) {
	// Two runs over the same input must produce the same record, or the
	// stored checks map is not comparable across attempts.
	a := run(t, goodPacket(), goodReport(), goodEvidence())
	b := run(t, goodPacket(), goodReport(), goodEvidence())
	if len(a.Results) != len(b.Results) {
		t.Fatalf("different numbers of results: %d and %d", len(a.Results), len(b.Results))
	}
	for i := range a.Results {
		if a.Results[i].Name != b.Results[i].Name {
			t.Fatalf("order differs at %d: %s and %s", i, a.Results[i].Name, b.Results[i].Name)
		}
	}
}

func TestFailedListIsOrderedAndComplete(t *testing.T) {
	r := goodReport()
	r.Assumed = ""
	r.RevertBaseRef = ""
	o := run(t, goodPacket(), r, goodEvidence())

	want := []string{delegsvc.CheckAssumption, delegsvc.CheckRevertAnchor}
	got := append([]string{}, o.Failed...)
	sort.Strings(got)
	sort.Strings(want)
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("Failed = %v, want %v", o.Failed, want)
	}
}
