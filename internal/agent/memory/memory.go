// Package memory is ideva's cross-session recall, in the shape the kernel
// already fixed on the Python side (trace.py resume_pack): assembly, not
// summarization — open steps, progress, prior failures, reads pointers,
// timeline pointers, zero generated text. The Go version reads the same
// artifacts a fresh ideva session needs to pick a ticket up without
// re-reading the whole world.
package memory

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"go.yaml.in/yaml/v3"
)

// Resume is the bundle a fresh session reads first. Field names match the
// Python schema exactly (resume_pack in scripts/trace.py writes the same
// keys to <ticket>/workflow/resume.yaml) — a Go reader and a Python writer
// must be interchangeable, the reads.yaml lesson.
type Resume struct {
	SchemaVersion int               `yaml:"schema_version"`
	Feature       string            `yaml:"feature"`
	Rounds        int               `yaml:"rounds,omitempty"`
	CtxLastRound  int               `yaml:"ctx_last_round,omitempty"`
	HandoffNote   string            `yaml:"handoff_note,omitempty"`
	Open          []string          `yaml:"open"`
	Progress      string            `yaml:"progress,omitempty"`
	PriorFailures map[string]string `yaml:"prior_failures,omitempty"`
	Reads         []ReadRow         `yaml:"reads,omitempty"`
	TimelineEvents []TimelineEvent  `yaml:"timeline_events,omitempty"`
}

// ReadRow is one reads.yaml row: a pointer, never a body (disk replays it).
type ReadRow struct {
	Step   string `yaml:"step"`
	Span   string `yaml:"span"`
	SHA256 string `yaml:"sha256"`
}

// TimelineEvent points at a trace the structured-retainer folded: which
// source round, what it recorded, how many delegations it carried.
type TimelineEvent struct {
	Source     string `yaml:"source"`
	Recorded   []string `yaml:"recorded,omitempty"`
	Delegations int    `yaml:"delegations"`
}

// ProgressLine formats PROGRESS the way the loop prints it: closed/total
// plus open ids — one vocabulary, two hosts.
func ProgressLine(steps []RunStep) string {
	total := len(steps)
	closed := 0
	var open []string
	for _, s := range steps {
		if s.Status == "" {
			open = append(open, s.ID)
		} else {
			closed++
		}
	}
	line := fmt.Sprintf("PROGRESS closed=%d/%d", closed, total)
	if len(open) > 0 {
		line += " open=" + strings.Join(open, ",")
	}
	return line
}

// RunStep is the subset of run.yaml a resume needs.
type RunStep struct {
	ID     string `yaml:"id"`
	Status string `yaml:"status"`
}

type runFile struct {
	SchemaVersion int       `yaml:"schema_version"`
	WorkflowID     string    `yaml:"workflow_id"`
	Feature        string    `yaml:"feature"`
	Steps          []RunStep `yaml:"steps"`
	Revisions      []struct {
		Note string `yaml:"note"`
	} `yaml:"revisions"`
}

// LoadResume reads <ticket>/workflow/resume.yaml if the Python side wrote
// one. Missing file is (nil, nil): nothing to resume is a normal state,
// and a fresh session falls back to run.yaml plus the ledger below.
func LoadResume(ticketDir string) (*Resume, error) {
	path := filepath.Join(ticketDir, "workflow", "resume.yaml")
	body, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("memory: resume: %w", err)
	}
	var r Resume
	if err := yaml.Unmarshal(body, &r); err != nil {
		return nil, fmt.Errorf("memory: resume parse: %w", err)
	}
	return &r, nil
}

// LoadReads reads <ticket>/workflow/reads.yaml — the same ledger the
// Python read_ledger maintains; replay uses the same sha256-match rule.
func LoadReads(ticketDir string) ([]ReadRow, error) {
	path := filepath.Join(ticketDir, "workflow", "reads.yaml")
	body, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("memory: reads: %w", err)
	}
	var wrap struct {
		Reads []ReadRow `yaml:"reads"`
	}
	if err := yaml.Unmarshal(body, &wrap); err != nil {
		return nil, fmt.Errorf("memory: reads parse: %w", err)
	}
	return wrap.Reads, nil
}

// LoadRunSteps reads the run.yaml projection for progress and open steps.
func LoadRunSteps(ticketDir string) ([]RunStep, error) {
	path := filepath.Join(ticketDir, "workflow", "run.yaml")
	body, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("memory: run: %w", err)
	}
	var run runFile
	if err := yaml.Unmarshal(body, &run); err != nil {
		return nil, fmt.Errorf("memory: run parse: %w", err)
	}
	return run.Steps, nil
}

// BuildResume assembles a Resume the same way the Python resume_pack does:
// from run.yaml (open + progress) and reads.yaml (pointers). Callers that
// have the Python-written resume.yaml should prefer LoadResume — this
// builder is for the moments only the raw artifacts exist.
func BuildResume(feature string, ticketDir string) (*Resume, error) {
	steps, err := LoadRunSteps(ticketDir)
	if err != nil {
		return nil, err
	}
	if steps == nil {
		return nil, nil
	}
	reads, err := LoadReads(ticketDir)
	if err != nil {
		return nil, err
	}
	var open []string
	for _, s := range steps {
		if s.Status == "" {
			open = append(open, s.ID)
		}
	}
	if len(open) == 0 && len(reads) == 0 {
		return nil, nil
	}
	return &Resume{
		SchemaVersion: 1,
		Feature:       feature,
		Open:          open,
		Progress:      ProgressLine(steps),
		Reads:         reads,
	}, nil
}

// Render lays the resume out as the lines a system or user message carries:
// the model reads pointers and goes, the same way agent-brief.md's
// `RESUME` row prescribes for the Python side.
func (r *Resume) Render() string {
	var b strings.Builder
	fmt.Fprintf(&b, "RESUME feature=%s\n", r.Feature)
	fmt.Fprintf(&b, "%s\n", r.Progress)
	if len(r.Open) > 0 {
		fmt.Fprintf(&b, "open: %s\n", strings.Join(r.Open, ","))
	}
	if len(r.PriorFailures) > 0 {
		b.WriteString("prior_failures:\n")
		for _, step := range sortedKeys(r.PriorFailures) {
			fmt.Fprintf(&b, "  %s: %s\n", step, r.PriorFailures[step])
		}
	}
	if len(r.Reads) > 0 {
		b.WriteString("reads (pointer, 需要时 load):\n")
		for _, row := range r.Reads {
			fmt.Fprintf(&b, "  %s %s sha256=%s\n", row.Step, row.Span, row.SHA256)
		}
	}
	return b.String()
}

func sortedKeys(m map[string]string) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
