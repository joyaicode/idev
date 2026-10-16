package lease_test

import (
	"errors"
	"strings"
	"testing"
	"time"

	"pgregory.net/rapid"

	"github.com/idev/internal/domain/lease"
)

var now = time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)

func writeLease(paths ...string) lease.Lease {
	return lease.Lease{
		ID: "l1", Purpose: lease.PurposeWrite, Feature: "demo",
		Agent: "idev-coder", WritePaths: paths, Fencing: 7,
		ExpiresAt: now.Add(time.Hour),
	}
}

// --- path normalisation ----------------------------------------------------

func TestNormalizeAcceptsRepoRelativePaths(t *testing.T) {
	cases := map[string]string{
		"a.go":            "a.go",
		"./a.go":          "a.go",
		"dir/a.go":        "dir/a.go",
		"dir//a.go":       "dir/a.go",
		"dir/./a.go":      "dir/a.go",
		"dir/sub/../a.go": "dir/a.go",
		"dir\\a.go":       "dir/a.go",
	}
	for in, want := range cases {
		got, err := lease.Normalize(in)
		if err != nil {
			t.Errorf("Normalize(%q): %v", in, err)
			continue
		}
		if got != want {
			t.Errorf("Normalize(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestNormalizeRefusesWhatItCannotCompare(t *testing.T) {
	// Each of these means the caller is talking about something outside the
	// lease's frame of reference. Clamping them would make the boundary
	// check decorative.
	for _, in := range []string{"", "/etc/passwd", "../outside", "..", ".", "a\x00b"} {
		if got, err := lease.Normalize(in); err == nil {
			t.Errorf("Normalize(%q) = %q, want an error", in, got)
		}
	}
}

func TestNormalizeRefusesEscapeAfterCleaning(t *testing.T) {
	// dir/../.. cleans to ".." — the escape is only visible after cleaning.
	if _, err := lease.Normalize("dir/../../etc"); err == nil {
		t.Error("a path that escapes only after cleaning must be refused")
	}
}

// --- glob matching ---------------------------------------------------------

func TestMatchSingleStarStaysInOneSegment(t *testing.T) {
	if !lease.Match("src/*.go", "src/a.go") {
		t.Error("* should match within a segment")
	}
	if lease.Match("src/*.go", "src/sub/a.go") {
		t.Error("* must not cross a separator")
	}
	if lease.Match("src/*", "src/sub/a.go") {
		t.Error("* must not cross a separator")
	}
}

func TestMatchDoubleStarCrossesSegments(t *testing.T) {
	pattern := "docs/task/demo/**"
	for _, p := range []string{
		"docs/task/demo/review.md",
		"docs/task/demo/verify/plan.yaml",
		"docs/task/demo/verify/out/log.txt",
		// `dir/**` is the subtree *including its root*: a lease over the
		// ticket directory owns the directory too. Writing a directory as a
		// file is not a thing, so this costs nothing and keeps the pattern
		// meaning one thing rather than two.
		"docs/task/demo",
	} {
		if !lease.Match(pattern, p) {
			t.Errorf("%q should match %q", pattern, p)
		}
	}
	for _, p := range []string{
		"docs/task/other/x.md",
		"docs/task/demoX/review.md", // a sibling sharing a name prefix
		"docs/task",                 // the parent
		"src/a.go",
	} {
		if lease.Match(pattern, p) {
			t.Errorf("%q should not match %q", pattern, p)
		}
	}
}

func TestMatchDoubleStarInTheMiddle(t *testing.T) {
	if !lease.Match("src/**/a.go", "src/a.go") {
		t.Error("** should match zero segments")
	}
	if !lease.Match("src/**/a.go", "src/x/y/a.go") {
		t.Error("** should match several segments")
	}
	if lease.Match("src/**/a.go", "src/x/b.go") {
		t.Error("the trailing literal must still match")
	}
}

func TestMatchQuestionMark(t *testing.T) {
	if !lease.Match("a?.go", "ab.go") {
		t.Error("? should match one character")
	}
	if lease.Match("a?.go", "abc.go") {
		t.Error("? should match exactly one character")
	}
}

func TestMatchExactPath(t *testing.T) {
	if !lease.Match("go.mod", "go.mod") {
		t.Error("an exact pattern should match itself")
	}
	if lease.Match("go.mod", "go.sum") {
		t.Error("an exact pattern should match nothing else")
	}
}

// --- what a lease allows ---------------------------------------------------

func TestAllowsAndCheckPath(t *testing.T) {
	l := writeLease("src/**", "go.mod")

	for _, p := range []string{"src/a.go", "src/deep/b.go", "go.mod"} {
		if !l.Allows(p) {
			t.Errorf("Allows(%q) = false", p)
		}
		if err := l.CheckPath(p); err != nil {
			t.Errorf("CheckPath(%q): %v", p, err)
		}
	}
	for _, p := range []string{"go.sum", "docs/x.md", "/etc/passwd", "../x"} {
		if l.Allows(p) {
			t.Errorf("Allows(%q) = true", p)
		}
		err := l.CheckPath(p)
		if err == nil {
			t.Errorf("CheckPath(%q) allowed it", p)
			continue
		}
		var le *lease.Error
		if !errors.As(err, &le) {
			t.Errorf("CheckPath(%q) error type = %T", p, err)
			continue
		}
		if le.Path == "" || le.Reason == "" {
			t.Errorf("CheckPath(%q) refusal lacks context: %+v", p, le)
		}
	}
}

func TestAllowsIgnoresUnusablePatterns(t *testing.T) {
	// A lease with one bad pattern still honours the good ones rather than
	// failing open or failing shut on everything.
	l := writeLease("/absolute/bad", "src/**")
	if !l.Allows("src/a.go") {
		t.Error("a usable pattern stopped working because another was bad")
	}
	if l.Allows("absolute/bad") {
		t.Error("an unusable pattern was honoured")
	}
}

func TestOutsideReportsEveryViolationSortedAndDeduped(t *testing.T) {
	l := writeLease("src/**")
	got := l.Outside([]string{
		"src/a.go", "docs/b.md", "", "go.mod", "docs/b.md", "src/deep/c.go",
	})
	want := []string{"docs/b.md", "go.mod"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("Outside = %v, want %v", got, want)
	}
}

func TestOutsideIsEmptyWhenEverythingIsCovered(t *testing.T) {
	l := writeLease("src/**", "go.mod")
	if got := l.Outside([]string{"src/a.go", "go.mod"}); len(got) != 0 {
		t.Errorf("Outside = %v, want none", got)
	}
}

// --- fencing, holder, expiry ----------------------------------------------

func TestFencingRefusesASupersededToken(t *testing.T) {
	l := writeLease("src/**")
	if err := l.CheckFencing(7); err != nil {
		t.Errorf("the current token must be accepted: %v", err)
	}
	// A report from the previous holder, arriving after the lease was
	// re-issued, carries the old token.
	err := l.CheckFencing(6)
	if err == nil {
		t.Fatal("a stale fencing token was accepted; a late report would overwrite the new holder")
	}
	if !strings.Contains(err.Error(), "superseded") {
		t.Errorf("error = %q, should say the lease was superseded", err)
	}
	if l.CheckFencing(8) == nil {
		t.Error("a token from the future was accepted")
	}
}

func TestHolderIsChecked(t *testing.T) {
	l := writeLease("src/**")
	if err := l.CheckHolder("idev-coder"); err != nil {
		t.Errorf("the holder must be accepted: %v", err)
	}
	if err := l.CheckHolder("idev-verifier"); err == nil {
		t.Error("a report from a different agent was accepted")
	}
}

func TestExpiry(t *testing.T) {
	l := writeLease("src/**")
	if l.Expired(now) {
		t.Error("a live lease reported as expired")
	}
	if !l.Expired(l.ExpiresAt.Add(time.Second)) {
		t.Error("an expired lease reported as live")
	}
	// A lease with no expiry never expires: used for conductor steps.
	forever := l
	forever.ExpiresAt = time.Time{}
	if forever.Expired(now.Add(10000 * time.Hour)) {
		t.Error("a lease with no expiry must not expire")
	}
}

// --- the verifier's boundary ----------------------------------------------

func TestVerifyLeaseCannotReachProductCode(t *testing.T) {
	ticket := "docs/task/demo"

	ok := []string{
		"docs/task/demo/review.md",
		"docs/task/demo/verify/plan.yaml",
		"docs/task/demo/**",
		"docs/task/demo",
	}
	if err := lease.ValidateVerifyPaths(ticket, ok); err != nil {
		t.Errorf("ticket artefacts must be allowed: %v", err)
	}

	// Each of these would let a verifier change what it is verifying.
	bad := [][]string{
		{"src/**"},
		{"docs/task/demo/review.md", "src/a.go"},
		{"docs/task/**"},
		{"docs/**"},
		{"**"},
		{"docs/task/demo-other/x.md"},
		{"/etc/passwd"},
		{"../elsewhere/x.md"},
	}
	for _, paths := range bad {
		if err := lease.ValidateVerifyPaths(ticket, paths); err == nil {
			t.Errorf("ValidateVerifyPaths accepted %v", paths)
		}
	}
}

func TestVerifyLeaseNeedsSomewhereToWrite(t *testing.T) {
	if err := lease.ValidateVerifyPaths("docs/task/demo", nil); err == nil {
		t.Error("a verify lease with no paths can record nothing and must be refused")
	}
}

func TestValidateVerifyPathsRefusesABadTicketDir(t *testing.T) {
	if err := lease.ValidateVerifyPaths("/abs/ticket", []string{"/abs/ticket/x"}); err == nil {
		t.Error("an absolute ticket directory must be refused")
	}
}

func TestPrefixSiblingIsNotInside(t *testing.T) {
	// "docs/task/demo-other" starts with "docs/task/demo" as a string but is
	// a different directory. A naive prefix check would let a verifier into
	// another ticket.
	if err := lease.ValidateVerifyPaths("docs/task/demo", []string{"docs/task/demoX/x.md"}); err == nil {
		t.Error("a sibling directory sharing a name prefix was treated as inside")
	}
}

// --- single writer --------------------------------------------------------

func TestOverlapDetectsConflictingWriteSets(t *testing.T) {
	cases := []struct {
		a, b []string
		want bool
	}{
		{[]string{"src/**"}, []string{"src/a.go"}, true},
		{[]string{"src/a.go"}, []string{"src/a.go"}, true},
		{[]string{"src/**"}, []string{"docs/**"}, false},
		{[]string{"src/a.go"}, []string{"src/b.go"}, false},
		{[]string{"src/*.go"}, []string{"src/a.go"}, true},
		{[]string{"**"}, []string{"anything/at/all.go"}, true},
		{[]string{"a/**"}, []string{"a/b/c.go"}, true},
		{[]string{"a/b/**"}, []string{"a/c/**"}, false},
		{[]string{"docs/task/demo/**"}, []string{"docs/task/other/**"}, false},
	}
	for _, tc := range cases {
		if got := lease.Overlap(tc.a, tc.b); got != tc.want {
			t.Errorf("Overlap(%v, %v) = %v, want %v", tc.a, tc.b, got, tc.want)
		}
	}
}

func TestOverlapIsSymmetric(t *testing.T) {
	pairs := [][2][]string{
		{{"src/**"}, {"src/a.go"}},
		{{"src/**"}, {"docs/**"}},
		{{"a/*.go"}, {"a/b.go"}},
	}
	for _, p := range pairs {
		if lease.Overlap(p[0], p[1]) != lease.Overlap(p[1], p[0]) {
			t.Errorf("Overlap is asymmetric for %v and %v", p[0], p[1])
		}
	}
}

func TestOverlapAssumesTheWorstOnUnusablePatterns(t *testing.T) {
	// Refusing a lease is recoverable; two agents writing the same file is
	// not, so an uninterpretable pattern counts as overlapping.
	if !lease.Overlap([]string{"/absolute"}, []string{"src/a.go"}) {
		t.Error("an unusable pattern must be treated as overlapping")
	}
	if !lease.Overlap([]string{"src/a.go"}, []string{".."}) {
		t.Error("an unusable pattern must be treated as overlapping")
	}
}

// --- properties -----------------------------------------------------------

// Normalisation is idempotent, and a normalised path never escapes.
func TestPropertyNormalizeIsIdempotent(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		raw := rapid.String().Draw(t, "path")
		once, err := lease.Normalize(raw)
		if err != nil {
			return
		}
		twice, err := lease.Normalize(once)
		if err != nil {
			t.Fatalf("Normalize(%q) = %q, which then failed: %v", raw, once, err)
		}
		if once != twice {
			t.Fatalf("not idempotent: %q -> %q -> %q", raw, once, twice)
		}
		if strings.HasPrefix(once, "/") || once == ".." || strings.HasPrefix(once, "../") {
			t.Fatalf("Normalize produced an escaping path: %q", once)
		}
	})
}

// A verify lease validated against a ticket directory can never allow a path
// outside it. This is invariant I-2's other half, and it has to hold for any
// pattern someone can write.
func TestPropertyVerifyLeaseNeverEscapesTheTicket(t *testing.T) {
	ticket := "docs/task/demo"
	outside := []string{
		"src/a.go", "go.mod", "docs/task/other/x.md", "docs/task/demoX/x.md",
		"docs/x.md", "a.go", "docs/task/x.md",
	}
	rapid.Check(t, func(t *rapid.T) {
		pattern := rapid.SampledFrom([]string{
			"docs/task/demo/**", "docs/task/demo/review.md", "docs/task/demo",
			"docs/task/demo/verify/**", "docs/task/**", "docs/**", "**",
			"src/**", "docs/task/demo*/**", "docs/task/*/x.md",
		}).Draw(t, "pattern")

		if err := lease.ValidateVerifyPaths(ticket, []string{pattern}); err != nil {
			return // refused, which is the safe answer
		}
		// Accepted: it must not reach anything outside the ticket.
		l := lease.Lease{
			ID: "v", Purpose: lease.PurposeVerify, WritePaths: []string{pattern},
		}
		for _, p := range outside {
			if l.Allows(p) {
				t.Fatalf("verify pattern %q was accepted but reaches %q", pattern, p)
			}
		}
	})
}

// Whatever the lease, Outside and Allows agree.
func TestPropertyOutsideAgreesWithAllows(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		patterns := rapid.SliceOfN(rapid.SampledFrom([]string{
			"src/**", "src/*.go", "go.mod", "docs/task/demo/**", "**",
		}), 1, 3).Draw(t, "patterns")
		l := writeLease(patterns...)

		candidates := rapid.SliceOfN(rapid.SampledFrom([]string{
			"src/a.go", "src/deep/b.go", "go.mod", "go.sum",
			"docs/task/demo/review.md", "docs/other.md",
		}), 0, 6).Draw(t, "paths")

		bad := map[string]bool{}
		for _, p := range l.Outside(candidates) {
			bad[p] = true
		}
		for _, p := range candidates {
			if l.Allows(p) == bad[p] {
				t.Fatalf("Allows(%q)=%v but Outside says %v (patterns %v)",
					p, l.Allows(p), bad[p], patterns)
			}
		}
	})
}
