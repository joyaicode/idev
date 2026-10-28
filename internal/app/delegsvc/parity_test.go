package delegsvc_test

import (
	"os"
	"regexp"
	"sort"
	"strings"
	"testing"

	"github.com/idev/internal/app/delegsvc"
)

// The check names are identifiers, not labels: they sit in stored records,
// in the weekly audit's counts and in the agent definitions' prose. While
// both implementations are live, a name that exists on one side and not the
// other means a record written by one cannot be compared with a record
// written by the other.
//
// This test exists because writing the Go side from the design document's
// §6.3 table produced five names the Python implementation does not use
// (assumed-declared, scope-covers-changed, read-covers-changed,
// revert-present, and a single scope check where there are two). Nothing
// caught it until the names were compared directly.
const pythonSource = "../../../scripts/delegation.py"

var checkKeyRE = regexp.MustCompile(`(?:checks|out)\["([a-z0-9-]+)"\]`)

func pythonCheckNames(t *testing.T) map[string]bool {
	t.Helper()
	raw, err := os.ReadFile(pythonSource)
	if err != nil {
		t.Fatalf("read %s: %v", pythonSource, err)
	}
	names := map[string]bool{}
	for _, m := range checkKeyRE.FindAllStringSubmatch(string(raw), -1) {
		names[m[1]] = true
	}
	if len(names) == 0 {
		t.Fatal("found no check names in the Python source; the pattern has drifted")
	}
	return names
}

// goCheckNames are the names this package can emit. Listed explicitly rather
// than scraped, so adding a constant without deciding which side it belongs
// to does not silently pass.
func goCheckNames() []string {
	return []string{
		delegsvc.CheckBriefComplete,
		delegsvc.CheckReportParsed,
		delegsvc.CheckEvidence,
		delegsvc.CheckNoSignoffWrite,
		delegsvc.CheckScopeDeclared,
		delegsvc.CheckScopeHeld,
		delegsvc.CheckReadBefore,
		delegsvc.CheckRevertAnchor,
		delegsvc.CheckRedFirst,
		delegsvc.CheckAssumption,
		delegsvc.CheckAssumedTagged,
		delegsvc.CheckFactsFirst,
		delegsvc.CheckS0Declared,
		delegsvc.CheckLeasePaths,
		delegsvc.CheckBaselineIntact,
	}
}

// designAdditions are the checks the design adds (§6.3 marks them "新").
// They have no Python counterpart by construction: they compare the report
// against evidence the server gathered itself, which the Python side had no
// way to do.
var designAdditions = map[string]bool{
	delegsvc.CheckLeasePaths:     true,
	delegsvc.CheckBaselineIntact: true,
}

func TestEveryGoCheckNameExistsInPython(t *testing.T) {
	python := pythonCheckNames(t)
	for _, name := range goCheckNames() {
		if designAdditions[name] {
			continue
		}
		if !python[name] {
			t.Errorf("check %q does not exist in %s; a record using it cannot be compared "+
				"with one written by the Python side", name, pythonSource)
		}
	}
}

func TestPythonChecksAreEitherPortedOrListedAsDeferred(t *testing.T) {
	// The Python side has checks this package has not ported. That is a
	// decision, so it is recorded here rather than discovered later: each
	// one is either in the Go set or in this list with a reason.
	deferred := map[string]string{
		"anchor-granularity":     "WARN-only nicety about file:symbol granularity; no behaviour depends on it",
		"artifact-verified":      "needs the workspace port to compare a running artefact with source (P2.4)",
		"canon-walked":           "needs review.md parsing, which moves to the asset bundle in P3",
		"changed-within-actual":  "reads IDEV_DATA/subagent-stops.jsonl from the client hook; Go record path has no hook log yet (phase 1 §4)",
		"drift-declared":         "needs doc-drift detection against the asset bundle (P3)",
		"facts-sourced":          "subsumed by facts-first here; the Python split is historical",
		"hit-applied":            "needs the convention tables, which are asset-bundle data (P3)",
		"java-hygiene":           "scans the product checkout's branch diff against the java.md rows; needs the workspace port (P2.4) and the asset bundle (P3)",
		"return-schema":          "validates api/schemas/delegation-return.schema.json via Python jsonschema; port with the asset-bundle validator (phase 1 §7)",
		"struct-gated":           "needs the structured-change gate from coding.md §3 (P3)",
	}

	ported := map[string]bool{}
	for _, n := range goCheckNames() {
		ported[n] = true
	}

	var unaccounted []string
	for name := range pythonCheckNames(t) {
		if ported[name] {
			continue
		}
		if _, ok := deferred[name]; ok {
			continue
		}
		unaccounted = append(unaccounted, name)
	}
	sort.Strings(unaccounted)
	if len(unaccounted) > 0 {
		t.Errorf("these Python checks are neither ported nor listed as deferred: %s\n"+
			"add each one to the Go set or to the deferred list with a reason",
			strings.Join(unaccounted, ", "))
	}

	// And the other way: a deferred entry that has since been ported should
	// come off the list, or the list becomes folklore.
	for name := range deferred {
		if ported[name] {
			t.Errorf("%q is listed as deferred but is implemented; remove the entry", name)
		}
	}
}

func TestNoCheckNameIsEmptyOrDuplicated(t *testing.T) {
	seen := map[string]bool{}
	for _, name := range goCheckNames() {
		if name == "" {
			t.Error("a check constant is empty")
		}
		if seen[name] {
			t.Errorf("check %q is declared twice", name)
		}
		seen[name] = true
	}
}
