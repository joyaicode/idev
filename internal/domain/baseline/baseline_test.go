package baseline_test

import (
	"strings"
	"testing"
	"time"

	"pgregory.net/rapid"

	"github.com/idev/internal/domain/baseline"
	"github.com/idev/pkg/canonical"
)

var at = time.Date(2026, 10, 16, 12, 0, 0, 0, time.UTC)

func doc() map[string]any {
	return map[string]any{
		"goal":       "export users",
		"non_goal":   []any{"no bulk import"},
		"items":      []any{map[string]any{"id": "B1", "text": "csv"}},
		"boundaries": []any{"no schema change"},
		"details":    []any{"docs/spec/demo.md"},
	}
}

func build(t *testing.T, files []baseline.File) baseline.Manifest {
	t.Helper()
	m, err := baseline.Build("demo", 1, files, "a1b2c3", false, at)
	if err != nil {
		t.Fatalf("Build: %v", err)
	}
	return m
}

func yamlFile(t *testing.T, path string, raw []byte, d map[string]any) baseline.File {
	t.Helper()
	f, err := baseline.YAMLFile(path, raw, d, nil)
	if err != nil {
		t.Fatalf("YAMLFile: %v", err)
	}
	return f
}

// --- what a seal covers ----------------------------------------------------

func TestOnlySealedFieldsCount(t *testing.T) {
	a := doc()
	b := doc()
	// Scratch work must not be part of the fingerprint: deliver-schema.md
	// requires these emptied before sealing, so including them would make
	// the seal depend on whether someone tidied up.
	b["review_questions"] = []any{"what about csv quoting?"}
	b["objections"] = []any{"none"}
	b["stage"] = "req"

	da, _, err := baseline.SemanticYAML(a, nil)
	if err != nil {
		t.Fatal(err)
	}
	db, _, err := baseline.SemanticYAML(b, nil)
	if err != nil {
		t.Fatal(err)
	}
	if da != db {
		t.Error("an unsealed field changed the digest")
	}
}

func TestEverySealedFieldCounts(t *testing.T) {
	base, _, err := baseline.SemanticYAML(doc(), nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, field := range baseline.SealedFields {
		edited := doc()
		edited[field] = "something else entirely"
		got, _, err := baseline.SemanticYAML(edited, nil)
		if err != nil {
			t.Fatal(err)
		}
		if got == base {
			t.Errorf("changing %q did not change the digest", field)
		}
	}
}

func TestAbsentFieldsAreRecordedNotInvented(t *testing.T) {
	// A baseline that never had non_goal and one where it was deleted are
	// different facts. The field list in the manifest is what distinguishes
	// them, so it has to reflect what was actually there.
	d := doc()
	delete(d, "non_goal")
	_, present, err := baseline.SemanticYAML(d, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, f := range present {
		if f == "non_goal" {
			t.Fatal("an absent field was reported as present")
		}
	}
	if len(present) != len(baseline.SealedFields)-1 {
		t.Errorf("present = %v, want %d fields", present, len(baseline.SealedFields)-1)
	}

	// And deleting it is a change.
	full, _, _ := baseline.SemanticYAML(doc(), nil)
	partial, _, _ := baseline.SemanticYAML(d, nil)
	if full == partial {
		t.Error("deleting a sealed field did not change the digest")
	}
}

func TestExplicitFieldListIsHonoured(t *testing.T) {
	_, present, err := baseline.SemanticYAML(doc(), []string{"goal"})
	if err != nil {
		t.Fatal(err)
	}
	if len(present) != 1 || present[0] != "goal" {
		t.Errorf("present = %v, want [goal]", present)
	}
}

func TestYAMLEntryRecordsBothDigests(t *testing.T) {
	raw := []byte("goal: export users\n")
	f := yamlFile(t, "baseline.yaml", raw, doc())
	if f.Mode != baseline.ModeYAMLFields {
		t.Errorf("mode = %s", f.Mode)
	}
	if f.Raw != canonical.Hash(raw) {
		t.Error("the raw digest must be of the original bytes")
	}
	if f.Semantic == f.Raw {
		t.Error("semantic and raw digests of different inputs collided")
	}
	if f.Size != len(raw) {
		t.Errorf("size = %d, want %d", f.Size, len(raw))
	}
}

func TestTextEntryIgnoresFormattingButNotContent(t *testing.T) {
	a := baseline.TextFile("spec.md", []byte("# Spec\r\n\r\nexport users   \n\n\n"))
	b := baseline.TextFile("spec.md", []byte("# Spec\n\nexport users\n"))
	if a.Semantic != b.Semantic {
		t.Error("line endings and trailing whitespace changed the semantic digest")
	}
	if a.Raw == b.Raw {
		t.Error("the raw digests should differ; that is what makes format-only detectable")
	}
	c := baseline.TextFile("spec.md", []byte("# Spec\n\nexport orders\n"))
	if b.Semantic == c.Semantic {
		t.Error("edited prose must change the semantic digest")
	}
}

// --- building the manifest -------------------------------------------------

func TestBuildComputesBothRoots(t *testing.T) {
	m := build(t, []baseline.File{
		yamlFile(t, "baseline.yaml", []byte("goal: x\n"), doc()),
		baseline.TextFile("spec.md", []byte("spec\n")),
	})
	if m.Schema != baseline.Schema {
		t.Errorf("schema = %q", m.Schema)
	}
	if !m.ManifestRoot.Valid() || !m.RawRoot.Valid() {
		t.Error("a manifest must carry usable roots")
	}
	if m.ManifestRoot == m.RawRoot {
		t.Error("the two roots collided")
	}
	// Files come back sorted, so a printed manifest is stable.
	if m.Files[0].Path != "baseline.yaml" || m.Files[1].Path != "spec.md" {
		t.Errorf("files not sorted: %s, %s", m.Files[0].Path, m.Files[1].Path)
	}
}

func TestBuildRefusesNonsense(t *testing.T) {
	good := baseline.TextFile("a.md", []byte("a\n"))
	cases := []struct {
		name    string
		feature string
		rev     int
		files   []baseline.File
	}{
		{"no feature", "", 1, []baseline.File{good}},
		{"zero revision", "demo", 0, []baseline.File{good}},
		{"negative revision", "demo", -1, []baseline.File{good}},
		{"no files", "demo", 1, nil},
		{"empty path", "demo", 1, []baseline.File{{Mode: baseline.ModeTextNormalized, Semantic: good.Semantic, Raw: good.Raw}}},
		{"duplicate path", "demo", 1, []baseline.File{good, good}},
		{"bad digest", "demo", 1, []baseline.File{{Path: "a.md", Semantic: "nope", Raw: "nope"}}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := baseline.Build(tc.feature, tc.rev, tc.files, "", false, at); err == nil {
				t.Errorf("Build accepted %s", tc.name)
			}
		})
	}
}

func TestBuildIsDeterministic(t *testing.T) {
	files := []baseline.File{
		yamlFile(t, "baseline.yaml", []byte("goal: x\n"), doc()),
		baseline.TextFile("spec.md", []byte("spec\n")),
	}
	reversed := []baseline.File{files[1], files[0]}
	a := build(t, files)
	b := build(t, reversed)
	if a.ManifestRoot != b.ManifestRoot || a.RawRoot != b.RawRoot {
		t.Error("the roots depend on the order files were collected in")
	}
}

// --- detecting what changed ------------------------------------------------

func TestIntactWhenNothingMoved(t *testing.T) {
	files := []baseline.File{
		yamlFile(t, "baseline.yaml", []byte("goal: x\n"), doc()),
		baseline.TextFile("spec.md", []byte("spec\n")),
	}
	sealed := build(t, files)
	got := baseline.Compare(sealed, build(t, files))
	if got.Verdict != baseline.VerdictIntact {
		t.Fatalf("verdict = %s, want intact (%s)", got.Verdict, got.Line)
	}
	if !got.Intact() {
		t.Error("intact must let the run continue")
	}
	if !strings.HasPrefix(got.Line, "OK") {
		t.Errorf("line = %q, want an OK line", got.Line)
	}
}

func TestReformattingIsAWarnNotABlock(t *testing.T) {
	sealed := build(t, []baseline.File{baseline.TextFile("spec.md", []byte("spec\n"))})
	// Same meaning, different bytes.
	current := build(t, []baseline.File{baseline.TextFile("spec.md", []byte("spec   \r\n\n"))})

	got := baseline.Compare(sealed, current)
	if got.Verdict != baseline.VerdictFormatOnly {
		t.Fatalf("verdict = %s, want format_only (%s)", got.Verdict, got.Line)
	}
	if !got.Intact() {
		t.Error("a reformat must not stop the run")
	}
	if !strings.HasPrefix(got.Line, "WARN") {
		t.Errorf("line = %q, want a WARN line", got.Line)
	}
	if len(got.Changes) != 1 || got.Changes[0].Kind != "reformatted" {
		t.Errorf("changes = %+v, want one reformatted", got.Changes)
	}
}

func TestAnEditedRequirementIsDrift(t *testing.T) {
	// Threat T5: signed, then edited.
	sealed := build(t, []baseline.File{
		yamlFile(t, "baseline.yaml", []byte("goal: export users\n"), doc()),
	})
	edited := doc()
	edited["goal"] = "export everything"
	current := build(t, []baseline.File{
		yamlFile(t, "baseline.yaml", []byte("goal: export everything\n"), edited),
	})

	got := baseline.Compare(sealed, current)
	if got.Verdict != baseline.VerdictDrift {
		t.Fatalf("verdict = %s, want drift", got.Verdict)
	}
	if got.Intact() {
		t.Error("drift must stop the run")
	}
	// The old CLI's shape, so the conductor and the golden files agree.
	if !strings.HasPrefix(got.Line, "BLOCKED baseline-drift baseline.yaml (sealed rev 1)") {
		t.Errorf("line = %q", got.Line)
	}
	if len(got.Changes) != 1 || got.Changes[0].Kind != "changed" {
		t.Errorf("changes = %+v", got.Changes)
	}
}

func TestAddedAndRemovedFilesAreDrift(t *testing.T) {
	a := baseline.TextFile("a.md", []byte("a\n"))
	b := baseline.TextFile("b.md", []byte("b\n"))

	removed := baseline.Compare(build(t, []baseline.File{a, b}), build(t, []baseline.File{a}))
	if removed.Verdict != baseline.VerdictDrift {
		t.Errorf("removing a sealed file = %s, want drift", removed.Verdict)
	}
	if removed.Changes[0].Kind != "removed" {
		t.Errorf("kind = %s, want removed", removed.Changes[0].Kind)
	}

	added := baseline.Compare(build(t, []baseline.File{a}), build(t, []baseline.File{a, b}))
	if added.Verdict != baseline.VerdictDrift {
		t.Errorf("adding a file = %s, want drift", added.Verdict)
	}
	if added.Changes[0].Kind != "added" {
		t.Errorf("kind = %s, want added", added.Changes[0].Kind)
	}
}

func TestDriftWinsOverAConcurrentReformat(t *testing.T) {
	// One file reformatted, one file genuinely edited. The verdict is drift,
	// and the line names the edited file rather than the reformatted one.
	sealed := build(t, []baseline.File{
		baseline.TextFile("a.md", []byte("a\n")),
		baseline.TextFile("z.md", []byte("z\n")),
	})
	current := build(t, []baseline.File{
		baseline.TextFile("a.md", []byte("a   \n")),    // reformat
		baseline.TextFile("z.md", []byte("changed\n")), // real edit
	})
	got := baseline.Compare(sealed, current)
	if got.Verdict != baseline.VerdictDrift {
		t.Fatalf("verdict = %s, want drift", got.Verdict)
	}
	if !strings.Contains(got.Line, "z.md") {
		t.Errorf("line = %q, should name the edited file, not the reformatted one", got.Line)
	}
}

func TestUnsealedIsNotDrift(t *testing.T) {
	got := baseline.Compare(baseline.Manifest{}, build(t, []baseline.File{
		baseline.TextFile("a.md", []byte("a\n")),
	}))
	if got.Verdict != baseline.VerdictUnsealed {
		t.Fatalf("verdict = %s, want unsealed", got.Verdict)
	}
	if !got.Intact() {
		// An unsealed baseline is not a drift; the stage machine is what
		// refuses to advance, not this.
		t.Log("unsealed does not count as intact, which is fine as long as the caller distinguishes it")
	}
}

func TestChangesAreSortedByPath(t *testing.T) {
	sealed := build(t, []baseline.File{
		baseline.TextFile("c.md", []byte("c\n")),
		baseline.TextFile("a.md", []byte("a\n")),
		baseline.TextFile("b.md", []byte("b\n")),
	})
	current := build(t, []baseline.File{
		baseline.TextFile("c.md", []byte("c2\n")),
		baseline.TextFile("a.md", []byte("a2\n")),
		baseline.TextFile("b.md", []byte("b2\n")),
	})
	got := baseline.Compare(sealed, current)
	for i := 1; i < len(got.Changes); i++ {
		if got.Changes[i-1].Path > got.Changes[i].Path {
			t.Fatalf("changes not sorted: %v", got.Changes)
		}
	}
}

// --- properties ------------------------------------------------------------

// Comparing a manifest with itself is always intact. If this failed, every
// stage check would report drift on unchanged content.
func TestPropertyAManifestNeverDriftsFromItself(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		n := rapid.IntRange(1, 6).Draw(t, "files")
		files := make([]baseline.File, 0, n)
		seen := map[string]bool{}
		for i := 0; i < n; i++ {
			path := rapid.SampledFrom([]string{"a.md", "b.md", "c.md", "d.md", "e.md", "f.md"}).
				Draw(t, "path")
			if seen[path] {
				continue
			}
			seen[path] = true
			files = append(files, baseline.TextFile(path, []byte(rapid.String().Draw(t, "body"))))
		}
		m, err := baseline.Build("demo", 1, files, "head", false, at)
		if err != nil {
			t.Fatalf("Build: %v", err)
		}
		got := baseline.Compare(m, m)
		if got.Verdict != baseline.VerdictIntact {
			t.Fatalf("a manifest drifted from itself: %s (%s)", got.Verdict, got.Line)
		}
	})
}

// Any change to a sealed field is drift, and only a byte-level change is
// format_only. The two must never be confused — one blocks a run.
func TestPropertyDriftAndFormatOnlyAreNeverConfused(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		body := rapid.String().Draw(t, "body")
		sealed, err := baseline.Build("demo", 1,
			[]baseline.File{baseline.TextFile("a.md", []byte(body))}, "h", false, at)
		if err != nil {
			t.Fatal(err)
		}

		if rapid.Bool().Draw(t, "reformatOnly") {
			// Changes that normalisation folds away.
			noise := rapid.SampledFrom([]string{"\n", "\n\n", "   \n", "\r\n"}).Draw(t, "noise")
			current, err := baseline.Build("demo", 1,
				[]baseline.File{baseline.TextFile("a.md", []byte(body+noise))}, "h", false, at)
			if err != nil {
				t.Fatal(err)
			}
			got := baseline.Compare(sealed, current)
			if got.Verdict == baseline.VerdictDrift {
				t.Fatalf("whitespace read as drift: %q + %q", body, noise)
			}
			if !got.Intact() {
				t.Fatal("a format-only change blocked the run")
			}
			return
		}

		// A change normalisation cannot fold away.
		current, err := baseline.Build("demo", 1,
			[]baseline.File{baseline.TextFile("a.md", []byte(body+"x"))}, "h", false, at)
		if err != nil {
			t.Fatal(err)
		}
		got := baseline.Compare(sealed, current)
		if canonical.HashText([]byte(body)) == canonical.HashText([]byte(body+"x")) {
			return // the two normalise the same; not a real edit
		}
		if got.Verdict != baseline.VerdictDrift {
			t.Fatalf("an edit read as %s: %q -> %q", got.Verdict, body, body+"x")
		}
		if got.Intact() {
			t.Fatal("an edited requirement did not stop the run")
		}
	})
}
