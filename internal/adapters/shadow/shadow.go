// Package shadow compares Go and Python run projections read-only (E6.5).
package shadow

import "fmt"

// Diff reports mismatches between two status projections without writing.
func Diff(_, _ map[string]any) ([]string, error) {
	return nil, fmt.Errorf("shadow: not configured (E6.5)")
}
