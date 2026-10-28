package ticketbaseline_test

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/idev/internal/adapters/ticketbaseline"
)

func TestFromTicketStableRoot(t *testing.T) {
	dir := t.TempDir()
	body := "revision: 1\ngoal: same\nnon_goal: x\nitems: []\nboundaries: []\ndetails: {}\n"
	must := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(filepath.Join(dir, "baseline.yaml"), []byte(body), 0o644))
	at := time.Date(2026, 10, 28, 0, 0, 0, 0, time.UTC)
	a, err := ticketbaseline.FromTicket("demo", dir, 0, at)
	must(err)
	b, err := ticketbaseline.FromTicket("demo", dir, 0, at)
	must(err)
	if a.ManifestRoot != b.ManifestRoot || a.ManifestRoot == "" {
		t.Fatalf("roots differ or empty: %q vs %q", a.ManifestRoot, b.ManifestRoot)
	}
}
