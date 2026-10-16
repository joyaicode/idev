// Package schemas compiles the embedded JSON Schema contracts and validates
// values against them.
//
// The schemas are the one source for three consumers: MCP tool definitions,
// the HTTP API, and the projections back to the old YAML files. Compiling
// them once at first use means a malformed contract fails loudly rather than
// at the first request that happens to exercise it.
//
// In pkg/ because an auditor verifying an exported run needs to check it
// against the same contracts without running idevd.
package schemas

import (
	"bytes"
	"errors"
	"fmt"
	"io/fs"
	"path"
	"sort"
	"strings"
	"sync"

	"github.com/santhosh-tekuri/jsonschema/v6"

	apischemas "github.com/idev/api/schemas"
)

// Base is the $id prefix the contracts use to reference one another.
const Base = "https://idev.dev/schemas/"

// Contract names, for callers that iterate them.
const (
	Common           = "common.schema.json"
	Kinds            = "kinds.schema.json"
	DelegationPacket = "delegation-packet.schema.json"
	DelegationReturn = "delegation-return.schema.json"
	BaselineManifest = "baseline-manifest.schema.json"
)

// Names lists every embedded contract, sorted.
func Names() ([]string, error) {
	entries, err := fs.Glob(apischemas.Files, "*.json")
	if err != nil {
		return nil, err
	}
	sort.Strings(entries)
	return entries, nil
}

var (
	once     sync.Once
	compiled map[string]*jsonschema.Schema
	loadErr  error
)

func load() {
	compiler := jsonschema.NewCompiler()
	// In Draft 2020-12 `format` is an annotation unless asked otherwise, so
	// without this a "created_at": "last tuesday" would validate. These are
	// wire contracts; a malformed timestamp is a contract violation.
	compiler.AssertFormat()
	compiled = map[string]*jsonschema.Schema{}

	names, err := Names()
	if err != nil {
		loadErr = err
		return
	}
	if len(names) == 0 {
		loadErr = fmt.Errorf("schemas: nothing embedded; the build is wrong, not the input")
		return
	}

	// Register under each contract's own $id. The $refs between them are
	// relative ("common.schema.json#/$defs/digest"), and a relative ref
	// resolves against the referrer's $id — so registering under the bare
	// file name leaves every cross-reference pointing at an unregistered
	// absolute URL, and the compiler tries to fetch it over the network.
	for _, name := range names {
		raw, err := apischemas.Files.ReadFile(name)
		if err != nil {
			loadErr = fmt.Errorf("schemas: read %s: %w", name, err)
			return
		}
		doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
		if err != nil {
			loadErr = fmt.Errorf("schemas: parse %s: %w", name, err)
			return
		}
		if err := compiler.AddResource(Base+name, doc); err != nil {
			loadErr = fmt.Errorf("schemas: add %s: %w", name, err)
			return
		}
	}
	for _, name := range names {
		s, err := compiler.Compile(Base + name)
		if err != nil {
			loadErr = fmt.Errorf("schemas: compile %s: %w", name, err)
			return
		}
		compiled[name] = s
	}
}

// Get returns a compiled contract by file name.
func Get(name string) (*jsonschema.Schema, error) {
	once.Do(load)
	if loadErr != nil {
		return nil, loadErr
	}
	s, ok := compiled[path.Base(name)]
	if !ok {
		return nil, fmt.Errorf("schemas: no such contract %q", name)
	}
	return s, nil
}

// Def compiles one definition out of a contract, e.g.
// Def(Kinds, "/$defs/kind"). Callers that validate a single field — an MCP
// tool taking just a kind, say — need the subschema rather than the whole
// document, which is an object and would reject a bare string.
func Def(name, pointer string) (*jsonschema.Schema, error) {
	once.Do(load)
	if loadErr != nil {
		return nil, loadErr
	}
	c := jsonschema.NewCompiler()
	c.AssertFormat()
	names, err := Names()
	if err != nil {
		return nil, err
	}
	for _, n := range names {
		raw, err := apischemas.Files.ReadFile(n)
		if err != nil {
			return nil, err
		}
		doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
		if err != nil {
			return nil, err
		}
		if err := c.AddResource(Base+n, doc); err != nil {
			return nil, err
		}
	}
	s, err := c.Compile(Base + path.Base(name) + "#" + pointer)
	if err != nil {
		return nil, fmt.Errorf("schemas: %s%s: %w", name, pointer, err)
	}
	return s, nil
}

// Validate checks a decoded JSON value against one contract.
//
// `v` must come from jsonschema.UnmarshalJSON or be built from the same
// primitives (map[string]any, []any, float64, string, bool, nil). A Go
// struct will not validate the way the wire format does, which is the point:
// the contract is about the bytes on the wire.
func Validate(name string, v any) error {
	s, err := Get(name)
	if err != nil {
		return err
	}
	return s.Validate(v)
}

// ValidateBytes decodes raw JSON and validates it.
func ValidateBytes(name string, raw []byte) error {
	v, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
	if err != nil {
		return fmt.Errorf("schemas: %s: malformed JSON: %w", name, err)
	}
	return Validate(name, v)
}

// Pointers lists the instance locations a validation error touched, outermost
// first, as RFC 6901 JSON Pointers. Used to tell a caller which field is
// wrong rather than handing them the whole error tree.
func Pointers(err error) []string {
	var ve *jsonschema.ValidationError
	if !errors.As(err, &ve) {
		return nil
	}
	var out []string
	var walk func(*jsonschema.ValidationError)
	walk = func(e *jsonschema.ValidationError) {
		out = append(out, pointer(e.InstanceLocation))
		for _, c := range e.Causes {
			walk(c)
		}
	}
	walk(ve)
	return out
}

// pointer renders a location as a JSON Pointer. The library hands back the
// path as segments; "" is the document root.
func pointer(segments []string) string {
	if len(segments) == 0 {
		return ""
	}
	var sb bytes.Buffer
	for _, s := range segments {
		sb.WriteByte('/')
		// RFC 6901 escaping.
		s = strings.ReplaceAll(s, "~", "~0")
		s = strings.ReplaceAll(s, "/", "~1")
		sb.WriteString(s)
	}
	return sb.String()
}
