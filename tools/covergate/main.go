// Command covergate enforces per-package statement-coverage floors from a
// coverprofile that go test already wrote.
//
// The CI floor used to be an awk pipeline over `go test -cover` stdout. It
// had two blind spots: it re-ran the whole suite a second time just to
// print percentages, and a package with no test files emits a line whose
// fields the awk could not parse (the package name never lands in $2), so
// an untested package inside a floored tree was invisible. covergate reads
// the profile the race step already wrote, expands the package patterns
// with `go list`, and fails outright when a package in scope is missing
// from the profile: an untested package shows up as 0%, a skipped one as
// FAIL. That missing-package check is what an awk over stdout can never
// give you, and memstore's 20% under a 70-floor tree is what exposed the
// old step.
//
// Floors are per package because a repository-wide average hides exactly
// the package a floor exists for. Ratios are compared exactly
// (hits*100 >= floor*total), not through the one-decimal number go test
// prints: 89.9% must fail a 90 floor, 90.0% exactly must pass it.
//
// Two exemptions, both cases where a floor would be a floor on nothing:
//
//   - adapters/store/storetest is a library *of* tests, run through every
//     store adapter; it has no tests of its own by construction.
//   - adapters/memstore is the fake Store the app and e2e matrix runs
//     against. Per-package attribution cannot see exercise that arrives
//     from other packages' tests (that would take -coverpkg), so a floor
//     here would demand a copy of the app matrix inside the package; its
//     own tests cover the parts only it owns (the A2-6 checkpoint
//     contract).
package main

import (
	"bufio"
	"bytes"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"sort"
	"strconv"
	"strings"
)

func main() {
	// mustPrint panics when a verdict line cannot be written (recovered
	// here): a gate whose verdict printed only halfway must exit red, not
	// let the floor math hand CI a truncated-but-green step.
	defer func() {
		if r := recover(); r != nil {
			fmt.Fprintln(os.Stderr, "covergate:", r)
			os.Exit(1)
		}
	}()
	profile := flag.String("profile", "cover.out", "coverprofile written by `go test -coverprofile`")
	flag.Usage = func() {
		fmt.Fprintln(os.Stderr, "covergate: per-package coverage floors from a coverprofile")
		fmt.Fprintln(os.Stderr)
		fmt.Fprintln(os.Stderr, "usage: go run ./tools/covergate [-profile cover.out] [pattern...]")
		fmt.Fprintln(os.Stderr)
		fmt.Fprintln(os.Stderr, "Patterns are expanded with go list. With no pattern, every package in")
		fmt.Fprintln(os.Stderr, "the profile is checked. A package matched by the patterns but missing from")
		fmt.Fprintln(os.Stderr, "the profile fails outright — coverage numbers only mean something for tests")
		fmt.Fprintln(os.Stderr, "that actually ran.")
		flag.PrintDefaults()
	}
	flag.Parse()

	if err := run(*profile, flag.Args(), os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "covergate:", err)
		os.Exit(1)
	}
}

// run judges every package in the universe — the patterns expanded through
// go list, or (with no patterns) every package present in the profile — and
// prints one verdict line per package.
func run(profilePath string, patterns []string, w io.Writer) error {
	f, err := os.Open(profilePath) // #nosec G304 -- the path is this repo's own coverprofile, named on the -profile flag
	if err != nil {
		return err
	}
	defer func() { _ = f.Close() }() // read-only fd: Close has nothing left to fail on

	covs, err := parseProfile(f)
	if err != nil {
		return fmt.Errorf("parse %s: %w", profilePath, err)
	}

	var universe []string
	if len(patterns) == 0 {
		for dir := range covs {
			universe = append(universe, dir)
		}
		sort.Strings(universe)
	} else if universe, err = goList(patterns); err != nil {
		return err
	}

	failed := 0
	for _, pkg := range universe {
		v := judge(pkg, covs)
		if !v.ok {
			failed++
		}
		printVerdict(w, v)
	}
	mustPrint(w, "covergate: %d package(s) checked, %d failed\n", len(universe), failed)
	if failed > 0 {
		return fmt.Errorf("coverage floors not met: %d of %d package(s) failed", failed, len(universe))
	}
	return nil
}

// pkgCov is the per-package statement tally aggregated from the profile.
type pkgCov struct {
	hits  int // statements executed at least once
	total int // statements in covered files
}

// parseProfile aggregates a coverprofile by package directory. The mode
// line (set/count/atomic — race builds write atomic) is skipped: only the
// block lines matter. A block with zero statements (an empty span the
// compiler still reports) contributes nothing to either tally.
func parseProfile(r io.Reader) (map[string]pkgCov, error) {
	covs := map[string]pkgCov{}
	sc := bufio.NewScanner(r)
	lineNo := 0
	for sc.Scan() {
		lineNo++
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "mode:") {
			continue
		}
		file, stmts, count, ok := splitBlock(line)
		if !ok {
			return nil, fmt.Errorf("line %d: not a coverage block: %q", lineNo, line)
		}
		dir := path.Dir(file)
		c := covs[dir]
		c.total += stmts
		if count > 0 {
			c.hits += stmts
		}
		covs[dir] = c
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if len(covs) == 0 {
		return nil, fmt.Errorf("no coverage blocks found")
	}
	return covs, nil
}

// splitBlock splits one coverprofile block line:
//
//	file.go:startLine.startCol,endLine.endCol numStatements hitCount
//
// Only the file path, statement count, and hit count matter here; the
// position span is not validated beyond the separating colon.
func splitBlock(line string) (file string, stmts, count int, ok bool) {
	fields := strings.Fields(line)
	if len(fields) != 3 {
		return "", 0, 0, false
	}
	colon := strings.LastIndexByte(fields[0], ':')
	if colon < 0 {
		return "", 0, 0, false
	}
	stmts, err := strconv.Atoi(fields[1])
	if err != nil {
		return "", 0, 0, false
	}
	count, err = strconv.Atoi(fields[2])
	if err != nil || stmts < 0 || count < 0 {
		return "", 0, 0, false
	}
	return fields[0][:colon], stmts, count, true
}

// verdict is the judged outcome for one package.
type verdict struct {
	pkg     string
	hits    int
	total   int
	floor   int  // percent; 0 = no floor applies to this package
	exempt  bool // floor waived, see the package doc for why
	missing bool // in scope but absent from the profile
	ok      bool
}

func judge(pkg string, covs map[string]pkgCov) verdict {
	v := verdict{pkg: pkg}
	c, found := findCov(covs, pkg)
	if !found {
		v.missing = true
		return v
	}
	v.hits, v.total = c.hits, c.total
	v.floor, v.exempt = floorFor(pkg)
	switch {
	case v.exempt, v.floor == 0, v.total == 0:
		v.ok = true
	default:
		// Exact ratio, not the rounded percentage go test prints.
		v.ok = v.hits*100 >= v.floor*v.total
	}
	return v
}

// findCov looks a package up in the profile. Profiles normally record
// import-anchored paths (github.com/idev/internal/domain/lease), so an
// exact hit is the common case; the suffix fallback also accepts a
// module-relative profile (internal/domain/lease) or a bare import path.
func findCov(covs map[string]pkgCov, pkg string) (pkgCov, bool) {
	if c, ok := covs[pkg]; ok {
		return c, true
	}
	dirs := make([]string, 0, len(covs))
	for dir := range covs {
		dirs = append(dirs, dir)
	}
	sort.Strings(dirs)
	for _, dir := range dirs {
		if samePkg(dir, pkg) {
			return covs[dir], true
		}
	}
	return pkgCov{}, false
}

// samePkg reports whether a profile directory and an import path from go
// list name the same package, in either import-anchored or
// module-relative spelling.
func samePkg(profileDir, importPath string) bool {
	return profileDir == importPath ||
		strings.HasSuffix(importPath, "/"+profileDir) ||
		strings.HasSuffix(profileDir, "/"+importPath)
}

// floorFor returns the coverage floor for one package and whether the
// package is exempt. Matching is tree-relative so both import-anchored
// (github.com/idev/internal/...) and module-relative (internal/...)
// spellings work; exemption order matters — memstore and storetest sit
// inside the adapters tree their exemption would otherwise be floored by.
func floorFor(pkg string) (floor int, exempt bool) {
	switch {
	case isPkg(pkg, "internal/adapters/store/storetest"):
		return 0, true
	case isPkg(pkg, "internal/adapters/memstore"):
		return 0, true
	case underTree(pkg, "internal/domain"):
		return 90, false
	case isPkg(pkg, "pkg/canonical"):
		return 90, false
	case underTree(pkg, "internal/app"):
		return 75, false
	case underTree(pkg, "internal/adapters"):
		return 70, false
	}
	return 0, false
}

// isPkg reports whether pkg names exactly the given package, in either
// import-anchored or module-relative spelling.
func isPkg(pkg, name string) bool {
	return pkg == name || strings.HasSuffix(pkg, "/"+name)
}

// underTree reports whether pkg is a subpackage inside the given source
// tree. The tree's own package (if one exists at the tree root itself)
// does not match — same semantics as the old `*/internal/domain/*` case.
func underTree(pkg, tree string) bool {
	return strings.HasPrefix(pkg, tree+"/") || strings.Contains(pkg, "/"+tree+"/")
}

// goList expands package patterns through the go tool. It is the one seam
// that reaches outside the process; everything after it is pure data flow.
func goList(patterns []string) ([]string, error) {
	args := append([]string{"list"}, patterns...)
	var out bytes.Buffer
	cmd := exec.Command("go", args...) // #nosec G204 -- patterns come from this repo's CI invocation, not runtime input
	cmd.Stdout = &out
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("go list %s: %w", strings.Join(patterns, " "), err)
	}
	var pkgs []string
	for _, line := range strings.Split(out.String(), "\n") {
		if line = strings.TrimSpace(line); line != "" {
			pkgs = append(pkgs, line)
		}
	}
	if len(pkgs) == 0 {
		return nil, fmt.Errorf("go list %s: no packages matched", strings.Join(patterns, " "))
	}
	sort.Strings(pkgs)
	return pkgs, nil
}

func printVerdict(w io.Writer, v verdict) {
	pct := pctOf(v.hits, v.total)
	switch {
	case v.missing:
		mustPrint(w, "FAIL %s: not in the coverage profile — did its tests run?\n", v.pkg)
	case !v.ok:
		mustPrint(w, "FAIL %s: %.1f%% (%d/%d statements), floor %d%%\n", v.pkg, pct, v.hits, v.total, v.floor)
	case v.exempt:
		mustPrint(w, "exempt %s: %.1f%% (%d/%d statements), floor waived (test double)\n", v.pkg, pct, v.hits, v.total)
	case v.floor == 0:
		mustPrint(w, "ok %s: %.1f%% (%d/%d statements), no floor\n", v.pkg, pct, v.hits, v.total)
	default:
		mustPrint(w, "ok %s: %.1f%% (%d/%d statements), floor %d%%\n", v.pkg, pct, v.hits, v.total, v.floor)
	}
}

// mustPrint writes one verdict line. A write failure panics (recovered by
// main) instead of being swallowed: once the writer has failed, every later
// line would fail the same way, and a verdict whose tail is missing must
// never be able to read as a green step.
func mustPrint(w io.Writer, format string, args ...any) {
	if _, err := fmt.Fprintf(w, format, args...); err != nil {
		panic(fmt.Errorf("write verdict: %w", err))
	}
}

// pctOf is display-only; the pass/fail decision never rounds.
func pctOf(hits, total int) float64 {
	if total == 0 {
		return 100
	}
	return float64(hits) / float64(total) * 100
}
