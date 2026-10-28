// Package postgres will run the same storetest suite as sqlite (E6.2).
//
// This build only documents the contract and refuses to open unless
// IDEV_POSTGRES_URL is set — so CI stays green without a database.
package postgres

import (
	"context"
	"fmt"
	"os"
)

// Open refuses until a driver is wired. Callers that want the suite skip
// when this returns the ErrNotConfigured sentinel.
func Open(ctx context.Context, url string) error {
	if url == "" {
		url = os.Getenv("IDEV_POSTGRES_URL")
	}
	if url == "" {
		return ErrNotConfigured
	}
	return fmt.Errorf("postgres: driver not wired in this build (url set, E6.2 in progress)")
}

// ErrNotConfigured means the suite should skip.
var ErrNotConfigured = fmt.Errorf("postgres: IDEV_POSTGRES_URL unset")
