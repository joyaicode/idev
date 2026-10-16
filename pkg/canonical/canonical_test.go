package canonical_test

import (
	"strings"
	"testing"

	"pgregory.net/rapid"

	"github.com/idev/pkg/canonical"
)

func TestHashIsPrefixedAndValid(t *testing.T) {
	d := canonical.Hash([]byte("x"))
	if !strings.HasPrefix(string(d), canonical.DigestPrefix) {
		t.Errorf("digest %q has no algorithm prefix", d)
	}
	if len(d.Hex()) != 64 {
		t.Errorf("hex length = %d, want 64", len(d.Hex()))
	}
	if !d.Valid() {
		t.Error("a digest this package produced must validate")
	}
	for _, bad := range []canonical.Digest{
		"", "sha256:", "deadbeef", canonical.Digest("md5:" + d.Hex()), "sha256:zz",
	} {
		if bad.Valid() {
			t.Errorf("Valid() accepted %q", bad)
		}
	}
}

// --- JCS: the point is that formatting does not count ----------------------

func TestJCSIgnoresKeyOrder(t *testing.T) {
	a := map[string]any{"goal": "x", "items": []any{"1", "2"}}
	b := map[string]any{"items": []any{"1", "2"}, "goal": "x"}
	da, err := canonical.HashJCS(a)
	if err != nil {
		t.Fatal(err)
	}
	db, err := canonical.HashJCS(b)
	if err != nil {
		t.Fatal(err)
	}
	if da != db {
		t.Error("key order changed the digest; re-serialising a baseline would read as a change")
	}
}

func TestJCSSortsKeysPerRFC8785(t *testing.T) {
	b, err := canonical.JCS(map[string]any{"b": 1, "a": 2, "C": 3})
	if err != nil {
		t.Fatal(err)
	}
	// Sorted by UTF-16 code unit, so uppercase sorts before lowercase.
	if got := string(b); got != `{"C":3,"a":2,"b":1}` {
		t.Errorf("JCS = %s, want {\"C\":3,\"a\":2,\"b\":1}", got)
	}
}

func TestJCSDistinguishesRealChanges(t *testing.T) {
	a, _ := canonical.HashJCS(map[string]any{"goal": "export users"})
	b, _ := canonical.HashJCS(map[string]any{"goal": "export orders"})
	if a == b {
		t.Fatal("a changed requirement must change the digest")
	}
	// Nesting and order inside arrays still count: a reordered list of
	// requirement items is a different agreement.
	c, _ := canonical.HashJCS(map[string]any{"items": []any{"a", "b"}})
	d, _ := canonical.HashJCS(map[string]any{"items": []any{"b", "a"}})
	if c == d {
		t.Error("array order must count; items are ordered requirements")
	}
}

func TestJCSRefusesUnrepresentableValues(t *testing.T) {
	if _, err := canonical.JCS(func() {}); err == nil {
		t.Error("a value JSON cannot represent must be an error, not a silent digest")
	}
}

// --- text normalisation ----------------------------------------------------

func TestNormalizeTextFoldsEditorNoise(t *testing.T) {
	cases := []struct{ name, in, want string }{
		{"crlf", "a\r\nb\r\n", "a\nb\n"},
		{"cr", "a\rb\r", "a\nb\n"},
		{"trailing spaces", "a   \nb\t\n", "a\nb\n"},
		{"many trailing newlines", "a\n\n\n\n", "a\n"},
		{"no trailing newline", "a", "a\n"},
		{"empty", "", ""},
		{"only newlines", "\n\n\n", ""},
		{"interior blank line kept", "a\n\nb\n", "a\n\nb\n"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := string(canonical.NormalizeText([]byte(tc.in))); got != tc.want {
				t.Errorf("NormalizeText(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}

func TestNormalizeTextAppliesNFC(t *testing.T) {
	// e + combining acute, versus the precomposed character. The same text
	// as far as a reader is concerned, and two different byte strings.
	decomposed := "café\n"
	precomposed := "café\n"
	if canonical.HashText([]byte(decomposed)) != canonical.HashText([]byte(precomposed)) {
		t.Error("NFC was not applied; the same prose in two encodings read as a change")
	}
}

func TestHashTextDetectsRealEdits(t *testing.T) {
	a := canonical.HashText([]byte("export users\n"))
	b := canonical.HashText([]byte("export orders\n"))
	if a == b {
		t.Fatal("edited prose must change the digest")
	}
}

// --- the manifest root -----------------------------------------------------

func TestRootIsOrderIndependent(t *testing.T) {
	lines := []canonical.Line{
		{Path: "b.md", Digest: canonical.Hash([]byte("b"))},
		{Path: "a.md", Digest: canonical.Hash([]byte("a"))},
	}
	reversed := []canonical.Line{lines[1], lines[0]}
	if canonical.Root(lines) != canonical.Root(reversed) {
		t.Error("the root depends on input order; two machines would disagree")
	}
}

func TestRootDoesNotMutateItsInput(t *testing.T) {
	lines := []canonical.Line{
		{Path: "b.md", Digest: canonical.Hash([]byte("b"))},
		{Path: "a.md", Digest: canonical.Hash([]byte("a"))},
	}
	canonical.Root(lines)
	if lines[0].Path != "b.md" {
		t.Error("Root sorted the caller's slice")
	}
}

func TestRootInputIsReproducibleBySha256sum(t *testing.T) {
	// The format is sha256sum's, so a person can re-derive the root without
	// trusting this tool. That property is the reason for the two spaces.
	da := canonical.Hash([]byte("a"))
	db := canonical.Hash([]byte("b"))
	got := string(canonical.RootInput([]canonical.Line{
		{Path: "z.md", Digest: db}, {Path: "a.md", Digest: da},
	}))
	want := da.Hex() + "  a.md\n" + db.Hex() + "  z.md\n"
	if got != want {
		t.Errorf("RootInput =\n%q\nwant\n%q", got, want)
	}
	if canonical.Hash([]byte(got)) != canonical.Root([]canonical.Line{
		{Path: "z.md", Digest: db}, {Path: "a.md", Digest: da},
	}) {
		t.Error("Root is not the hash of RootInput; the published recipe would be wrong")
	}
}

func TestRootChangesWhenAnyFileChanges(t *testing.T) {
	base := []canonical.Line{
		{Path: "a.md", Digest: canonical.Hash([]byte("a"))},
		{Path: "b.md", Digest: canonical.Hash([]byte("b"))},
	}
	root := canonical.Root(base)

	edited := []canonical.Line{base[0], {Path: "b.md", Digest: canonical.Hash([]byte("b2"))}}
	if canonical.Root(edited) == root {
		t.Error("editing a file did not change the root")
	}
	renamed := []canonical.Line{base[0], {Path: "c.md", Digest: base[1].Digest}}
	if canonical.Root(renamed) == root {
		t.Error("renaming a file did not change the root; the path is part of the seal")
	}
	removed := []canonical.Line{base[0]}
	if canonical.Root(removed) == root {
		t.Error("removing a file did not change the root")
	}
}

func TestEmptyRootIsStable(t *testing.T) {
	if canonical.Root(nil) != canonical.Root([]canonical.Line{}) {
		t.Error("nil and empty must agree")
	}
}

// --- properties ------------------------------------------------------------

// Normalisation must be idempotent. If it were not, re-sealing unchanged
// content could produce a different digest and look like drift.
func TestPropertyNormalizeTextIsIdempotent(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		raw := []byte(rapid.String().Draw(t, "text"))
		once := canonical.NormalizeText(raw)
		twice := canonical.NormalizeText(once)
		if string(once) != string(twice) {
			t.Fatalf("not idempotent: %q -> %q -> %q", raw, once, twice)
		}
		if len(once) > 0 && once[len(once)-1] != '\n' {
			t.Fatalf("normalised text does not end in a newline: %q", once)
		}
		if strings.Contains(string(once), "\r") {
			t.Fatalf("carriage return survived: %q", once)
		}
		for _, line := range strings.Split(strings.TrimSuffix(string(once), "\n"), "\n") {
			if line != strings.TrimRight(line, " \t") {
				t.Fatalf("trailing whitespace survived in %q", line)
			}
		}
	})
}

// The root is a pure function of the set of (path, digest) pairs.
func TestPropertyRootDependsOnlyOnTheSet(t *testing.T) {
	rapid.Check(t, func(t *rapid.T) {
		n := rapid.IntRange(0, 8).Draw(t, "files")
		lines := make([]canonical.Line, 0, n)
		seen := map[string]bool{}
		for i := 0; i < n; i++ {
			path := rapid.SampledFrom([]string{"a", "b", "c", "d", "e", "f", "g", "h"}).Draw(t, "path")
			if seen[path] {
				continue
			}
			seen[path] = true
			lines = append(lines, canonical.Line{
				Path:   path,
				Digest: canonical.Hash([]byte(rapid.String().Draw(t, "content"))),
			})
		}
		shuffled := make([]canonical.Line, len(lines))
		copy(shuffled, lines)
		for i := range shuffled {
			j := rapid.IntRange(0, len(shuffled)-1).Draw(t, "swap")
			shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
		}
		if canonical.Root(lines) != canonical.Root(shuffled) {
			t.Fatal("the root changed under reordering")
		}
	})
}
