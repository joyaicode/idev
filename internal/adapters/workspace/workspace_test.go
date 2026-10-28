package workspace_test

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/adapters/ticketbaseline"
	"github.com/idev/internal/adapters/workspace"
)

func TestLocateTicketNativeLayout(t *testing.T) {
	repo := t.TempDir()
	feat := "demo"
	task := filepath.Join(repo, ".idev", "task", feat)
	must(t, os.MkdirAll(task, 0o755))
	must(t, os.WriteFile(filepath.Join(task, "baseline.yaml"), []byte("revision: 1\n"), 0o644))

	got, err := workspace.Local{}.LocateTicket(context.Background(), repo, feat, "task")
	if err != nil {
		t.Fatal(err)
	}
	if got != mustResolve(t, task) {
		t.Fatalf("task = %s, want %s", got, task)
	}
	layout, err := workspace.Local{}.LocateTicket(context.Background(), repo, feat, "layout")
	if err != nil {
		t.Fatal(err)
	}
	if layout != "native" {
		t.Fatalf("layout = %s, want native", layout)
	}
}

func TestLocateTicketMatchesDocHomePython(t *testing.T) {
	repo := t.TempDir()
	feat := "parity"
	task := filepath.Join(repo, ".idev", "task", feat)
	must(t, os.MkdirAll(task, 0o755))
	must(t, os.WriteFile(filepath.Join(task, "deliver.yaml"), []byte("stage: req\n"), 0o644))

	goPath, err := workspace.Local{}.LocateTicket(context.Background(), repo, feat, "task")
	if err != nil {
		t.Fatal(err)
	}
	py := runDocHome(t, repo, feat, "task")
	goPath = mustResolve(t, goPath)
	py = mustResolve(t, py)
	if goPath != py {
		t.Fatalf("LocateTicket %q != doc_home.py %q", goPath, py)
	}
}

func TestManifestMatchesTicketbaselineWhenNoDetails(t *testing.T) {
	dir := t.TempDir()
	body := "revision: 1\ngoal: same\nnon_goal: x\nitems: []\nboundaries: []\ndetails: {}\n"
	must(t, os.WriteFile(filepath.Join(dir, "baseline.yaml"), []byte(body), 0o644))
	at := time.Date(2026, 10, 28, 0, 0, 0, 0, time.UTC)
	thin, err := ticketbaseline.FromTicket("demo", dir, 0, at)
	if err != nil {
		t.Fatal(err)
	}
	full, err := workspace.FromTicket("demo", dir, "", 0, at)
	if err != nil {
		t.Fatal(err)
	}
	if thin.ManifestRoot != full.ManifestRoot {
		t.Fatalf("roots differ: thin=%s full=%s", thin.ManifestRoot, full.ManifestRoot)
	}
}

func TestManifestRootMatchesPython(t *testing.T) {
	repo := t.TempDir()
	feat := "py-parity"
	task := filepath.Join(repo, ".idev", "task", feat)
	must(t, os.MkdirAll(task, 0o755))
	specDir := filepath.Join(repo, ".idev", "docs", "spec")
	must(t, os.MkdirAll(specDir, 0o755))
	must(t, os.WriteFile(filepath.Join(specDir, feat+".md"), []byte("# Hello\n\nworld\n"), 0o644))
	body := "revision: 1\ngoal: g\nnon_goal: n\nitems: []\nboundaries: []\n" +
		"details:\n  - .idev/docs/spec/" + feat + ".md\n"
	must(t, os.WriteFile(filepath.Join(task, "baseline.yaml"), []byte(body), 0o644))
	at := time.Date(2026, 10, 28, 12, 0, 0, 0, time.UTC)
	m, err := workspace.FromTicket(feat, task, repo, 0, at)
	if err != nil {
		t.Fatal(err)
	}
	py := runPythonManifest(t, task, repo)
	if string(m.ManifestRoot) != py {
		t.Fatalf("Go %s != Python %s", m.ManifestRoot, py)
	}
}

func TestRecomputeKeepsBaselineOnlySealIntact(t *testing.T) {
	dir := t.TempDir()
	body := "revision: 1\ngoal: same\nnon_goal: x\nitems: []\nboundaries: []\ndetails:\n  - missing.md\n"
	must(t, os.WriteFile(filepath.Join(dir, "baseline.yaml"), []byte(body), 0o644))
	at := time.Date(2026, 10, 28, 0, 0, 0, 0, time.UTC)
	// Old seal shape: only baseline.yaml in the file set.
	sealed, err := ticketbaseline.FromTicket("demo", dir, 0, at)
	if err != nil {
		t.Fatal(err)
	}
	current, err := workspace.Recompute(sealed, dir, "", at)
	if err != nil {
		t.Fatal(err)
	}
	if current.ManifestRoot != sealed.ManifestRoot {
		t.Fatalf("recompute drifted a baseline-only seal: %s vs %s", current.ManifestRoot, sealed.ManifestRoot)
	}
}

func TestManifestIncludesDetailFiles(t *testing.T) {
	repo := t.TempDir()
	feat := "with-details"
	task := filepath.Join(repo, ".idev", "task", feat)
	must(t, os.MkdirAll(task, 0o755))
	spec := filepath.Join(repo, ".idev", "docs", "spec")
	must(t, os.MkdirAll(spec, 0o755))
	must(t, os.WriteFile(filepath.Join(spec, feat+".md"), []byte("# Spec\n\nbody\n"), 0o644))
	body := "revision: 1\ngoal: g\nnon_goal: n\nitems: []\nboundaries: []\n" +
		"details:\n  - .idev/docs/spec/" + feat + ".md\n"
	must(t, os.WriteFile(filepath.Join(task, "baseline.yaml"), []byte(body), 0o644))
	at := time.Date(2026, 10, 28, 0, 0, 0, 0, time.UTC)

	thin, err := ticketbaseline.FromTicket(feat, task, 0, at)
	if err != nil {
		t.Fatal(err)
	}
	full, err := workspace.FromTicket(feat, task, repo, 0, at)
	if err != nil {
		t.Fatal(err)
	}
	if full.ManifestRoot == thin.ManifestRoot {
		t.Fatal("expected detail file to change ManifestRoot")
	}
	if len(full.Files) < 2 {
		t.Fatalf("files = %d, want >= 2", len(full.Files))
	}
}

func TestChangedSinceAndHead(t *testing.T) {
	repo := t.TempDir()
	run(t, repo, "git", "init")
	run(t, repo, "git", "config", "user.email", "t@example.com")
	run(t, repo, "git", "config", "user.name", "t")
	must(t, os.WriteFile(filepath.Join(repo, "a.txt"), []byte("a\n"), 0o644))
	run(t, repo, "git", "add", "a.txt")
	run(t, repo, "git", "commit", "-m", "a")
	head, dirty, err := workspace.Local{}.Head(context.Background(), repo)
	if err != nil {
		t.Fatal(err)
	}
	if head == "" || dirty {
		t.Fatalf("head=%q dirty=%v", head, dirty)
	}
	must(t, os.WriteFile(filepath.Join(repo, "b.txt"), []byte("b\n"), 0o644))
	run(t, repo, "git", "add", "b.txt")
	run(t, repo, "git", "commit", "-m", "b")
	changed, err := workspace.Local{}.ChangedSince(context.Background(), repo, "HEAD~1")
	if err != nil {
		t.Fatal(err)
	}
	if len(changed) != 1 || changed[0] != "b.txt" {
		t.Fatalf("changed = %v, want [b.txt]", changed)
	}
}

func runDocHome(t *testing.T, repo, feature, key string) string {
	t.Helper()
	root := filepath.Join("..", "..", "..", "scripts", "lib", "doc_home.py")
	abs, err := filepath.Abs(root)
	if err != nil {
		t.Fatal(err)
	}
	out, err := exec.Command("python3", abs, "--repo", repo, "--feature", feature, "--key", key).Output()
	if err != nil {
		t.Fatalf("doc_home.py: %v", err)
	}
	return strings.TrimSpace(string(out))
}

func runPythonManifest(t *testing.T, ticket, repo string) string {
	t.Helper()
	root := filepath.Join("..", "..", "..", "scripts", "lib", "baseline_manifest.py")
	abs, err := filepath.Abs(root)
	if err != nil {
		t.Fatal(err)
	}
	out, err := exec.Command("python3", abs, "--ticket", ticket, "--repo", repo).Output()
	if err != nil {
		t.Fatalf("baseline_manifest.py: %v (%s)", err, out)
	}
	return strings.TrimSpace(string(out))
}

func run(t *testing.T, dir string, name string, args ...string) {
	t.Helper()
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("%s %v: %v (%s)", name, args, err, out)
	}
}

func must(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}

func mustResolve(t *testing.T, path string) string {
	t.Helper()
	out, err := filepath.EvalSymlinks(path)
	if err != nil {
		t.Fatal(err)
	}
	return out
}
