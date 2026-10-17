package main

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// The profile fixture below is one line per package on purpose: the parser
// under test is exactly "sum statements per directory", and one line per
// package keeps an arithmetic error from hiding inside a multi-line pile.
const sampleProfile = `mode: atomic
github.com/idev/internal/domain/lease/lease.go:10.2,12.1 3 1
github.com/idev/internal/domain/lease/lease.go:20.2,22.1 2 0
github.com/idev/internal/domain/lease/other.go:1.2,2.1 4 2
github.com/idev/internal/adapters/memstore/memstore.go:1.2,2.1 5 1
github.com/idev/pkg/canonical/canonical.go:1.2,2.1 10 10
github.com/idev/internal/ports/ports.go:55.2,55.20 1 0
`

func TestParseProfileAggregatesByPackage(t *testing.T) {
	covs, err := parseProfile(strings.NewReader(sampleProfile))
	if err != nil {
		t.Fatal(err)
	}
	// lease: three blocks — 3 statements hit, 2 not hit, 4 hit — so
	// 9 total statements and 3+0+4 = 7 hits.
	want := map[string][2]int{
		"github.com/idev/internal/domain/lease":      {9, 7},
		"github.com/idev/internal/adapters/memstore": {5, 5},
		"github.com/idev/pkg/canonical":              {10, 10},
		"github.com/idev/internal/ports":             {1, 0},
	}
	if len(covs) != len(want) {
		t.Fatalf("parseProfile grouped %d packages, want %d: %v", len(covs), len(want), covs)
	}
	for dir, w := range want {
		c, ok := covs[dir]
		if !ok {
			t.Fatalf("%s missing from the parsed profile", dir)
		}
		if c.total != w[0] || c.hits != w[1] {
			t.Errorf("%s: got %d/%d statements, want %d/%d", dir, c.hits, c.total, w[1], w[0])
		}
	}
}

// A block the compiler reports with zero statements (an empty span) must
// move neither tally — otherwise a file with many such spans would look
// better covered than it is.
func TestParseProfileIgnoresZeroStatementBlocks(t *testing.T) {
	const in = `mode: set
x/p.go:1.2,2.1 0 1
x/p.go:3.2,4.1 2 1
`
	covs, err := parseProfile(strings.NewReader(in))
	if err != nil {
		t.Fatal(err)
	}
	c := covs["x"]
	if c.total != 2 || c.hits != 2 {
		t.Errorf("got %d/%d statements, want 2/2: %+v", c.hits, c.total, c)
	}
}

func TestParseProfileRejectsMalformedLines(t *testing.T) {
	for _, in := range []string{
		"not a block at all",
		"x.go:1.2,2.1 three 1", // statement count is not an integer
		"x.go:1.2,2.1 2 -1",    // negative hit count
		"x.go:1.2,2.1 2",       // missing hit count
		"noseparator.go 2 1",   // no colon in the file field
		"mode: set\n",          // mode line alone: no blocks anywhere
	} {
		if _, err := parseProfile(strings.NewReader(in)); err == nil {
			t.Errorf("parseProfile(%q) succeeded, want an error", in)
		}
	}
}

// Both spellings must floor identically: CI passes import-anchored paths
// from go list, a hand-run might paste module-relative ones. The prefix
// traps (internal/domainology) and the tree's own package are the cases
// the old `*/internal/domain/*` case pattern also refused.
func TestFloorForMatchesTreesInBothSpellings(t *testing.T) {
	tests := []struct {
		pkg    string
		floor  int
		exempt bool
	}{
		{"github.com/idev/internal/domain/lease", 90, false},
		{"internal/domain/lease", 90, false},               // module-relative
		{"github.com/idev/internal/domain", 0, false},      // the tree itself, not a subpackage
		{"github.com/idev/internal/domainology", 0, false}, // prefix trap
		{"github.com/idev/pkg/canonical", 90, false},
		{"pkg/canonical", 90, false},
		{"github.com/idev/pkg/canonical/sub", 0, false},
		{"github.com/idev/internal/app/runsvc", 75, false},
		{"github.com/idev/internal/adapters/kindreg", 70, false},
		{"github.com/idev/internal/adapters/memstore", 0, true},
		{"internal/adapters/memstore", 0, true},
		{"github.com/idev/internal/adapters/memstore/extra", 70, false}, // exemption is exact
		{"github.com/idev/internal/adapters/store/storetest", 0, true},
		{"github.com/idev/internal/ports", 0, false},
		{"github.com/idev/tools/covergate", 0, false},
	}
	for _, tc := range tests {
		floor, exempt := floorFor(tc.pkg)
		if floor != tc.floor || exempt != tc.exempt {
			t.Errorf("floorFor(%q) = %d exempt=%v, want %d exempt=%v",
				tc.pkg, floor, exempt, tc.floor, tc.exempt)
		}
	}
}

// The verdict compares the exact ratio, not the number go test prints:
// 8995/10000 renders as 90.0% under %.1f and must still fail a 90 floor,
// while 900/1000 exactly must pass. The old awk compared `$pct < $floor`
// on the same rounded number go test printed, so this case is the one the
// rewrite exists to get right.
func TestJudgeUsesTheExactRatioNotThePrintedPercent(t *testing.T) {
	lease := "github.com/idev/internal/domain/lease"
	for _, tc := range []struct {
		hits, total int
		ok          bool
	}{
		{9, 10, true},
		{900, 1000, true},
		{899, 1000, false},
		{8995, 10000, false}, // prints as 90.0% under %.1f
		{3, 5, false},
	} {
		covs := map[string]pkgCov{lease: {hits: tc.hits, total: tc.total}}
		v := judge(lease, covs)
		if v.floor != 90 {
			t.Fatalf("lease floor = %d, want 90", v.floor)
		}
		if v.ok != tc.ok {
			t.Errorf("judge(%d/%d) ok=%v, want %v", tc.hits, tc.total, v.ok, tc.ok)
		}
	}
}

// Exempt and unfloored packages pass whatever their numbers are; a package
// in scope but absent from the profile fails — "the tests never ran" is
// not a passing grade, and it is the state the old awk could not see.
func TestJudgeExemptUnflooredAndMissing(t *testing.T) {
	covs := map[string]pkgCov{
		"github.com/idev/internal/adapters/memstore": {hits: 1, total: 100},
		"github.com/idev/internal/ports":             {hits: 0, total: 3},
		"github.com/idev/pkg/empty":                  {hits: 0, total: 0},
	}
	for pkg, want := range map[string]bool{
		"github.com/idev/internal/adapters/memstore": true,
		"github.com/idev/internal/ports":             true,
		"github.com/idev/pkg/empty":                  true,
		"github.com/idev/internal/app/runsvc":        false,
	} {
		v := judge(pkg, covs)
		if v.ok != want {
			t.Errorf("judge(%s) ok=%v (missing=%v exempt=%v), want %v",
				pkg, v.ok, v.missing, v.exempt, want)
		}
	}
	if v := judge("github.com/idev/internal/app/runsvc", covs); !v.missing {
		t.Error("a package absent from the profile must be reported missing")
	}
}

func TestSamePkgAcceptsBothSpellings(t *testing.T) {
	tests := []struct {
		dir, pkg string
		want     bool
	}{
		{"github.com/idev/internal/domain/lease", "github.com/idev/internal/domain/lease", true},
		{"internal/domain/lease", "github.com/idev/internal/domain/lease", true},
		{"github.com/idev/internal/domain/lease", "internal/domain/lease", true},
		{"github.com/idev/lease", "github.com/idev/internal/lease", false},
		{"github.com/idev/internal/domain/baseline", "github.com/idev/internal/domain/lease", false},
	}
	for _, tc := range tests {
		if got := samePkg(tc.dir, tc.pkg); got != tc.want {
			t.Errorf("samePkg(%q, %q) = %v, want %v", tc.dir, tc.pkg, got, tc.want)
		}
	}
}

func TestFindCovFallsBackToSuffixMatch(t *testing.T) {
	covs := map[string]pkgCov{"github.com/idev/internal/domain/lease": {hits: 1, total: 2}}
	if c, ok := findCov(covs, "internal/domain/lease"); !ok || c.total != 2 {
		t.Errorf("module-relative lookup: ok=%v cov=%+v, want ok total=2", ok, c)
	}
	if _, ok := findCov(covs, "internal/domain/gate"); ok {
		t.Error("an unrelated package matched the profile")
	}
}

// run without patterns checks every package present in the profile, so the
// end-to-end path — file to verdicts to exit decision — is testable
// without invoking the go tool.
func TestRunWithoutPatterns(t *testing.T) {
	dir := t.TempDir()

	// One package per verdict branch: lease passes its floor exactly
	// (9/10 at 90), runsvc fails (1/10 at 75), memstore is exempt at 20%,
	// ports has no floor. Partial coverage is expressed the way the go
	// cover profile format actually works — a hit block plus an unhit
	// block, not a single block with a fractional count.
	failing := `mode: atomic
github.com/idev/internal/domain/lease/lease.go:1.2,2.1 9 1
github.com/idev/internal/domain/lease/lease.go:3.2,4.1 1 0
github.com/idev/internal/app/runsvc/runsvc.go:1.2,2.1 1 1
github.com/idev/internal/app/runsvc/runsvc.go:3.2,4.1 9 0
github.com/idev/internal/adapters/memstore/memstore.go:1.2,2.1 20 1
github.com/idev/internal/adapters/memstore/memstore.go:3.2,4.1 80 0
github.com/idev/internal/ports/ports.go:1.2,2.1 3 0
`
	failingPath := filepath.Join(dir, "cover.out")
	if err := os.WriteFile(failingPath, []byte(failing), 0o600); err != nil {
		t.Fatal(err)
	}
	var buf bytes.Buffer
	if err := run(failingPath, nil, &buf); err == nil {
		t.Fatalf("run accepted a profile with a package below its floor:\n%s", buf.String())
	}
	out := buf.String()
	for _, want := range []string{
		"ok github.com/idev/internal/domain/lease",
		"FAIL github.com/idev/internal/app/runsvc",
		"floor 75%",
		"exempt github.com/idev/internal/adapters/memstore",
		"ok github.com/idev/internal/ports",
		"no floor",
		"4 package(s) checked, 1 failed",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q:\n%s", want, out)
		}
	}

	green := `mode: set
github.com/idev/pkg/canonical/canonical.go:1.2,2.1 9 1
github.com/idev/pkg/canonical/canonical.go:3.2,4.1 1 0
`
	greenPath := filepath.Join(dir, "cover2.out")
	if err := os.WriteFile(greenPath, []byte(green), 0o600); err != nil {
		t.Fatal(err)
	}
	buf.Reset()
	if err := run(greenPath, nil, &buf); err != nil {
		t.Fatalf("run rejected an all-green profile: %v\n%s", err, buf.String())
	}
	if got := buf.String(); !strings.Contains(got, "ok github.com/idev/pkg/canonical") || !strings.Contains(got, "0 failed") {
		t.Errorf("unexpected output:\n%s", got)
	}
}

// A verdict write that fails must panic rather than return quietly: run
// derives its exit code from the floor math alone, so a swallowed write
// error would hand CI a truncated-but-green verdict. This pins the
// mustPrint contract that main's recover turns into exit 1.
func TestPrintVerdictWriteFailurePanics(t *testing.T) {
	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("printVerdict returned normally against a failing writer")
		}
		if msg := fmt.Sprint(r); !strings.Contains(msg, "write verdict") {
			t.Fatalf("panic value = %v, want it to name the failed write", r)
		}
	}()
	v := verdict{pkg: "internal/domain/lease", hits: 9, total: 10, floor: 90, ok: true}
	printVerdict(failWriter{}, v)
}

// failWriter fails every write, the way a pipe closed by an impatient
// `| head` does.
type failWriter struct{}

func (failWriter) Write([]byte) (int, error) { return 0, errors.New("broken pipe") }

// goList is the one seam that shells out. go test always has the go tool
// on PATH, and from this package's directory `go list ./...` expands to
// exactly this package — a cheap, honest check that arguments flow through
// in the right order and stdout is what we think it is.
func TestGoListExpandsPatternsThroughTheGoTool(t *testing.T) {
	pkgs, err := goList([]string{"./..."})
	if err != nil {
		t.Fatalf("go list ./...: %v", err)
	}
	found := false
	for _, p := range pkgs {
		if p == "github.com/idev/tools/covergate" {
			found = true
		}
	}
	if !found {
		t.Errorf("go list ./... = %v, want github.com/idev/tools/covergate among them", pkgs)
	}
}
