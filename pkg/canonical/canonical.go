// Package canonical turns values and file contents into stable bytes, so a
// digest of them means something across machines, formatters and YAML
// styles.
//
// It exists because "sealed: true" is not a seal. The old baseline was a
// boolean: once set, the text under it could be edited freely and nothing
// noticed (review §3.3). A seal has to be a fingerprint of content, and a
// fingerprint is only useful if re-computing it tomorrow, on another
// machine, gives the same answer — which is what canonicalisation buys.
//
// Two normalisations, because two kinds of equality matter:
//
//   - RFC 8785 JCS for structured data, so re-indenting a YAML file, quoting
//     a string differently or reordering keys does not read as a change to
//     the requirement.
//   - A text normalisation for prose, so CRLF, a trailing blank line or
//     stripped trailing spaces do not either.
//
// This package is in pkg/ because an auditor needs to verify a seal without
// running idevd: the same functions back `idev gate verify`.
package canonical

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/gowebpki/jcs"
	"golang.org/x/text/unicode/norm"
)

// DigestPrefix is carried in every digest string so a bare hex value can
// never be mistaken for a digest of a different algorithm.
const DigestPrefix = "sha256:"

// Digest is a prefixed hex sha256, e.g. "sha256:2b7e1516…".
type Digest string

// Hash returns the digest of raw bytes.
func Hash(b []byte) Digest {
	sum := sha256.Sum256(b)
	return Digest(DigestPrefix + hex.EncodeToString(sum[:]))
}

// Hex is the digest without its prefix, for formats that want bare hex.
func (d Digest) Hex() string { return strings.TrimPrefix(string(d), DigestPrefix) }

// Valid reports whether d looks like a sha256 digest this package produced.
func (d Digest) Valid() bool {
	hexPart := d.Hex()
	if len(hexPart) != 64 || !strings.HasPrefix(string(d), DigestPrefix) {
		return false
	}
	_, err := hex.DecodeString(hexPart)
	return err == nil
}

// JCS canonicalises a value per RFC 8785: object keys sorted by their UTF-16
// code units, no insignificant whitespace, one spelling per number.
//
// The value is marshalled with encoding/json first, so it must be
// JSON-representable. YAML documents are converted by the caller (the
// adapter that parsed them), which keeps this package free of a YAML
// dependency and keeps the YAML dialect decision in one place.
func JCS(v any) ([]byte, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return nil, fmt.Errorf("canonical: marshal: %w", err)
	}
	out, err := jcs.Transform(raw)
	if err != nil {
		return nil, fmt.Errorf("canonical: jcs: %w", err)
	}
	return out, nil
}

// HashJCS is JCS followed by Hash: the digest of a structured value.
func HashJCS(v any) (Digest, error) {
	b, err := JCS(v)
	if err != nil {
		return "", err
	}
	return Hash(b), nil
}

// NormalizeText is the prose normalisation: NFC, LF line endings, no
// trailing whitespace on any line, exactly one newline at end of file.
//
// Each of these is a difference an editor introduces without anyone deciding
// anything. A seal that breaks when someone's editor strips a trailing space
// is a seal people learn to ignore.
func NormalizeText(raw []byte) []byte {
	s := norm.NFC.String(string(raw))
	s = strings.ReplaceAll(s, "\r\n", "\n")
	s = strings.ReplaceAll(s, "\r", "\n")

	lines := strings.Split(s, "\n")
	for i, line := range lines {
		lines[i] = strings.TrimRight(line, " \t")
	}
	s = strings.Join(lines, "\n")
	s = strings.TrimRight(s, "\n")
	if s == "" {
		return []byte{}
	}
	return []byte(s + "\n")
}

// HashText normalises prose and returns its digest.
func HashText(raw []byte) Digest { return Hash(NormalizeText(raw)) }

// Line is one row of a manifest: a path and the digest of its content.
type Line struct {
	Path   string
	Digest Digest
}

// Root combines per-file digests into one.
//
// The line format is sha256sum's — "<hex>  <path>\n" — on purpose: a person
// who distrusts the tool can reproduce the root with `sha256sum` and `sort`,
// which is the difference between a verifiable seal and a number the tool
// asserts.
//
// Sorting is by path, byte-wise, so the order does not depend on the
// filesystem or the locale.
func Root(lines []Line) Digest {
	sorted := make([]Line, len(lines))
	copy(sorted, lines)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].Path < sorted[j].Path })

	var sb strings.Builder
	for _, l := range sorted {
		sb.WriteString(l.Digest.Hex())
		sb.WriteString("  ")
		sb.WriteString(l.Path)
		sb.WriteString("\n")
	}
	return Hash([]byte(sb.String()))
}

// RootInput renders exactly the bytes Root hashes, so `idev baseline show`
// can print what a person would feed to sha256sum.
func RootInput(lines []Line) []byte {
	sorted := make([]Line, len(lines))
	copy(sorted, lines)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].Path < sorted[j].Path })

	var sb strings.Builder
	for _, l := range sorted {
		sb.WriteString(l.Digest.Hex())
		sb.WriteString("  ")
		sb.WriteString(l.Path)
		sb.WriteString("\n")
	}
	return []byte(sb.String())
}
