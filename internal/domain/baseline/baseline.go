// Package baseline turns a sealed requirement into a content fingerprint,
// and detects when the content moves afterwards.
//
// The problem it solves is review §3.3: `sealed: true` was a boolean, so
// "the baseline is sealed" and "the baseline still says what was agreed"
// were different facts and only the first was checked. Signing and then
// editing left no trace. A manifest of per-file digests, with the approval
// bound to the root, makes the second fact checkable — and cheap enough to
// re-check on every stage check and every delegation acceptance (§11.3).
//
// The distinction that makes it usable is semantic versus raw. Re-indenting
// a YAML file changes its bytes and not its meaning; the semantic digest
// ignores that, the raw digest records it. So a formatting change is a WARN
// and a changed requirement is a blocked run.
//
// Zero IO: file reading and YAML parsing happen in the workspace adapter,
// which hands this package the parsed document and the raw bytes.
package baseline

import (
	"fmt"
	"sort"
	"time"

	"github.com/idev/pkg/canonical"
)

// Schema is the manifest's schema identifier, as written to disk.
const Schema = "idev.baseline-manifest/1"

// SealedFields are the baseline fields a seal covers.
//
// review_questions and objections are deliberately out: deliver-schema.md
// requires them emptied before sealing, so including them would make the
// digest depend on scratch work rather than on the agreement.
var SealedFields = []string{"goal", "non_goal", "items", "boundaries", "details"}

// Mode says how a file's semantic digest was computed.
type Mode string

// The two modes.
const (
	// ModeYAMLFields digests only the sealed fields of a YAML document, so
	// formatting and unrelated keys do not count.
	ModeYAMLFields Mode = "yaml-fields"
	// ModeTextNormalized digests prose after NFC, LF and trailing-whitespace
	// normalisation.
	ModeTextNormalized Mode = "text-normalized"
)

// File is one entry in a manifest.
type File struct {
	Path     string           `json:"path"`
	Mode     Mode             `json:"mode"`
	Fields   []string         `json:"fields,omitempty"`
	Semantic canonical.Digest `json:"semantic_sha256"`
	Raw      canonical.Digest `json:"raw_sha256"`
	Size     int              `json:"size"`
}

// Manifest is the fingerprint of one baseline revision.
type Manifest struct {
	Schema       string           `json:"schema"`
	Feature      string           `json:"feature"`
	Revision     int              `json:"revision"`
	Files        []File           `json:"files"`
	ManifestRoot canonical.Digest `json:"manifest_root"`
	RawRoot      canonical.Digest `json:"raw_root"`
	RepoHead     string           `json:"repo_head"`
	Dirty        bool             `json:"dirty"`
	CreatedAt    time.Time        `json:"created_at"`
}

// SemanticYAML digests the sealed fields of a parsed YAML document.
//
// `doc` is the document as the adapter parsed it, with YAML-specific types
// already converted to JSON-representable ones. Missing fields are omitted
// rather than recorded as null: a baseline that never had `non_goal` and one
// where it was deleted are different, and the second is a change worth
// catching — which is why the field list is recorded in the manifest
// alongside the digest.
func SemanticYAML(doc map[string]any, fields []string) (canonical.Digest, []string, error) {
	if len(fields) == 0 {
		fields = SealedFields
	}
	subset := map[string]any{}
	var present []string
	for _, f := range fields {
		if v, ok := doc[f]; ok {
			subset[f] = v
			present = append(present, f)
		}
	}
	d, err := canonical.HashJCS(subset)
	if err != nil {
		return "", nil, fmt.Errorf("baseline: %w", err)
	}
	return d, present, nil
}

// YAMLFile builds a manifest entry for a YAML document.
func YAMLFile(path string, raw []byte, doc map[string]any, fields []string) (File, error) {
	semantic, present, err := SemanticYAML(doc, fields)
	if err != nil {
		return File{}, err
	}
	return File{
		Path: path, Mode: ModeYAMLFields, Fields: present,
		Semantic: semantic, Raw: canonical.Hash(raw), Size: len(raw),
	}, nil
}

// TextFile builds a manifest entry for prose.
func TextFile(path string, raw []byte) File {
	return File{
		Path: path, Mode: ModeTextNormalized,
		Semantic: canonical.HashText(raw), Raw: canonical.Hash(raw), Size: len(raw),
	}
}

// Build assembles a manifest and computes both roots.
func Build(feature string, revision int, files []File, repoHead string, dirty bool, now time.Time) (Manifest, error) {
	if feature == "" {
		return Manifest{}, fmt.Errorf("baseline: a manifest names its feature")
	}
	if revision <= 0 {
		return Manifest{}, fmt.Errorf("baseline: revision must be positive, got %d", revision)
	}
	if len(files) == 0 {
		return Manifest{}, fmt.Errorf("baseline: a manifest over no files seals nothing")
	}
	seen := map[string]bool{}
	semanticLines := make([]canonical.Line, 0, len(files))
	rawLines := make([]canonical.Line, 0, len(files))
	for _, f := range files {
		if f.Path == "" {
			return Manifest{}, fmt.Errorf("baseline: a manifest entry has no path")
		}
		if seen[f.Path] {
			return Manifest{}, fmt.Errorf("baseline: %s appears twice", f.Path)
		}
		seen[f.Path] = true
		if !f.Semantic.Valid() || !f.Raw.Valid() {
			return Manifest{}, fmt.Errorf("baseline: %s has an unusable digest", f.Path)
		}
		semanticLines = append(semanticLines, canonical.Line{Path: f.Path, Digest: f.Semantic})
		rawLines = append(rawLines, canonical.Line{Path: f.Path, Digest: f.Raw})
	}

	sorted := make([]File, len(files))
	copy(sorted, files)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].Path < sorted[j].Path })

	return Manifest{
		Schema: Schema, Feature: feature, Revision: revision, Files: sorted,
		ManifestRoot: canonical.Root(semanticLines),
		RawRoot:      canonical.Root(rawLines),
		RepoHead:     repoHead, Dirty: dirty, CreatedAt: now,
	}, nil
}

// Verdict is the result of comparing a sealed manifest with the content now.
type Verdict string

// The verdicts. format_only and drift are deliberately different: one is a
// WARN and the other blocks the run (§11.3).
const (
	// VerdictIntact means both roots match: nothing changed at all.
	VerdictIntact Verdict = "intact"
	// VerdictFormatOnly means the meaning is unchanged but the bytes are
	// not — a reformat, a line-ending change, a re-quote.
	VerdictFormatOnly Verdict = "format_only"
	// VerdictDrift means a sealed field changed. The run blocks.
	VerdictDrift Verdict = "drift"
	// VerdictUnsealed means there is nothing to compare against.
	VerdictUnsealed Verdict = "unsealed"
)

// Change describes one file's difference.
type Change struct {
	Path string
	// Kind is "added", "removed", "changed" or "reformatted".
	Kind string
	Was  canonical.Digest
	Now  canonical.Digest
}

// Comparison is the full answer to "does the seal still hold".
type Comparison struct {
	Verdict Verdict
	Changes []Change
	// Line is the message the old CLI prints, so the conductor and the
	// golden files keep seeing the same shape.
	Line string
}

// Compare checks the content now against what was sealed.
//
// Ordering matters: a semantic difference anywhere makes the whole thing
// drift, regardless of how many files merely reformatted.
func Compare(sealed, current Manifest) Comparison {
	if sealed.ManifestRoot == "" {
		return Comparison{Verdict: VerdictUnsealed, Line: "OK   baseline is not sealed"}
	}
	if sealed.ManifestRoot == current.ManifestRoot && sealed.RawRoot == current.RawRoot {
		return Comparison{Verdict: VerdictIntact, Line: "OK   baseline intact"}
	}

	was := map[string]File{}
	for _, f := range sealed.Files {
		was[f.Path] = f
	}
	now := map[string]File{}
	for _, f := range current.Files {
		now[f.Path] = f
	}

	var changes []Change
	drifted := false
	for path, old := range was {
		cur, ok := now[path]
		if !ok {
			changes = append(changes, Change{Path: path, Kind: "removed", Was: old.Semantic})
			drifted = true
			continue
		}
		switch {
		case old.Semantic != cur.Semantic:
			changes = append(changes, Change{
				Path: path, Kind: "changed", Was: old.Semantic, Now: cur.Semantic,
			})
			drifted = true
		case old.Raw != cur.Raw:
			changes = append(changes, Change{
				Path: path, Kind: "reformatted", Was: old.Raw, Now: cur.Raw,
			})
		}
	}
	for path, cur := range now {
		if _, ok := was[path]; !ok {
			changes = append(changes, Change{Path: path, Kind: "added", Now: cur.Semantic})
			drifted = true
		}
	}
	sort.Slice(changes, func(i, j int) bool { return changes[i].Path < changes[j].Path })

	if drifted {
		first := ""
		for _, c := range changes {
			if c.Kind != "reformatted" {
				first = c.Path
				break
			}
		}
		return Comparison{
			Verdict: VerdictDrift,
			Changes: changes,
			Line:    fmt.Sprintf("BLOCKED baseline-drift %s (sealed rev %d)", first, sealed.Revision),
		}
	}
	return Comparison{
		Verdict: VerdictFormatOnly,
		Changes: changes,
		Line:    fmt.Sprintf("WARN format-only change (%d file(s), sealed rev %d)", len(changes), sealed.Revision),
	}
}

// Intact reports whether a comparison allows the run to continue. A
// format-only change does.
func (c Comparison) Intact() bool {
	return c.Verdict == VerdictIntact || c.Verdict == VerdictFormatOnly
}
