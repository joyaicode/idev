// Package workspace is the local filesystem side of ports.Workspace:
// ticket locate (doc_home), baseline manifest hashing, and git head/diff.
//
// Zero side effects on locate: missing tickets stay missing. Manifest digests
// match ticketbaseline when the ticket only seals baseline.yaml; when
// details[] names readable files those join the manifest (design §11.1).
package workspace

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/idev/internal/adapters/ticketbaseline"
	"github.com/idev/internal/domain/baseline"
	"go.yaml.in/yaml/v3"
)

// Local satisfies ports.Workspace against a developer's checkout.
type Local struct{}

var (
	grillLine     = regexp.MustCompile(`(?m)^convention:\s*grilling\s*$`)
	grillingWord  = regexp.MustCompile(`(?i)\bgrilling\b`)
	homeKeys      = map[string]bool{
		"layout": true, "task": true, "deliver": true, "plan": true,
		"prd": true, "spec": true, "test-case": true, "patrol": true,
	}
)

// LocateTicket resolves a ticket path the way scripts/lib/doc_home.py does.
// key is one of layout|task|deliver|plan|prd|spec|test-case|patrol.
// Returned paths are symlink-resolved when the target exists, so Go and
// Python (Path.resolve) agree on macOS /var → /private/var.
func (Local) LocateTicket(_ context.Context, repoRoot, feature, key string) (string, error) {
	if feature == "" && key != "layout" {
		return "", fmt.Errorf("workspace: --feature is required")
	}
	repo, err := filepath.Abs(repoRoot)
	if err != nil {
		return "", err
	}
	if key == "" {
		key = "task"
	}
	if !homeKeys[key] {
		return "", fmt.Errorf("workspace: unknown key %q", key)
	}
	if key == "layout" && feature == "" {
		if usesProductDocs(repo) {
			return "product", nil
		}
		return "native", nil
	}
	found, err := homes(repo, feature)
	if err != nil {
		return "", err
	}
	if key == "layout" {
		return found["layout"], nil
	}
	return resolveExisting(found[key]), nil
}

func resolveExisting(path string) string {
	if path == "" {
		return path
	}
	if out, err := filepath.EvalSymlinks(path); err == nil {
		return out
	}
	return path
}

// Manifest builds a baseline.Manifest for feature under repoRoot.
// revision 0 reads revision from baseline.yaml. Digests match
// ticketbaseline.FromTicket when no detail files are readable.
func (l Local) Manifest(ctx context.Context, repoRoot, feature string, revision int) (baseline.Manifest, error) {
	ticket, err := l.LocateTicket(ctx, repoRoot, feature, "task")
	if err != nil {
		return baseline.Manifest{}, err
	}
	m, err := FromTicket(feature, ticket, repoRoot, revision, time.Now().UTC())
	if err != nil {
		return baseline.Manifest{}, err
	}
	if head, dirty, herr := l.Head(ctx, repoRoot); herr == nil {
		m.RepoHead = head
		m.Dirty = dirty
	}
	return m, nil
}

// FromTicket hashes baseline.yaml plus readable details[] paths.
// Path "baseline.yaml" is kept so digests stay aligned with ticketbaseline.
// repoRoot may be empty; detail paths are then resolved only under ticketDir.
func FromTicket(feature, ticketDir, repoRoot string, overrideRev int, now time.Time) (baseline.Manifest, error) {
	base, err := ticketbaseline.FromTicket(feature, ticketDir, overrideRev, now)
	if err != nil {
		return baseline.Manifest{}, err
	}
	path := filepath.Join(ticketDir, "baseline.yaml")
	raw, err := os.ReadFile(path)
	if err != nil {
		return baseline.Manifest{}, err
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return baseline.Manifest{}, err
	}
	files := append([]baseline.File(nil), base.Files...)
	for _, rel := range detailPaths(doc["details"]) {
		abs, ok := resolveDetail(ticketDir, repoRoot, rel)
		if !ok {
			continue
		}
		body, err := os.ReadFile(abs)
		if err != nil {
			continue
		}
		entryPath := filepath.ToSlash(rel)
		switch strings.ToLower(filepath.Ext(rel)) {
		case ".yaml", ".yml":
			var nested map[string]any
			if err := yaml.Unmarshal(body, &nested); err != nil {
				files = append(files, baseline.TextFile(entryPath, body))
			} else {
				f, err := baseline.YAMLFile(entryPath, body, nested, nil)
				if err != nil {
					return baseline.Manifest{}, err
				}
				files = append(files, f)
			}
		default:
			files = append(files, baseline.TextFile(entryPath, body))
		}
	}
	if len(files) == len(base.Files) {
		return base, nil
	}
	return baseline.Build(feature, base.Revision, files, base.RepoHead, base.Dirty, now)
}

func resolveDetail(ticketDir, repoRoot, rel string) (string, bool) {
	if filepath.IsAbs(rel) {
		if _, err := os.Stat(rel); err == nil {
			return rel, true
		}
		return "", false
	}
	underTicket := filepath.Join(ticketDir, rel)
	if _, err := os.Stat(underTicket); err == nil {
		return underTicket, true
	}
	if repoRoot == "" {
		repoRoot = GuessRepo(ticketDir)
	}
	if repoRoot != "" {
		underRepo := filepath.Join(repoRoot, rel)
		if _, err := os.Stat(underRepo); err == nil {
			return underRepo, true
		}
	}
	return "", false
}

// GuessRepo walks up from a ticket directory to the checkout root
// (…/docs/task/<f> or …/.idev/task/<f> → repo). Empty when unknown.
func GuessRepo(ticketDir string) string {
	slash := filepath.ToSlash(ticketDir)
	for _, marker := range []string{"/docs/task/", "/.idev/task/"} {
		if i := strings.LastIndex(slash, marker); i >= 0 {
			return filepath.FromSlash(slash[:i])
		}
	}
	return ""
}

// Recompute rehashes exactly the files a sealed manifest named, so verify
// stays aligned with old baseline.yaml-only seals while still covering
// detail files when they were part of the seal (E5.5).
func Recompute(sealed baseline.Manifest, ticketDir, repoRoot string, now time.Time) (baseline.Manifest, error) {
	if sealed.Feature == "" {
		return baseline.Manifest{}, fmt.Errorf("workspace: recompute needs a sealed feature")
	}
	if len(sealed.Files) == 0 {
		return FromTicket(sealed.Feature, ticketDir, repoRoot, sealed.Revision, now)
	}
	if repoRoot == "" {
		repoRoot = GuessRepo(ticketDir)
	}
	files := make([]baseline.File, 0, len(sealed.Files))
	for _, was := range sealed.Files {
		abs, ok := resolveDetail(ticketDir, repoRoot, was.Path)
		if !ok {
			return baseline.Manifest{}, fmt.Errorf("workspace: sealed file %s is missing under %s", was.Path, ticketDir)
		}
		body, err := os.ReadFile(abs)
		if err != nil {
			return baseline.Manifest{}, fmt.Errorf("workspace: reading sealed file %s: %w", was.Path, err)
		}
		switch was.Mode {
		case baseline.ModeYAMLFields:
			var doc map[string]any
			if err := yaml.Unmarshal(body, &doc); err != nil {
				return baseline.Manifest{}, fmt.Errorf("workspace: parsing %s: %w", was.Path, err)
			}
			f, err := baseline.YAMLFile(was.Path, body, doc, was.Fields)
			if err != nil {
				return baseline.Manifest{}, err
			}
			files = append(files, f)
		default:
			files = append(files, baseline.TextFile(was.Path, body))
		}
	}
	return baseline.Build(sealed.Feature, sealed.Revision, files, sealed.RepoHead, sealed.Dirty, now)
}

// ChangedSince lists paths changed since baseRef (git diff --name-only).
func (Local) ChangedSince(_ context.Context, repoRoot, baseRef string) ([]string, error) {
	if baseRef == "" {
		return nil, fmt.Errorf("workspace: base_ref is required")
	}
	out, err := git(repoRoot, "diff", "--name-only", baseRef)
	if err != nil {
		return nil, err
	}
	var paths []string
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimSpace(line)
		if line != "" {
			paths = append(paths, line)
		}
	}
	return paths, nil
}

// Head returns HEAD and whether the worktree is dirty.
func (Local) Head(_ context.Context, repoRoot string) (string, bool, error) {
	commit, err := git(repoRoot, "rev-parse", "HEAD")
	if err != nil {
		return "", false, err
	}
	status, err := git(repoRoot, "status", "--porcelain")
	if err != nil {
		return strings.TrimSpace(commit), false, err
	}
	return strings.TrimSpace(commit), strings.TrimSpace(status) != "", nil
}

// LegacySeal is git's evidence that a ticket was sealed before the store
// took over seals.
type LegacySeal struct {
	Commit      string
	CommittedAt time.Time
}

var sealedLine = regexp.MustCompile(`(?m)^sealed:\s*true\s*$`)

// FindLegacySeal looks for that evidence. The last commit before the cutover
// that touched the ticket's baseline.yaml must have it sealed, and every file
// of the manifest must be in that commit and unchanged since: what gets
// adopted is exactly what was sealed then. files are manifest paths, as
// FromTicket names them.
func FindLegacySeal(ticketDir, repoRoot string, files []string, before time.Time) (LegacySeal, error) {
	out, err := git(ticketDir, "rev-parse", "--show-toplevel")
	if err != nil {
		return LegacySeal{}, fmt.Errorf("workspace: %s is not in a git checkout; a legacy seal is proven by its history", ticketDir)
	}
	top := strings.TrimSpace(out)
	baselineRel, err := relTo(top, filepath.Join(ticketDir, "baseline.yaml"))
	if err != nil {
		return LegacySeal{}, err
	}
	rels := make([]string, 0, len(files))
	for _, f := range files {
		abs, ok := resolveDetail(ticketDir, repoRoot, f)
		if !ok {
			return LegacySeal{}, fmt.Errorf("workspace: %s is missing under %s", f, ticketDir)
		}
		rel, err := relTo(top, abs)
		if err != nil {
			return LegacySeal{}, err
		}
		rels = append(rels, rel)
	}

	out, err = git(top, "log", "-1", "--format=%H%x09%cI",
		"--before="+before.UTC().Format(time.RFC3339), "--", baselineRel)
	if err != nil {
		return LegacySeal{}, err
	}
	commit, at, _ := strings.Cut(strings.TrimSpace(out), "\t")
	if commit == "" {
		return LegacySeal{}, fmt.Errorf("workspace: %s has no commit before %s; seal it through a gate",
			baselineRel, before.UTC().Format(time.RFC3339))
	}
	committed, err := time.Parse(time.RFC3339, at)
	if err != nil {
		return LegacySeal{}, fmt.Errorf("workspace: commit %s has an unreadable date %q", abbrev(commit), at)
	}
	blob, err := git(top, "show", commit+":"+baselineRel)
	if err != nil {
		return LegacySeal{}, err
	}
	if !sealedLine.MatchString(blob) {
		return LegacySeal{}, fmt.Errorf("workspace: at %s %s was not sealed; there is no legacy seal to adopt",
			abbrev(commit), baselineRel)
	}
	for _, rel := range rels {
		if _, err := git(top, "cat-file", "-e", commit+":"+rel); err != nil {
			return LegacySeal{}, fmt.Errorf("workspace: %s was not committed at %s; the legacy seal did not cover it",
				rel, abbrev(commit))
		}
	}
	changed, err := git(top, append([]string{"diff", "--name-only", commit, "--"}, rels...)...)
	if err != nil {
		return LegacySeal{}, err
	}
	if c := strings.Fields(changed); len(c) > 0 {
		return LegacySeal{}, fmt.Errorf("workspace: changed since the legacy seal at %s: %s; reseal it through a gate",
			abbrev(commit), strings.Join(c, ", "))
	}
	return LegacySeal{Commit: commit, CommittedAt: committed}, nil
}

func relTo(top, path string) (string, error) {
	realTop, err := filepath.EvalSymlinks(top)
	if err != nil {
		return "", err
	}
	realPath, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(realTop, realPath)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("workspace: %s is outside the checkout %s", path, top)
	}
	return filepath.ToSlash(rel), nil
}

func abbrev(commit string) string {
	if len(commit) > 12 {
		return commit[:12]
	}
	return commit
}

func git(repo string, args ...string) (string, error) {
	cmd := exec.Command("git", append([]string{"-C", repo}, args...)...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("workspace: git %s: %w (%s)", strings.Join(args, " "), err, strings.TrimSpace(string(out)))
	}
	return string(out), nil
}

func detailPaths(v any) []string {
	switch x := v.(type) {
	case []any:
		var out []string
		for _, item := range x {
			switch s := item.(type) {
			case string:
				if s = strings.TrimSpace(s); s != "" {
					out = append(out, filepath.ToSlash(s))
				}
			}
		}
		return out
	case map[string]any:
		// details: {} or map of id→path — ignore non-string leaves
		var out []string
		for _, item := range x {
			if s, ok := item.(string); ok {
				if s = strings.TrimSpace(s); s != "" {
					out = append(out, filepath.ToSlash(s))
				}
			}
		}
		return out
	default:
		return nil
	}
}

// --- doc_home port -----------------------------------------------------------

func homes(repo, feature string) (map[string]string, error) {
	layout := layoutFor(repo, feature)
	var baseDocs, task string
	if layout == "product" {
		baseDocs = filepath.Join(repo, "docs")
		task = filepath.Join(baseDocs, "task", feature)
	} else {
		baseDocs = filepath.Join(repo, ".idev", "docs")
		task = filepath.Join(repo, ".idev", "task", feature)
	}
	spec, err := specFile(repo, feature, layout)
	if err != nil {
		return nil, err
	}
	return map[string]string{
		"layout":    layout,
		"task":      task,
		"deliver":   filepath.Join(task, "deliver.yaml"),
		"plan":      filepath.Join(task, "verify", "plan.yaml"),
		"prd":       filepath.Join(baseDocs, "prd", feature+".md"),
		"spec":      spec,
		"test-case": filepath.Join(baseDocs, "test-case", feature+".md"),
		"patrol":    filepath.Join(baseDocs, "test-case", feature+"-patrol.yaml"),
	}, nil
}

func layoutFor(repo, feature string) string {
	product := filepath.Join(repo, "docs", "task", feature)
	native := filepath.Join(repo, ".idev", "task", feature)
	productHit := hasTicket(product)
	nativeHit := hasTicket(native)
	if usesProductDocs(repo) {
		if productHit || !nativeHit {
			return "product"
		}
		return "native"
	}
	if productHit {
		return "product"
	}
	return "native"
}

func hasTicket(path string) bool {
	info, err := os.Stat(path)
	if err != nil || !info.IsDir() {
		return false
	}
	for _, name := range []string{"deliver.yaml", "baseline.yaml", "ops.yaml"} {
		if _, err := os.Stat(filepath.Join(path, name)); err == nil {
			return true
		}
	}
	_, err = os.Stat(filepath.Join(path, "verify", "plan.yaml"))
	return err == nil
}

func usesProductDocs(repo string) bool {
	return mattReady(repo) && grillingReady(repo)
}

func slugBlob(repo string) string {
	return readText(filepath.Join(repo, "docs", "agents", "issue-tracker.md")) + "\n" +
		readText(filepath.Join(repo, "AGENTS.md"))
}

func productSpecDir(repo string) string {
	if strings.Contains(slugBlob(repo), "docs/specs/") {
		return "specs"
	}
	return "spec"
}

func mattReady(repo string) bool {
	blob := slugBlob(repo)
	tracker := filepath.Join(repo, "docs", "agents", "issue-tracker.md")
	agents := filepath.Join(repo, "AGENTS.md")
	hasPRD := strings.Contains(blob, "docs/prd/")
	hasSpec := strings.Contains(blob, "docs/spec/") || strings.Contains(blob, "docs/specs/")
	hasTask := strings.Contains(blob, "docs/task/")
	if fileExists(tracker) && (hasPRD || hasSpec || hasTask) {
		return true
	}
	return fileExists(agents) && hasPRD && hasSpec && hasTask
}

func grillingReady(repo string) bool {
	for _, p := range []string{
		filepath.Join(repo, "docs", "agents", "issue-tracker.md"),
		filepath.Join(repo, "AGENTS.md"),
	} {
		if grillingWord.MatchString(readText(p)) {
			return true
		}
	}
	task := filepath.Join(repo, "docs", "task")
	entries, err := os.ReadDir(task)
	if err != nil {
		return false
	}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		g := filepath.Join(task, e.Name(), "grill.md")
		if fileExists(g) && grillLine.MatchString(readText(g)) {
			return true
		}
	}
	return false
}

func specFile(repo, feature, layout string) (string, error) {
	modern, legacy := specPair(repo, feature, layout)
	if fileExists(legacy) && !fileExists(modern) {
		return legacy, nil
	}
	return modern, nil
}

func specPair(repo, feature, layout string) (modern, legacy string) {
	var base, keep string
	if layout == "product" {
		base = filepath.Join(repo, "docs")
		keep = productSpecDir(repo)
	} else {
		base = filepath.Join(repo, ".idev", "docs")
		keep = "spec"
	}
	other := "spec"
	if keep == "spec" {
		other = "specs"
	}
	name := feature + ".md"
	return filepath.Join(base, keep, name), filepath.Join(base, other, name)
}

func readText(path string) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return string(b)
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
