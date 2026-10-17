package ulid

import (
	"math/big"
	"strings"
	"testing"
	"time"
)

// Fixed vectors produced independently, not by calling Encode. The first is
// the all-zeros sentinel; the second was computed by hand from the Python
// implementation (ids.ulid with secrets.randbits patched to return known
// values).
func TestEncodeVectors(t *testing.T) {
	if got := Encode(big.NewInt(0)); got != "00000000000000000000000000" {
		t.Fatalf("zero: got %q", got)
	}
	one := Encode(big.NewInt(1))
	if one != "00000000000000000000000001" {
		t.Fatalf("one: got %q", one)
	}
	// 31 encodes to the last alphabet character in the last position.
	v := Encode(big.NewInt(31))
	if v != "0000000000000000000000000Z" {
		t.Fatalf("31: got %q", v)
	}
	// 32 carries into the second position.
	v = Encode(big.NewInt(32))
	if v != "00000000000000000000000010" {
		t.Fatalf("32: got %q", v)
	}
	// Time-only: ms=1 -> 1<<80. Character i covers bits [5*(25-i), ...), so
	// bit 80 lands in character 9: nine leading zeros, then a 1.
	v = Encode(new(big.Int).Lsh(big.NewInt(1), 80))
	if !strings.HasPrefix(v, "0000000001") || len(v) != Len {
		t.Fatalf("1<<80: got %q", v)
	}
	if v[25] != '0' {
		t.Fatalf("1<<80 should end in 0 (16 zero bits), got %q", v)
	}

	// Cross-implementation vector: computed by ids.ulid() with ms and
	// randbits fixed (see scripts/lib/ids.py). If this ever fails, one of
	// the two encoders stopped agreeing, and run.yaml ids written by Python
	// would not parse as what Go expects.
	ms := new(big.Int).SetInt64(1760659200000)
	rand := new(big.Int).SetBytes([]byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A})
	v = Encode(new(big.Int).Or(new(big.Int).Lsh(ms, 80), rand))
	if v != "01K7QQEP00041061050R3GG28A" {
		t.Fatalf("python vector: got %q", v)
	}
}

func TestNewShape(t *testing.T) {
	s, err := NewAt(time.Date(2026, 10, 16, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if !Valid(s) {
		t.Fatalf("Valid(%q) = false", s)
	}
	// Same timestamp twice: the 80 random bits must differ.
	s2, err := NewAt(time.Date(2026, 10, 16, 0, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if s == s2 {
		t.Fatal("two fresh ULIDs at the same millisecond collided")
	}
	// The first ten chars are the millisecond: equal ms, equal prefix.
	if s[:10] != s2[:10] {
		t.Fatalf("same-ms prefix differs: %q vs %q", s[:10], s2[:10])
	}
}

func TestValid(t *testing.T) {
	for _, bad := range []string{
		"", "short", "0000000000000000000000000", "000000000000000000000000000",
		"0000000000000000000000000I", "0000000000000000000000000O", "0000000000000000000000000L",
		"0000000000000000000000000U", "0000000000000000000000000a",
	} {
		if Valid(bad) {
			t.Errorf("Valid(%q) = true", bad)
		}
	}
}

func TestNewRefusesOverflow(t *testing.T) {
	if _, err := New(1 << 48); err == nil {
		t.Fatal("expected overflow error")
	}
}
