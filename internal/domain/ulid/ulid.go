// Package ulid is the ID the repo's records are named by.
//
// One encode, not a grab-bag: 48 bits of millisecond time, 80 bits of
// randomness, Crockford base32, 26 characters — the same alphabet and layout
// as scripts/lib/ids.py, because run.yaml files and gate ids written by one
// side are parsed and compared by the other while both exist. An id a human
// has to read back over the phone cannot contain I, L, O or U; Crockford is
// the reason.
//
// Zero IO per the domain rules: the randomness source is an argument.
package ulid

import (
	"crypto/rand"
	"fmt"
	"math/big"
	"time"
)

// Crockford base32, in value order. No I, L, O or U.
const alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

// Len is the fixed length of an encoded ULID.
const Len = 26

var base = big.NewInt(32)

// Encode renders a 128-bit value as 26 Crockford characters, least
// significant character last.
//
// big.Int is not an accident: a ULID is 130 bits nominally, so 64-bit
// shuffling turns into the kind of code this package's doc comment says not
// to write. An id is produced once per record; 130 bytes of scratch is not
// the bottleneck.
//
// Parsing is deliberately absent: nothing in this codebase reads an id
// apart from comparing it whole, and a decoder is an invitation to treat
// ids as numbers.
func Encode(v *big.Int) string {
	var out [Len]byte
	r := new(big.Int)
	n := new(big.Int).Set(v)
	for i := Len - 1; i >= 0; i-- {
		n.QuoRem(n, base, r)
		out[i] = alphabet[r.Int64()]
	}
	return string(out[:])
}

// New renders a fresh ULID for `ms` milliseconds since the epoch: 48 bits
// of time followed by 80 bits of randomness, matching ids.ulid() exactly.
func New(ms uint64) (string, error) {
	if ms >= 1<<48 {
		return "", fmt.Errorf("ulid: time %d overflows 48 bits", ms)
	}
	var b [10]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", fmt.Errorf("ulid: random source: %w", err)
	}
	v := new(big.Int).SetUint64(ms)
	v.Lsh(v, 80)
	v.Or(v, new(big.Int).SetBytes(b[:]))
	return Encode(v), nil
}

// NewAt is New for a specific time, for tests.
func NewAt(t time.Time) (string, error) {
	return New(uint64(t.UnixMilli()))
}

// Valid reports whether s has the shape of a ULID. Mirror of ids.is_ulid:
// 26 characters, all in the alphabet.
func Valid(s string) bool {
	if len(s) != Len {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		ok := c >= '0' && c <= '9' || c >= 'A' && c <= 'H' || c >= 'J' && c <= 'K' ||
			c >= 'M' && c <= 'N' || c >= 'P' && c <= 'T' || c >= 'V' && c <= 'Z'
		if !ok {
			return false
		}
	}
	return true
}
