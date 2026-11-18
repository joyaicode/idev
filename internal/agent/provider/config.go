// Channel config: the file that names several model accesses so the CLI
// can switch between them mid-session (/use, /model) instead of restarting
// with different flags. The precedence stays what the presets established:
// explicit flags/env win over the file, the file wins over built-in
// presets, and an unknown name is an error — never a guess.

package provider

import (
	"fmt"
	"os"
	"time"

	"go.yaml.in/yaml/v3"
)

// ChannelEntry is one provider block in the config file. Every field is
// optional except enough to actually reach an endpoint: either a preset
// name to inherit from, or a base_url. api_key_env beats nothing — it is
// an alternative to api_key, not an overlay: the file value wins when both
// are set, because the file is the thing the person is looking at.
type ChannelEntry struct {
	// Preset names a built-in preset (ollama / jdcloud / jcp) whose
	// base URL and key this entry inherits before its own fields apply.
	Preset string `yaml:"preset,omitempty"`
	// BaseURL overrides the (possibly inherited) base URL.
	BaseURL string `yaml:"base_url,omitempty"`
	// APIKey is the literal key. Fine for local-proxy placeholder keys;
	// real secrets belong in APIKeyEnv.
	APIKey string `yaml:"api_key,omitempty"`
	// APIKeyEnv names an environment variable holding the key.
	APIKeyEnv string `yaml:"api_key_env,omitempty"`
	// Models lists the model names reachable through this channel. The
	// first is the channel's default model when default_model is absent.
	Models []string `yaml:"models,omitempty"`
	// TimeoutSecs caps one full request (0 = package default 120s).
	TimeoutSecs int `yaml:"timeout_s,omitempty"`
	// ExtraHTTPHeaders ride along verbatim (gateway auth quirks).
	ExtraHeaders map[string]string `yaml:"extra_headers,omitempty"`
}

// channelFile is the on-disk shape of the whole config.
type channelFile struct {
	Default      string                  `yaml:"default,omitempty"`
	DefaultModel string                  `yaml:"default_model,omitempty"`
	Providers    map[string]ChannelEntry `yaml:"providers"`
}

// ChannelSet is the loaded, immutable view of the config file. A nil
// *ChannelSet means "no config file" — the flag/env/preset path stands
// alone exactly as before this file existed.
type ChannelSet struct {
	defaultChannel string
	defaultModel   string
	entries        map[string]ChannelEntry
}

// LoadChannels reads path. A missing file is not an error: it returns
// (nil, nil) so the caller falls back to flags without special-casing.
// A present-but-broken file IS an error — a half-parsed channel list is
// how a /use lands on the wrong endpoint.
func LoadChannels(path string) (*ChannelSet, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("provider: read %s: %w", path, err)
	}
	var cf channelFile
	if err := yaml.Unmarshal(raw, &cf); err != nil {
		return nil, fmt.Errorf("provider: parse %s: %w", path, err)
	}
	if len(cf.Providers) == 0 {
		// An empty file behaves like a missing one; anything else
		// (default pointing nowhere) is caught by Validate.
		return nil, nil
	}
	set := &ChannelSet{
		defaultChannel: cf.Default,
		defaultModel:   cf.DefaultModel,
		entries:        cf.Providers,
	}
	if err := set.Validate(); err != nil {
		return nil, fmt.Errorf("provider: %s: %w", path, err)
	}
	return set, nil
}

// Validate checks the cross-references: the default channel must exist.
// A dangling default fails at load, not at first /use — same
// unknown-name-is-an-error rule as Preset.
func (s *ChannelSet) Validate() error {
	if s == nil {
		return nil
	}
	if s.defaultChannel != "" {
		if _, ok := s.entries[s.defaultChannel]; !ok {
			return fmt.Errorf("default channel %q is not in providers", s.defaultChannel)
		}
	}
	return nil
}

// Names returns the channel names in stable (sorted) order.
func (s *ChannelSet) Names() []string {
	if s == nil {
		return nil
	}
	names := make([]string, 0, len(s.entries))
	for n := range s.entries {
		names = append(names, n)
	}
	sortStrings(names)
	return names
}

// Entry returns the channel entry and whether it exists.
func (s *ChannelSet) Entry(name string) (ChannelEntry, bool) {
	if s == nil {
		return ChannelEntry{}, false
	}
	e, ok := s.entries[name]
	return e, ok
}

// DefaultChannel is the file's default channel name, possibly "".
func (s *ChannelSet) DefaultChannel() string {
	if s == nil {
		return ""
	}
	return s.defaultChannel
}

// DefaultModelFor returns the model a channel should start with: the
// file's default_model when this channel is the file's default channel,
// else the channel's first listed model. Empty when neither exists —
// the caller then requires an explicit model.
func (s *ChannelSet) DefaultModelFor(name string) string {
	if s == nil {
		return ""
	}
	if s.defaultModel != "" && name == s.defaultChannel {
		return s.defaultModel
	}
	if e, ok := s.entries[name]; ok && len(e.Models) > 0 {
		return e.Models[0]
	}
	return ""
}

// Build resolves a channel and model into a provider Config. The entry's
// preset (if any) fills the base, the entry's own fields override it, and
// the model is checked against the entry's list when the entry has one —
// listing models in the file is exactly how a typo gets caught at /use
// time instead of as a confusing 404 from the gateway three turns later.
// An entry without a models list accepts any model name (the channel is
// a passthrough; the person curates names elsewhere).
func (s *ChannelSet) Build(name, model string) (Config, error) {
	if s == nil {
		return Config{}, fmt.Errorf("provider: no channel config loaded")
	}
	e, ok := s.entries[name]
	if !ok {
		return Config{}, fmt.Errorf("provider: unknown channel %q (configured: %v)", name, s.Names())
	}
	if model == "" {
		model = s.DefaultModelFor(name)
		if model == "" {
			return Config{}, fmt.Errorf("provider: channel %q has no model (no default_model, empty models list)", name)
		}
	}
	if len(e.Models) > 0 && !containsString(e.Models, model) {
		return Config{}, fmt.Errorf("provider: model %q is not in channel %q's models list %v", model, name, e.Models)
	}
	var cfg Config
	if e.Preset != "" {
		pre, err := Preset(e.Preset)
		if err != nil {
			return Config{}, err
		}
		cfg.BaseURL = pre.BaseURL
		cfg.APIKey = pre.APIKey
	}
	if e.BaseURL != "" {
		cfg.BaseURL = e.BaseURL
	}
	if e.APIKey != "" {
		cfg.APIKey = e.APIKey
	} else if e.APIKeyEnv != "" {
		cfg.APIKey = os.Getenv(e.APIKeyEnv)
	}
	cfg.Model = model
	if e.TimeoutSecs > 0 {
		cfg.Timeout = time.Duration(e.TimeoutSecs) * time.Second
	}
	cfg.ExtraHTTPHeaders = e.ExtraHeaders
	return cfg, nil
}

func sortStrings(ss []string) {
	for i := 1; i < len(ss); i++ {
		for j := i; j > 0 && ss[j] < ss[j-1]; j-- {
			ss[j], ss[j-1] = ss[j-1], ss[j]
		}
	}
}

func containsString(ss []string, s string) bool {
	for _, v := range ss {
		if v == s {
			return true
		}
	}
	return false
}
