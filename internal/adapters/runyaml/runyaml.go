// Package runyaml projects step outcomes into a ticket's run.yaml.
//
// Phase 1 §6: Go is the writer of the YAML bytes. Python may compute the next
// document in memory; only this package (via `idev run write` / `idev run record`)
// puts those bytes on disk, under the same flock convention as safeyaml.py.
//
// E2.1: when SQLite holds a live (non-external) run, Export overlays the
// domain run onto the YAML file so the file becomes a projection, not truth.
package runyaml

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/idev/internal/domain/run"
	"go.yaml.in/yaml/v3"
	"golang.org/x/sys/unix"
)

// ErrStale is returned when --expect-sha256 does not match the file on disk.
// The caller should re-read, re-mutate and try again.
type ErrStale struct {
	Want string
	Got  string
}

func (e *ErrStale) Error() string {
	return fmt.Sprintf("runyaml: stale file (want sha256 %s, got %s); record again", e.Want, e.Got)
}

func lock(path string) (*os.File, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, fmt.Errorf("runyaml: mkdir: %w", err)
	}
	lockPath := path + ".lock"
	lf, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, fmt.Errorf("runyaml: lock %s: %w", lockPath, err)
	}
	if err := unix.Flock(int(lf.Fd()), unix.LOCK_EX); err != nil {
		_ = lf.Close()
		return nil, fmt.Errorf("runyaml: flock: %w", err)
	}
	return lf, nil
}

func unlock(lf *os.File) {
	_ = unix.Flock(int(lf.Fd()), unix.LOCK_UN)
	_ = lf.Close()
}

func atomicWrite(path string, body []byte) error {
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, body, 0o644); err != nil {
		return fmt.Errorf("runyaml: write temp: %w", err)
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return fmt.Errorf("runyaml: rename: %w", err)
	}
	return nil
}

// SHA256Hex is the hex digest of the file contents, or "" when missing.
func SHA256Hex(path string) (string, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", err
	}
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:]), nil
}

// Write replaces the file with body under an exclusive flock.
// expectSHA must match the current digest ("" means the file is missing or
// empty). Always compared under the lock so concurrent creators that all saw
// an empty file still serialize: the second gets ErrStale.
func Write(path string, body []byte, expectSHA string) error {
	if path == "" {
		return fmt.Errorf("runyaml: path is required")
	}
	lf, err := lock(path)
	if err != nil {
		return err
	}
	defer unlock(lf)

	got, err := SHA256Hex(path)
	if err != nil {
		return err
	}
	if got != expectSHA {
		return &ErrStale{Want: expectSHA, Got: got}
	}
	return atomicWrite(path, body)
}

// Record updates one step's status on disk under an exclusive flock.
func Record(path, stepID, status, evidence, note string) error {
	if path == "" || stepID == "" || status == "" {
		return fmt.Errorf("runyaml: path, step and status are required")
	}
	lf, err := lock(path)
	if err != nil {
		return err
	}
	defer unlock(lf)

	raw, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("runyaml: read %s: %w", path, err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return fmt.Errorf("runyaml: parse %s: %w", path, err)
	}
	steps, ok := doc["steps"].([]any)
	if !ok {
		return fmt.Errorf("runyaml: %s has no steps list", path)
	}
	found := false
	now := time.Now().Format(time.RFC3339)
	for i, s := range steps {
		step, ok := s.(map[string]any)
		if !ok {
			continue
		}
		if fmt.Sprint(step["id"]) != stepID {
			continue
		}
		step["status"] = status
		step["at"] = now
		if evidence != "" {
			step["evidence"] = evidence
		}
		if note != "" {
			step["note"] = note
		}
		steps[i] = step
		found = true
		break
	}
	if !found {
		return fmt.Errorf("runyaml: no step %q in %s", stepID, path)
	}
	doc["steps"] = steps
	if st, _ := doc["status"].(string); st == "" || st == "blocked" {
		doc["status"] = "running"
	}
	out, err := yaml.Marshal(doc)
	if err != nil {
		return fmt.Errorf("runyaml: marshal: %w", err)
	}
	return atomicWrite(path, out)
}

// Doc is the subset of run.yaml needed to refresh the SQLite projection.
type Doc struct {
	ID         string
	WorkflowID string
	Feature    string
	Risk       string
	Steps      []Step
}

// Step is one projected step.
type Step struct {
	ID     string
	Kind   string
	State  string
	Writer string
	Group  string
	Writes []string
}

// ParseDoc reads the projection fields from YAML bytes.
func ParseDoc(raw []byte) (Doc, error) {
	var m map[string]any
	if err := yaml.Unmarshal(raw, &m); err != nil {
		return Doc{}, err
	}
	d := Doc{
		ID:         str(m["run_id"]),
		WorkflowID: str(m["workflow_id"]),
		Feature:    str(m["feature"]),
		Risk:       str(m["risk_tier"]),
	}
	if d.Risk == "" {
		d.Risk = "P1"
	}
	steps, _ := m["steps"].([]any)
	for _, s := range steps {
		step, ok := s.(map[string]any)
		if !ok {
			continue
		}
		st := Step{
			ID:     str(step["id"]),
			Kind:   str(step["kind"]),
			State:  str(step["status"]),
			Group:  str(step["group"]),
		}
		if st.State == "" {
			st.State = "pending"
		}
		if del, ok := step["delegated"].(map[string]any); ok {
			st.Writer = str(del["agent"])
		}
		if writes, ok := step["writes"].([]any); ok {
			for _, w := range writes {
				if s := str(w); s != "" {
					st.Writes = append(st.Writes, s)
				}
			}
		}
		d.Steps = append(d.Steps, st)
	}
	return d, nil
}

func str(v any) string {
	if v == nil {
		return ""
	}
	return fmt.Sprint(v)
}

// Export overlays a domain run onto existing YAML bytes (preserving params,
// recipe, policy, and other Python-owned keys) and returns the new document.
// Terminal step states are stamped; open steps keep no status key so the
// Python driver still reads them as unfinished.
func Export(existing []byte, rn run.Run) ([]byte, error) {
	doc := map[string]any{}
	if len(existing) > 0 {
		if err := yaml.Unmarshal(existing, &doc); err != nil {
			return nil, fmt.Errorf("runyaml: parse for export: %w", err)
		}
		if doc == nil {
			doc = map[string]any{}
		}
	}
	doc["run_id"] = rn.ID
	doc["workflow_id"] = rn.WorkflowID
	if rn.Feature != "" {
		doc["feature"] = rn.Feature
	}
	doc["status"] = yamlRunStatus(rn.Status())

	prevByID := map[string]map[string]any{}
	if steps, ok := doc["steps"].([]any); ok {
		for _, s := range steps {
			m, ok := s.(map[string]any)
			if !ok {
				continue
			}
			prevByID[str(m["id"])] = m
		}
	}
	outSteps := make([]any, 0, len(rn.Steps))
	for _, st := range rn.Steps {
		m := map[string]any{}
		if prev := prevByID[st.ID]; prev != nil {
			for k, v := range prev {
				m[k] = v
			}
		}
		m["id"] = st.ID
		m["kind"] = st.Kind
		if st.Group != "" {
			m["group"] = st.Group
		}
		if len(st.Writes) > 0 {
			writes := make([]any, len(st.Writes))
			for i, w := range st.Writes {
				writes[i] = w
			}
			m["writes"] = writes
		}
		if terminal, ok := yamlStepStatus(st.State); ok {
			m["status"] = terminal
			if st.Evidence != "" {
				m["evidence"] = st.Evidence
			}
			if st.Note != "" {
				m["note"] = st.Note
			}
			delete(m, "delegated")
		} else {
			delete(m, "evidence")
			delete(m, "at")
			// Project open machine states so lease acquire's ProjectRun does
			// not collapse verifying back into delegated (E2.5 / E3.1).
			switch st.State {
			case run.StepDelegated, run.StepReturned:
				delete(m, "status")
				if st.Writer != "" {
					m["delegated"] = map[string]any{"agent": st.Writer}
				}
			case run.StepVerifying:
				m["status"] = string(run.StepVerifying)
				if st.Writer != "" {
					m["delegated"] = map[string]any{"agent": st.Writer}
				}
			case run.StepAwaitingSignoff:
				m["status"] = string(run.StepAwaitingSignoff)
				delete(m, "delegated")
			default:
				delete(m, "status")
				delete(m, "delegated")
			}
		}
		outSteps = append(outSteps, m)
	}
	doc["steps"] = outSteps
	if len(rn.Revisions) > 0 {
		revs := make([]any, 0, len(rn.Revisions))
		for _, rev := range rn.Revisions {
			revs = append(revs, map[string]any{
				"step": rev.StepID,
				"from": string(rev.From),
				"to":   string(rev.To),
				"note": rev.Note,
			})
		}
		doc["revisions"] = revs
	}
	out, err := yaml.Marshal(doc)
	if err != nil {
		return nil, fmt.Errorf("runyaml: marshal export: %w", err)
	}
	return out, nil
}

func yamlRunStatus(s run.Status) string {
	switch s {
	case run.StatusAwaitingHuman:
		// Python still treats a pending gate as running.
		return "running"
	case run.StatusPending:
		return "running"
	default:
		return string(s)
	}
}

func yamlStepStatus(s run.StepState) (string, bool) {
	switch s {
	case run.StepPASS, run.StepFAIL, run.StepUNPROVEN, run.StepSKIPPED, run.StepBLOCKED, run.StepAUTO:
		return string(s), true
	default:
		return "", false
	}
}

// WriteExport writes Export(existing, rn) under flock with an empty expect
// when the file is missing, else the current digest (caller supplies expect).
func WriteExport(path string, existing []byte, rn run.Run, expectSHA string) error {
	body, err := Export(existing, rn)
	if err != nil {
		return err
	}
	return Write(path, body, expectSHA)
}
