// Package ticketbaseline builds a baseline.Manifest from a ticket directory.
//
// The sealed fields of baseline.yaml are the content fingerprint (I-4).
// One file, no IO beyond the ticket. Full ticket+details hashing and
// locate/diff live in adapters/workspace (E5.5); FromTicket there keeps
// the same ManifestRoot when details[] adds no readable files.
package ticketbaseline

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/idev/internal/domain/baseline"
	"go.yaml.in/yaml/v3"
)

// FromTicket reads baseline.yaml under ticketDir and builds a manifest for
// feature at the revision recorded in the file (or overrideRev when > 0).
func FromTicket(feature, ticketDir string, overrideRev int, now time.Time) (baseline.Manifest, error) {
	path := filepath.Join(ticketDir, "baseline.yaml")
	raw, err := os.ReadFile(path)
	if err != nil {
		return baseline.Manifest{}, fmt.Errorf("ticketbaseline: reading %s: %w", path, err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		return baseline.Manifest{}, fmt.Errorf("ticketbaseline: parsing %s: %w", path, err)
	}
	rev := overrideRev
	if rev <= 0 {
		rev = asInt(doc["revision"])
	}
	if rev <= 0 {
		return baseline.Manifest{}, fmt.Errorf("ticketbaseline: baseline.yaml needs a positive revision")
	}
	entry, err := baseline.YAMLFile("baseline.yaml", raw, doc, nil)
	if err != nil {
		return baseline.Manifest{}, err
	}
	return baseline.Build(feature, rev, []baseline.File{entry}, "", false, now)
}

func asInt(v any) int {
	switch x := v.(type) {
	case int:
		return x
	case int64:
		return int(x)
	case float64:
		return int(x)
	case string:
		n, _ := strconv.Atoi(x)
		return n
	default:
		return 0
	}
}
