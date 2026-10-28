// Package apischemas embeds the JSON Schema contract files.
//
// It exists only because go:embed cannot reach a parent directory: the
// contracts live in api/schemas because that is where a reader looks for an
// API contract, and the embed directive has to sit beside them. The usable
// surface — compiling and validating — is pkg/schemas.
package apischemas

import "embed"

// Files holds every contract, including the generated kinds.schema.json and
// the MCP tool input/output schemas under tools/, so a built binary validates
// against the enum its generator produced and the tool surface agents see.
//
//go:embed *.json tools/*.json
var Files embed.FS
