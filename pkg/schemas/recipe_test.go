package schemas_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"go.yaml.in/yaml/v3"

	"github.com/idev/pkg/schemas"
)

// The kernel's own recipes, which workflow-check.sh validates with the
// Python rules. Both validators are live during the migration, so a recipe
// one accepts and the other rejects is worse than either rule alone — this
// is the test that keeps them agreeing on real data rather than on examples
// written to fit.
const recipeDir = "../../workflows"

func TestEveryKernelRecipeMatchesTheContract(t *testing.T) {
	files, err := filepath.Glob(filepath.Join(recipeDir, "*.yaml"))
	if err != nil {
		t.Fatalf("glob: %v", err)
	}
	if len(files) == 0 {
		t.Fatal("no recipes found; this test would pass vacuously")
	}

	for _, f := range files {
		t.Run(filepath.Base(f), func(t *testing.T) {
			raw, err := os.ReadFile(f)
			if err != nil {
				t.Fatal(err)
			}
			if err := schemas.ValidateBytes("recipe.schema.json", toJSON(t, raw)); err != nil {
				t.Errorf("a shipped recipe does not match the contract:\n%v", err)
			}
		})
	}
	t.Logf("validated %d recipes", len(files))
}

func TestRecipeContractRefusesWhatThePythonCheckerRefuses(t *testing.T) {
	cases := []struct {
		name string
		yaml string
	}{
		{
			name: "a forbidden kind",
			yaml: "schema_version: 1\nid: bad\nsummary: x\nsteps:\n  - {id: a, kind: auto.seal}\n",
		},
		{
			name: "an unknown kind",
			yaml: "schema_version: 1\nid: bad\nsummary: x\nsteps:\n  - {id: a, kind: no.such.kind}\n",
		},
		{
			name: "no steps",
			yaml: "schema_version: 1\nid: bad\nsummary: x\nsteps: []\n",
		},
		{
			name: "an unknown top-level field",
			yaml: "schema_version: 1\nid: bad\nsummary: x\nskip_signoff: true\nsteps:\n  - {id: a, kind: human.gate, with: {will_write: []}}\n",
		},
		{
			name: "wrong schema version",
			yaml: "schema_version: 2\nid: bad\nsummary: x\nsteps:\n  - {id: a, kind: human.gate, with: {will_write: []}}\n",
		},
		{
			name: "a gate that cannot say what it writes",
			yaml: "schema_version: 1\nid: bad\nsummary: x\nsteps:\n  - {id: a, kind: human.gate, label: 请确认}\n",
		},
		{
			name: "verify.plan with no mode",
			yaml: "schema_version: 1\nid: bad\nsummary: x\nsteps:\n  - {id: a, kind: verify.plan}\n",
		},
		{
			name: "from=default with no default",
			yaml: "schema_version: 1\nid: bad\nsummary: x\nparams:\n  - {name: mode, from: default}\nsteps:\n  - {id: a, kind: route.s4}\n",
		},
		{
			name: "an uppercase id",
			yaml: "schema_version: 1\nid: Bad-Recipe\nsummary: x\nsteps:\n  - {id: a, kind: route.s4}\n",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := schemas.ValidateBytes("recipe.schema.json", toJSON(t, []byte(tc.yaml)))
			if err == nil {
				t.Error("accepted a recipe the Python checker refuses")
			}
		})
	}
}

func TestGateWithWillWriteOrTheOldLabelBothPass(t *testing.T) {
	// The old rule let a gate declare its fields in the label text. Recipes
	// written either way still exist, so both have to validate.
	for _, body := range []string{
		"schema_version: 1\nid: ok\nsummary: x\nsteps:\n  - {id: g, kind: human.gate, with: {will_write: [\"deliver.aligned\"]}}\n",
		"schema_version: 1\nid: ok\nsummary: x\nsteps:\n  - {id: g, kind: human.gate, label: \"将代写: deliver.aligned\"}\n",
	} {
		if err := schemas.ValidateBytes("recipe.schema.json", toJSON(t, []byte(body))); err != nil {
			t.Errorf("a valid gate shape was refused:\n%v", err)
		}
	}
}

// toJSON converts YAML to the primitives jsonschema validates against.
// Round-tripping through encoding/json normalises number types, which YAML
// decodes as int and JSON Schema expects as float64.
func toJSON(t *testing.T, raw []byte) []byte {
	t.Helper()
	var v any
	if err := yaml.Unmarshal(raw, &v); err != nil {
		t.Fatalf("parse yaml: %v", err)
	}
	out, err := json.Marshal(v)
	if err != nil {
		t.Fatalf("re-encode as json: %v", err)
	}
	return out
}
