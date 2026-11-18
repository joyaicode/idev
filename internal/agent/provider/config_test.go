package provider

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func writeChannel(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "channels.yaml")
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLoadChannelsMissingFileIsNil(t *testing.T) {
	set, err := LoadChannels(filepath.Join(t.TempDir(), "absent.yaml"))
	if err != nil {
		t.Fatalf("missing file must not error: %v", err)
	}
	if set != nil {
		t.Fatalf("missing file must return nil set, got %+v", set)
	}
}

func TestLoadChannelsParsesAndValidates(t *testing.T) {
	path := writeChannel(t, `
default: jcp
default_model: GLM-5.3
providers:
  jcp:
    preset: jcp
    models: [GLM-5.3, DeepSeek-V4.1-Flash]
  work:
    base_url: https://example.internal/v1
    api_key_env: WORK_KEY
    models: [m-a, m-b]
    timeout_s: 30
    extra_headers:
      X-Org: acme
`)
	set, err := LoadChannels(path)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if got := set.DefaultChannel(); got != "jcp" {
		t.Fatalf("default channel = %q, want jcp", got)
	}
	if got := set.Names(); len(got) != 2 || got[0] != "jcp" || got[1] != "work" {
		t.Fatalf("names = %v", got)
	}
}

func TestLoadChannelsDanglingDefaultFails(t *testing.T) {
	path := writeChannel(t, `
default: ghost
providers:
  a:
    base_url: http://localhost:1/v1
`)
	if _, err := LoadChannels(path); err == nil {
		t.Fatal("dangling default must fail at load")
	}
}

func TestLoadChannelsBrokenYAMLFails(t *testing.T) {
	path := writeChannel(t, "providers: [")
	if _, err := LoadChannels(path); err == nil {
		t.Fatal("broken YAML must fail")
	}
}

func TestLoadChannelsEmptyFileBehavesMissing(t *testing.T) {
	set, err := LoadChannels(writeChannel(t, ""))
	if err != nil || set != nil {
		t.Fatalf("empty file: set=%v err=%v", set, err)
	}
}

func TestBuildResolvesPresetAndOverrides(t *testing.T) {
	path := writeChannel(t, `
providers:
  jcp2:
    preset: jcp
    base_url: http://127.0.0.1:9999/v1
    models: [m1]
`)
	set, err := LoadChannels(path)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	cfg, err := set.Build("jcp2", "m1")
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	if cfg.BaseURL != "http://127.0.0.1:9999/v1" {
		t.Fatalf("base_url override lost: %q", cfg.BaseURL)
	}
	if cfg.APIKey != "jcp" {
		t.Fatalf("preset key lost: %q", cfg.APIKey)
	}
	if cfg.Model != "m1" {
		t.Fatalf("model = %q", cfg.Model)
	}
}

func TestBuildModelFromListDefaultAndValidation(t *testing.T) {
	set, err := LoadChannels(writeChannel(t, `
providers:
  a:
    base_url: http://localhost:1/v1
    models: [m-a, m-b]
  b:
    base_url: http://localhost:2/v1
`))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	// No model given: first listed model becomes the default.
	cfg, err := set.Build("a", "")
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	if cfg.Model != "m-a" {
		t.Fatalf("default model = %q, want m-a", cfg.Model)
	}
	// A model not in the list is an error, not a guess.
	if _, err := set.Build("a", "m-zz"); err == nil {
		t.Fatal("unlisted model must fail")
	}
	// A channel without a models list accepts any model.
	cfg, err = set.Build("b", "whatever")
	if err != nil {
		t.Fatalf("build b: %v", err)
	}
	if cfg.Model != "whatever" {
		t.Fatalf("model = %q", cfg.Model)
	}
}

func TestBuildFileDefaultModelBeatsChannelFirst(t *testing.T) {
	set, err := LoadChannels(writeChannel(t, `
default: a
default_model: m-b
providers:
  a:
    base_url: http://localhost:1/v1
    models: [m-a, m-b]
  b:
    base_url: http://localhost:2/v1
    models: [m-a, m-b]
`))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	cfg, err := set.Build("a", "")
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	if cfg.Model != "m-b" {
		t.Fatalf("default_model = %q, want m-b", cfg.Model)
	}
	// default_model scopes to the default channel: b keeps its own first.
	cfg, err = set.Build("b", "")
	if err != nil {
		t.Fatalf("build b: %v", err)
	}
	if cfg.Model != "m-a" {
		t.Fatalf("b default = %q, want m-a", cfg.Model)
	}
}

func TestBuildAPIKeyEnvFallback(t *testing.T) {
	t.Setenv("TEST_WORK_KEY", "sk-from-env")
	set, err := LoadChannels(writeChannel(t, `
providers:
  work:
    base_url: http://localhost:1/v1
    api_key_env: TEST_WORK_KEY
    models: [m]
`))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	cfg, err := set.Build("work", "m")
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	if cfg.APIKey != "sk-from-env" {
		t.Fatalf("api key = %q, want from env", cfg.APIKey)
	}
}

func TestBuildTimeoutAndHeaders(t *testing.T) {
	set, err := LoadChannels(writeChannel(t, `
providers:
  work:
    base_url: http://localhost:1/v1
    models: [m]
    timeout_s: 45
    extra_headers:
      X-Org: acme
`))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	cfg, err := set.Build("work", "m")
	if err != nil {
		t.Fatalf("build: %v", err)
	}
	if cfg.Timeout != 45*time.Second {
		t.Fatalf("timeout = %v", cfg.Timeout)
	}
	if cfg.ExtraHTTPHeaders["X-Org"] != "acme" {
		t.Fatalf("extra headers = %v", cfg.ExtraHTTPHeaders)
	}
}

func TestBuildUnknownChannelAndNoConfig(t *testing.T) {
	set, err := LoadChannels(writeChannel(t, `
providers:
  a:
    base_url: http://localhost:1/v1
`))
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if _, err := set.Build("nope", "m"); err == nil {
		t.Fatal("unknown channel must fail")
	}
	var nilSet *ChannelSet
	if _, err := nilSet.Build("a", "m"); err == nil {
		t.Fatal("nil set must fail build")
	}
}
