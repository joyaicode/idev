// Package qodana wraps the official qodana CLI for idevd quality gates (E6.3).
package qodana

import (
	"context"
	"fmt"
)

// Scan refuses until the adapter is wired to an allowlisted qodana binary.
func Scan(ctx context.Context, _ Args) error {
	_ = ctx
	return fmt.Errorf("qodana: not configured (E6.3)")
}

// Args will carry scope/linter once the CLI allowlist lands.
type Args struct {
	Scope  string
	Linter string
}
