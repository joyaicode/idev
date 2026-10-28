// Package e2e wraps the TesterArmy e2e CLI for idevd quality gates (E6.3).
package e2e

import (
	"context"
	"fmt"
)

// Run refuses until the adapter is wired to an allowlisted e2e binary.
func Run(ctx context.Context, _ Args) error {
	_ = ctx
	return fmt.Errorf("e2e: not configured (E6.3)")
}

// Args will carry profile/selection once the CLI allowlist lands.
type Args struct {
	Profile string
}
