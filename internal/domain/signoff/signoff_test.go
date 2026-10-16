package signoff_test

import (
	"os"
	"path/filepath"
	"testing"

	"go.yaml.in/yaml/v3"

	"github.com/idev/internal/domain/signoff"
)

// The same file scripts/test_signoff.py reads. Two implementations, one set
// of expectations: if they ever disagree on a row, the signoff gate has
// stopped being one rule (design §20.2).
const casesPath = "../../../test/signoff/cases.yaml"

type confirmCase struct {
	Quote    string `yaml:"quote"`
	GateType string `yaml:"gate_type"`
	Origin   string `yaml:"origin"`
	OK       bool   `yaml:"ok"`
	Reason   string `yaml:"reason"`
}

type rejectCase struct {
	Quote string `yaml:"quote"`
	OK    bool   `yaml:"ok"`
}

type humanCase struct {
	Name string `yaml:"name"`
	OK   bool   `yaml:"ok"`
}

type cases struct {
	Mode    string        `yaml:"mode"`
	Confirm []confirmCase `yaml:"confirm"`
	Reject  []rejectCase  `yaml:"reject"`
	Human   []humanCase   `yaml:"human"`
}

func load(t *testing.T) cases {
	t.Helper()
	raw, err := os.ReadFile(filepath.Clean(casesPath))
	if err != nil {
		t.Fatalf("read shared cases: %v", err)
	}
	var c cases
	if err := yaml.Unmarshal(raw, &c); err != nil {
		t.Fatalf("parse shared cases: %v", err)
	}
	if len(c.Confirm) == 0 || len(c.Human) == 0 {
		t.Fatal("shared cases file is empty; the parity test would pass vacuously")
	}
	return c
}

func TestSharedConfirmCases(t *testing.T) {
	c := load(t)
	for _, tc := range c.Confirm {
		t.Run(tc.Quote+"/"+tc.GateType, func(t *testing.T) {
			got := signoff.ParseConfirm(tc.Quote, signoff.GateType(tc.GateType), tc.Origin)
			if got.OK != tc.OK {
				t.Errorf("ParseConfirm(%q, %q, %q).OK = %v, want %v",
					tc.Quote, tc.GateType, tc.Origin, got.OK, tc.OK)
			}
			if string(got.Reason) != tc.Reason {
				t.Errorf("ParseConfirm(%q).Reason = %q, want %q", tc.Quote, got.Reason, tc.Reason)
			}
		})
	}
}

func TestSharedRejectCases(t *testing.T) {
	c := load(t)
	for _, tc := range c.Reject {
		t.Run(tc.Quote, func(t *testing.T) {
			if got := signoff.IsReject(tc.Quote); got != tc.OK {
				t.Errorf("IsReject(%q) = %v, want %v", tc.Quote, got, tc.OK)
			}
		})
	}
}

func TestSharedHumanCases(t *testing.T) {
	c := load(t)
	if c.Mode != "blacklist-only" {
		t.Fatalf("cases.yaml mode = %q; the human rows assume blacklist-only", c.Mode)
	}
	id := signoff.BlacklistOnly(
		"idev-deliver", "idev-coder", "idev-reviewer", "idev-verifier", "idev-ops",
	)
	for _, tc := range c.Human {
		t.Run(tc.Name, func(t *testing.T) {
			if got := id.IsHuman(tc.Name); got != tc.OK {
				t.Errorf("IsHuman(%q) = %v, want %v", tc.Name, got, tc.OK)
			}
		})
	}
}

func TestWhitelistRefusesUnlistedName(t *testing.T) {
	id := signoff.Identity{Whitelist: map[string]bool{"wangwei794": true}}
	if !id.IsHuman("wangwei794") {
		t.Error("a listed person must be able to sign")
	}
	if id.IsHuman("someone-plausible") {
		t.Error("an unlisted name must not sign when a whitelist is in force")
	}
	if id.Warning() != "" {
		t.Errorf("Warning() = %q, want empty when a whitelist is in force", id.Warning())
	}
}

func TestBlacklistBeatsWhitelist(t *testing.T) {
	// Listing an agent must not turn it into a person.
	id := signoff.Identity{
		Whitelist: map[string]bool{"idev-coder": true, "claude": true, "wangwei794": true},
		Agents:    []string{"idev-coder"},
	}
	for _, name := range []string{"idev-coder", "claude"} {
		if id.IsHuman(name) {
			t.Errorf("IsHuman(%q) = true even though it is an agent", name)
		}
	}
	if !id.IsHuman("wangwei794") {
		t.Error("the person in the same list must still sign")
	}
}

func TestBlacklistOnlyReportsItself(t *testing.T) {
	if got := signoff.BlacklistOnly().Warning(); got == "" {
		t.Error("blacklist-only mode must announce itself")
	}
}

// FuzzParseConfirm asserts the one property that matters: a quote is only ever
// an approval if it normalizes to something the grammar fully consumed.
func FuzzParseConfirm(f *testing.F) {
	for _, seed := range []string{
		"确认", "同意吗", "确认不了", "LGTM but wait", "", "确认 origin=code", "驳回",
	} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, quote string) {
		got := signoff.ParseConfirm(quote, "", "")
		if !got.OK {
			return
		}
		norm := signoff.Normalize(quote)
		if norm == "" {
			t.Fatalf("empty quote %q approved", quote)
		}
		for _, mark := range []string{"?", "？", "吗", "么", "嘛", "呢"} {
			if containsRune(norm, mark) {
				t.Fatalf("question %q approved (normalized %q)", quote, norm)
			}
		}
		if got.Reason != signoff.ReasonOK {
			t.Fatalf("OK result carries reason %q", got.Reason)
		}
	})
}

func containsRune(s, sub string) bool {
	return len(sub) > 0 && len(s) >= len(sub) && indexOf(s, sub) >= 0
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
