package schemas_test

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/idev/pkg/schemas"
)

// testdata lives beside the contracts, not beside this test: the corpus
// belongs to the contract, and P2's MCP tests read the same files.
const corpus = "../../api/schemas/testdata"

func TestEveryContractCompiles(t *testing.T) {
	names, err := schemas.Names()
	if err != nil {
		t.Fatalf("Names: %v", err)
	}
	if len(names) == 0 {
		t.Fatal("no contracts embedded; this test would pass vacuously")
	}
	for _, name := range names {
		if _, err := schemas.Get(name); err != nil {
			t.Errorf("%s does not compile: %v", name, err)
		}
	}
	t.Logf("compiled %d contracts: %s", len(names), strings.Join(names, ", "))
}

func TestUnknownContractIsAnError(t *testing.T) {
	if _, err := schemas.Get("invented.schema.json"); err == nil {
		t.Error("Get accepted a contract that does not exist")
	}
	if err := schemas.Validate("invented.schema.json", map[string]any{}); err == nil {
		t.Error("Validate accepted a contract that does not exist")
	}
}

// --- the corpus ------------------------------------------------------------

// Each contract with a testdata directory gets its valid/ files accepted and
// its invalid.json cases refused. A schema that accepts everything passes
// its valid corpus too, which is why the invalid half is the one that
// matters.
func TestCorpus(t *testing.T) {
	entries, err := os.ReadDir(corpus)
	if err != nil {
		t.Fatalf("read corpus: %v", err)
	}
	seen := 0
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		seen++
		contract := e.Name() + ".schema.json"
		t.Run(e.Name(), func(t *testing.T) {
			testValid(t, contract, filepath.Join(corpus, e.Name(), "valid"))
			testInvalid(t, contract, filepath.Join(corpus, e.Name(), "invalid.json"))
		})
	}
	if seen == 0 {
		t.Fatal("no contract corpora found")
	}
}

func testValid(t *testing.T, contract, dir string) {
	t.Helper()
	files, err := filepath.Glob(filepath.Join(dir, "*.json"))
	if err != nil {
		t.Fatalf("glob: %v", err)
	}
	if len(files) == 0 {
		t.Errorf("%s has no valid examples", contract)
	}
	for _, f := range files {
		t.Run("valid/"+filepath.Base(f), func(t *testing.T) {
			raw, err := os.ReadFile(f)
			if err != nil {
				t.Fatal(err)
			}
			if err := schemas.ValidateBytes(contract, raw); err != nil {
				t.Errorf("a valid example was refused:\n%v", err)
			}
		})
	}
}

type invalidCase struct {
	Name     string          `json:"name"`
	Why      string          `json:"why"`
	Pointer  string          `json:"pointer"`
	Instance json.RawMessage `json:"instance"`
}

func testInvalid(t *testing.T, contract, file string) {
	t.Helper()
	raw, err := os.ReadFile(file)
	if err != nil {
		t.Errorf("%s has no invalid corpus: %v", contract, err)
		return
	}
	var cases []invalidCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatalf("parse %s: %v", file, err)
	}
	if len(cases) == 0 {
		t.Errorf("%s has an empty invalid corpus", contract)
	}
	for _, tc := range cases {
		t.Run("invalid/"+tc.Name, func(t *testing.T) {
			if tc.Why == "" {
				t.Error("an invalid case must say why it is invalid, or nobody can review it")
			}
			err := schemas.ValidateBytes(contract, tc.Instance)
			if err == nil {
				t.Fatalf("accepted: %s", tc.Why)
			}
			// The pointer is where a caller will be told to look. An empty
			// expectation means "the document as a whole", which is what a
			// failed conditional reports.
			got := schemas.Pointers(err)
			if !contains(got, tc.Pointer) {
				t.Errorf("error points at %v, expected to include %q", got, tc.Pointer)
			}
		})
	}
}

func contains(xs []string, want string) bool {
	for _, x := range xs {
		if x == want {
			return true
		}
	}
	return false
}

// --- the shared definitions actually bite ---------------------------------

func TestSharedDefinitionsAreEnforced(t *testing.T) {
	// A $ref that resolves to nothing silently accepts everything, which is
	// the worst failure mode a schema has. Exercise each shared definition
	// through a contract that uses it.
	cases := []struct {
		name     string
		mutate   func(map[string]any)
		wantFail bool
	}{
		{"baseline", func(m map[string]any) {}, false},
		{
			"digest without its algorithm prefix",
			func(m map[string]any) { m["manifest_root"] = strings.Repeat("a", 64) },
			true,
		},
		{
			"digest of the wrong length",
			func(m map[string]any) { m["manifest_root"] = "sha256:abc" },
			true,
		},
		{
			"revision of zero",
			func(m map[string]any) { m["revision"] = 0 },
			true,
		},
		{
			"a feature key with spaces",
			func(m map[string]any) { m["feature"] = "not a slug" },
			true,
		},
		{
			"a timestamp that is not one",
			func(m map[string]any) { m["created_at"] = "last tuesday" },
			true,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			m := validManifest()
			tc.mutate(m)
			raw, err := json.Marshal(m)
			if err != nil {
				t.Fatal(err)
			}
			err = schemas.ValidateBytes(schemas.BaselineManifest, raw)
			if tc.wantFail && err == nil {
				t.Error("accepted, so the shared definition is not being applied")
			}
			if !tc.wantFail && err != nil {
				t.Errorf("refused a valid manifest: %v", err)
			}
		})
	}
}

func validManifest() map[string]any {
	return map[string]any{
		"schema":   "idev.baseline-manifest/1",
		"feature":  "demo",
		"revision": 1,
		"files": []any{
			map[string]any{
				"path":            "docs/task/demo/baseline.yaml",
				"mode":            "yaml-fields",
				"fields":          []any{"goal", "items"},
				"semantic_sha256": "sha256:" + strings.Repeat("a", 64),
				"raw_sha256":      "sha256:" + strings.Repeat("b", 64),
				"size":            2311,
			},
		},
		"manifest_root": "sha256:" + strings.Repeat("c", 64),
		"raw_root":      "sha256:" + strings.Repeat("d", 64),
		"repo_head":     "a1b2c3",
		"dirty":         false,
		"created_at":    "2026-10-16T12:00:00Z",
	}
}

func TestYAMLModeRequiresItsFieldList(t *testing.T) {
	// A yaml-fields digest without the field list cannot be interpreted: the
	// same digest means different things depending on which fields went in.
	m := validManifest()
	files := m["files"].([]any)
	entry := files[0].(map[string]any)
	delete(entry, "fields")
	raw, _ := json.Marshal(m)
	if err := schemas.ValidateBytes(schemas.BaselineManifest, raw); err == nil {
		t.Error("a yaml-fields entry with no field list was accepted")
	}
}

func TestKindEnumComesFromTheRegistry(t *testing.T) {
	// The generated enum is what a packet is validated against, so a kind
	// nobody registered cannot appear in one.
	s, err := schemas.Def(schemas.Kinds, "/$defs/kind")
	if err != nil {
		t.Fatal(err)
	}
	for _, kind := range []string{"deliver.code_pass", "human.gate", "git.commit_push"} {
		if err := s.Validate(kindInstance(t, kind)); err != nil {
			t.Errorf("registered kind %q was refused: %v", kind, err)
		}
	}
	if err := s.Validate(kindInstance(t, "deliver.invented")); err == nil {
		t.Error("an unregistered kind was accepted")
	}

	agents, err := schemas.Def(schemas.Kinds, "/$defs/agent")
	if err != nil {
		t.Fatal(err)
	}
	if err := agents.Validate(kindInstance(t, "idev-coder")); err != nil {
		t.Errorf("a registered agent was refused: %v", err)
	}
	if err := agents.Validate(kindInstance(t, "idev-invented")); err == nil {
		t.Error("an unregistered agent was accepted")
	}
}

func TestDefRejectsAMissingPointer(t *testing.T) {
	if _, err := schemas.Def(schemas.Kinds, "/$defs/nope"); err == nil {
		t.Error("Def accepted a pointer that resolves to nothing")
	}
}

// kindInstance validates a bare string against the kind definition by
// wrapping it the way a $ref consumer would.
func kindInstance(t *testing.T, kind string) any {
	t.Helper()
	v, err := jsonschema.UnmarshalJSON(bytes.NewReader([]byte(`"` + kind + `"`)))
	if err != nil {
		t.Fatal(err)
	}
	return v
}

func TestMalformedJSONIsReportedAsSuch(t *testing.T) {
	err := schemas.ValidateBytes(schemas.DelegationReturn, []byte("{not json"))
	if err == nil {
		t.Fatal("malformed JSON was accepted")
	}
	if !strings.Contains(err.Error(), "malformed JSON") {
		t.Errorf("error = %q, should distinguish a parse failure from a contract failure", err)
	}
}

func TestPointersOnANonValidationErrorIsEmpty(t *testing.T) {
	if got := schemas.Pointers(os.ErrNotExist); got != nil {
		t.Errorf("Pointers = %v, want nil for an unrelated error", got)
	}
}
