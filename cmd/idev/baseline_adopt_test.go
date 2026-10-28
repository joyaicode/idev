package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/idev/internal/app/baselinesvc"
)

const legacyBaseline = "" +
	"revision: 1\n" +
	"goal: carry the legacy seal over\n" +
	"non_goal: reseal anything\n" +
	"items:\n" +
	"  - id: I1\n" +
	"    must: survive the move\n" +
	"boundaries: []\n" +
	"details:\n" +
	"  - docs/task/legacy/design.md\n" +
	"sealed: true\n"

type legacyRepo struct {
	t      *testing.T
	f      fixture
	root   string
	ticket string
}

func newLegacyRepo(t *testing.T) legacyRepo {
	t.Helper()
	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git not on PATH")
	}
	r := legacyRepo{t: t, f: newFixture(t, "")}
	r.root = filepath.Join(t.TempDir(), "product")
	r.ticket = filepath.Join(r.root, "docs", "task", "legacy")
	must(t, os.MkdirAll(r.ticket, 0o755))
	r.git(time.Time{}, "init", "-q")
	r.git(time.Time{}, "config", "user.email", "legacy@example.com")
	r.git(time.Time{}, "config", "user.name", "legacy")
	return r
}

func (r legacyRepo) git(at time.Time, args ...string) {
	r.t.Helper()
	cmd := exec.Command("git", append([]string{"-C", r.root}, args...)...)
	cmd.Env = os.Environ()
	if !at.IsZero() {
		stamp := at.Format(time.RFC3339)
		cmd.Env = append(cmd.Env, "GIT_AUTHOR_DATE="+stamp, "GIT_COMMITTER_DATE="+stamp)
	}
	if out, err := cmd.CombinedOutput(); err != nil {
		r.t.Fatalf("git %v: %v\n%s", args, err, out)
	}
}

func (r legacyRepo) write(name, body string) {
	r.t.Helper()
	must(r.t, os.WriteFile(filepath.Join(r.ticket, name), []byte(body), 0o644))
}

func (r legacyRepo) commit(at time.Time, msg string) {
	r.t.Helper()
	r.git(at, "add", "-A")
	r.git(at, "commit", "-q", "-m", msg)
}

func (r legacyRepo) adopt(extra ...string) (int, string, string) {
	args := []string{"baseline", "adopt", "--feature", "legacy", "--ticket", r.ticket, "--by", "alice"}
	if len(extra) == 0 {
		extra = []string{"--reason", "sealed in YAML before the store existed"}
	}
	return r.f.do(false, "", append(args, extra...)...)
}

func beforeCutover() time.Time { return baselinesvc.LegacyCutover.Add(-48 * time.Hour) }
func afterCutover() time.Time  { return baselinesvc.LegacyCutover.Add(2 * time.Hour) }

func TestBaselineAdoptTakesASealCommittedBeforeTheStore(t *testing.T) {
	r := newLegacyRepo(t)
	r.write("baseline.yaml", legacyBaseline)
	r.write("design.md", "the design the seal covered\n")
	r.commit(beforeCutover(), "seal legacy")

	if code, _, _ := r.f.do(false, "", "baseline", "sealed", "--feature", "legacy"); code == exitOK {
		t.Fatal("no row before adopting")
	}
	code, out, errOut := r.adopt()
	if code != exitOK {
		t.Fatalf("adopt: code=%d out=%s err=%s", code, out, errOut)
	}
	var got map[string]any
	must(t, json.Unmarshal([]byte(out), &got))
	if got["status"] != "sealed" || got["assurance"] != "low" || got["provenance"] != "legacy-yaml" {
		t.Fatalf("adopt out = %v", got)
	}
	if code, out, errOut := r.f.do(false, "", "baseline", "sealed", "--feature", "legacy"); code != exitOK {
		t.Fatalf("sealed after adopt: %s %s", out, errOut)
	}
	if code, out, errOut := r.f.do(false, "", "baseline", "verify",
		"--feature", "legacy", "--ticket", r.ticket, "--block-run=false"); code != exitOK {
		t.Fatalf("verify after adopt: %s %s", out, errOut)
	}

	code, out, errOut = r.f.do(false, "", "audit", "export")
	if code != exitOK {
		t.Fatalf("export: %s", errOut)
	}
	var adopted map[string]any
	for _, line := range strings.Split(strings.TrimSpace(out), "\n") {
		var ev map[string]any
		must(t, json.Unmarshal([]byte(line), &ev))
		if ev["action"] == "baseline.adopted" {
			adopted = ev
		}
	}
	if adopted == nil {
		t.Fatalf("no baseline.adopted event in %s", out)
	}
	detail, _ := adopted["detail"].(map[string]any)
	if detail["assurance"] != "low" || detail["legacy_commit"] != got["legacy_commit"] || detail["reason"] == "" {
		t.Fatalf("adopted event detail = %v", detail)
	}

	if code, _, errOut := r.adopt(); code == exitOK || !strings.Contains(errOut, "sealed") {
		t.Fatalf("adopting twice must conflict: code=%d err=%s", code, errOut)
	}
}

func TestBaselineAdoptRefusesWhatHistoryDoesNotShow(t *testing.T) {
	cases := []struct {
		name  string
		setup func(r legacyRepo)
		want  string
	}{
		{"sealed only after the cutover", func(r legacyRepo) {
			r.write("baseline.yaml", legacyBaseline)
			r.write("design.md", "d\n")
			r.commit(afterCutover(), "seal after the store")
		}, "no commit before"},
		{"unsealed at the cutover", func(r legacyRepo) {
			r.write("baseline.yaml", strings.Replace(legacyBaseline, "sealed: true", "sealed: false", 1))
			r.write("design.md", "d\n")
			r.commit(beforeCutover(), "draft")
			r.write("baseline.yaml", legacyBaseline)
			r.commit(afterCutover(), "hand-sealed later")
		}, "was not sealed"},
		{"edited since the seal", func(r legacyRepo) {
			r.write("baseline.yaml", legacyBaseline)
			r.write("design.md", "d\n")
			r.commit(beforeCutover(), "seal legacy")
			r.write("design.md", "a different design\n")
		}, "changed since the legacy seal"},
		{"a details file the seal never saw", func(r legacyRepo) {
			r.write("baseline.yaml", legacyBaseline)
			r.commit(beforeCutover(), "seal legacy without its design")
			r.write("design.md", "d\n")
		}, "was not committed"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			r := newLegacyRepo(t)
			c.setup(r)
			code, out, errOut := r.adopt()
			if code == exitOK || !strings.Contains(errOut, c.want) {
				t.Fatalf("want refusal %q, got code=%d out=%s err=%s", c.want, code, out, errOut)
			}
			if code, _, _ := r.f.do(false, "", "baseline", "sealed", "--feature", "legacy"); code == exitOK {
				t.Fatal("a refused adoption must leave no row")
			}
		})
	}
}

func TestBaselineAdoptNeedsAReason(t *testing.T) {
	r := newLegacyRepo(t)
	r.write("baseline.yaml", legacyBaseline)
	r.write("design.md", "d\n")
	r.commit(beforeCutover(), "seal legacy")
	if code, _, errOut := r.adopt("--reason", "  "); code != exitUsage || !strings.Contains(errOut, "--reason") {
		t.Fatalf("want usage error naming --reason, got code=%d err=%s", code, errOut)
	}
}
