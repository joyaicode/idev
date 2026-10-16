// Package lease holds the single-writer rule and the path boundary that
// makes it mean something.
//
// Two invariants live here. I-1: at most one write lease per feature at a
// time, so two agents cannot edit the same ticket's code concurrently and
// discover it later in a merge. I-2's other half: a verify lease may only
// write verification artefacts inside the ticket directory — a verifier that
// can edit the code it is verifying is not an independent verifier.
//
// The enforcement that matters is server-side. Client hooks (Cursor's
// preToolUse, Claude Code's PreToolUse) call `idev lease check-path` and are
// useful, but they are advice: a subagent with a shell can write anywhere.
// So the real check is here, applied to the report and to `git diff` before
// a delegation is accepted (design §6.4, check `lease-paths`).
//
// Zero IO: paths are compared as strings. Whether a path exists is the
// workspace adapter's business.
package lease

import (
	"fmt"
	"path"
	"sort"
	"strings"
	"time"
)

// Purpose says what a lease permits.
type Purpose string

// The purposes, from registry/kinds.yaml's `lease` field.
const (
	// PurposeWrite permits changing product code. One per feature.
	PurposeWrite Purpose = "write"
	// PurposeVerify permits writing verification artefacts in the ticket
	// directory, and nothing else.
	PurposeVerify Purpose = "verify"
	// PurposeNone is for steps the conductor performs itself.
	PurposeNone Purpose = "none"
)

// Lease is one grant.
type Lease struct {
	ID      string
	Purpose Purpose
	Feature string
	RunID   string
	StepID  string
	// Agent is the handle the lease was issued to. A report from anyone else
	// is refused.
	Agent string
	// WritePaths are repo-relative glob patterns. `**` crosses directory
	// separators, `*` and `?` do not.
	WritePaths []string
	// Fencing is monotonic per feature. A lease that expired and was
	// re-issued gets a higher token, so a report from the old holder
	// arriving late is detectable rather than merely unlikely.
	Fencing   uint64
	ExpiresAt time.Time
}

// Error is a refused operation, naming the rule.
type Error struct {
	LeaseID string
	Reason  string
	Path    string
}

func (e *Error) Error() string {
	if e.Path != "" {
		return fmt.Sprintf("lease %s: %s: %s", e.LeaseID, e.Reason, e.Path)
	}
	return fmt.Sprintf("lease %s: %s", e.LeaseID, e.Reason)
}

// Normalize puts a path in the form patterns are matched against:
// slash-separated, cleaned, repo-relative.
//
// It refuses what it cannot compare safely rather than guessing. An absolute
// path and a path escaping the repo both mean the caller is talking about
// something outside the lease's frame of reference, and silently clamping
// them is how a boundary check becomes decorative.
func Normalize(p string) (string, error) {
	if p == "" {
		return "", fmt.Errorf("lease: empty path")
	}
	s := strings.ReplaceAll(p, "\\", "/")
	if strings.HasPrefix(s, "/") {
		return "", fmt.Errorf("lease: %q is absolute; paths are repo-relative", p)
	}
	if i := strings.IndexByte(s, 0); i >= 0 {
		return "", fmt.Errorf("lease: %q contains a NUL byte", p)
	}
	s = path.Clean(s)
	if s == ".." || strings.HasPrefix(s, "../") {
		return "", fmt.Errorf("lease: %q escapes the repository", p)
	}
	if s == "." {
		return "", fmt.Errorf("lease: %q is the repository root, not a file", p)
	}
	return s, nil
}

// Match reports whether a pattern covers a path.
//
// Written by hand because path.Match has no `**`, and `**` is what makes a
// lease expressible: "the ticket directory and everything under it" is the
// common case, and spelling it out file by file would mean re-issuing the
// lease every time a verifier writes a new report.
func Match(pattern, target string) bool {
	return matchSegments(strings.Split(pattern, "/"), strings.Split(target, "/"))
}

func matchSegments(pat, tgt []string) bool {
	for len(pat) > 0 {
		if pat[0] == "**" {
			// `**` at the end covers everything below.
			if len(pat) == 1 {
				return true
			}
			// Otherwise try to consume zero or more segments.
			for i := 0; i <= len(tgt); i++ {
				if matchSegments(pat[1:], tgt[i:]) {
					return true
				}
			}
			return false
		}
		if len(tgt) == 0 {
			return false
		}
		if !matchSegment(pat[0], tgt[0]) {
			return false
		}
		pat, tgt = pat[1:], tgt[1:]
	}
	return len(tgt) == 0
}

// matchSegment handles `*` and `?` within one path segment.
func matchSegment(pattern, s string) bool {
	ok, err := path.Match(pattern, s)
	return err == nil && ok
}

// Allows reports whether the lease permits writing `target`.
func (l Lease) Allows(target string) bool {
	norm, err := Normalize(target)
	if err != nil {
		return false
	}
	for _, p := range l.WritePaths {
		np, err := Normalize(p)
		if err != nil {
			continue
		}
		if Match(np, norm) {
			return true
		}
	}
	return false
}

// CheckPath is Allows with a reason, for `idev lease check-path` and the
// client hooks.
func (l Lease) CheckPath(target string) error {
	if _, err := Normalize(target); err != nil {
		return &Error{LeaseID: l.ID, Reason: err.Error(), Path: target}
	}
	if !l.Allows(target) {
		return &Error{
			LeaseID: l.ID,
			Reason:  "outside this lease's write paths",
			Path:    target,
		}
	}
	return nil
}

// Outside returns the paths a lease does not cover, sorted.
//
// This is the `lease-paths` machine check: both the report's CHANGED list
// and `git diff --name-only` go through it, because an agent that under-
// reports what it changed is exactly the case worth catching.
func (l Lease) Outside(paths []string) []string {
	var bad []string
	seen := map[string]bool{}
	for _, p := range paths {
		if p == "" || seen[p] {
			continue
		}
		seen[p] = true
		if !l.Allows(p) {
			bad = append(bad, p)
		}
	}
	sort.Strings(bad)
	return bad
}

// Expired reports whether the lease has run out.
func (l Lease) Expired(now time.Time) bool {
	return !l.ExpiresAt.IsZero() && now.After(l.ExpiresAt)
}

// CheckFencing refuses a report whose token is not the current one.
//
// A late report from a holder whose lease expired carries the old token.
// Without this, that report would be applied on top of whatever the new
// holder did.
func (l Lease) CheckFencing(presented uint64) error {
	if presented != l.Fencing {
		return &Error{
			LeaseID: l.ID,
			Reason: fmt.Sprintf("fencing mismatch: presented %d, current %d; this lease was superseded",
				presented, l.Fencing),
		}
	}
	return nil
}

// CheckHolder refuses a report from an agent the lease was not issued to.
func (l Lease) CheckHolder(agent string) error {
	if agent != l.Agent {
		return &Error{
			LeaseID: l.ID,
			Reason:  fmt.Sprintf("held by %q, not %q", l.Agent, agent),
		}
	}
	return nil
}

// ValidateVerifyPaths enforces that a verify lease cannot reach product code.
//
// `ticketDir` is repo-relative. The rule is from design §6.4: a verify
// lease's write paths must all sit under the ticket directory, because the
// verifier's independence is exactly its inability to change what it is
// checking.
func ValidateVerifyPaths(ticketDir string, paths []string) error {
	dir, err := Normalize(ticketDir)
	if err != nil {
		return fmt.Errorf("lease: ticket directory: %w", err)
	}
	if len(paths) == 0 {
		return &Error{Reason: "a verify lease with no write paths can record nothing"}
	}
	for _, p := range paths {
		np, err := Normalize(p)
		if err != nil {
			return &Error{Reason: err.Error(), Path: p}
		}
		// A pattern is inside the ticket only if every path it can match is.
		if !underDir(dir, np) {
			return &Error{
				Reason: fmt.Sprintf("a verify lease may only write under %s; product code is out of reach", dir),
				Path:   p,
			}
		}
	}
	return nil
}

// underDir reports whether every path `pattern` can match lies under `dir`.
func underDir(dir, pattern string) bool {
	// A wildcard in the directory part could escape, so require a literal
	// prefix equal to dir.
	if pattern == dir {
		return true
	}
	prefix := dir + "/"
	if !strings.HasPrefix(pattern, prefix) {
		return false
	}
	// `..` was already rejected by Normalize, and a `**` after the prefix
	// still stays below it.
	return true
}

// Overlap reports whether two sets of write patterns can both match the same
// path.
//
// Used to decide whether a second write lease on the same repository is
// safe. The answer is conservative: when it cannot be sure, it says yes, so
// the failure mode is a refused lease rather than two agents editing the
// same file.
func Overlap(a, b []string) bool {
	for _, pa := range a {
		na, err := Normalize(pa)
		if err != nil {
			return true // cannot reason about it; assume the worst
		}
		for _, pb := range b {
			nb, err := Normalize(pb)
			if err != nil {
				return true
			}
			if patternsIntersect(na, nb) {
				return true
			}
		}
	}
	return false
}

// patternsIntersect is true when some path matches both patterns.
func patternsIntersect(a, b string) bool {
	if a == b {
		return true
	}
	// A pattern matches the other pattern's literal prefix, or vice versa:
	// enough for the common `dir/**` versus `dir/file.go` case.
	if Match(a, b) || Match(b, a) {
		return true
	}
	// Compare segment by segment; two patterns intersect when no segment
	// pair is provably disjoint.
	return segmentsIntersect(strings.Split(a, "/"), strings.Split(b, "/"))
}

func segmentsIntersect(a, b []string) bool {
	for len(a) > 0 && len(b) > 0 {
		if a[0] == "**" || b[0] == "**" {
			return true // either can absorb whatever follows
		}
		if !segmentOverlaps(a[0], b[0]) {
			return false
		}
		a, b = a[1:], b[1:]
	}
	// One ran out. They intersect only if the other is a `**` tail.
	rest := a
	if len(b) > 0 {
		rest = b
	}
	return len(rest) == 1 && rest[0] == "**"
}

func segmentOverlaps(a, b string) bool {
	if a == b {
		return true
	}
	aWild := strings.ContainsAny(a, "*?")
	bWild := strings.ContainsAny(b, "*?")
	switch {
	case aWild && bWild:
		return true // conservative: two wildcards may well overlap
	case aWild:
		return matchSegment(a, b)
	case bWild:
		return matchSegment(b, a)
	}
	return false
}
