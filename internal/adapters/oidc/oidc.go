// Package oidc maps remote principals onto the local Authorizer (E6.4).
package oidc

import (
	"fmt"

	"github.com/idev/internal/ports"
)

// Resolve turns an OIDC subject into a local principal. Not configured yet.
func Resolve(_ string) (ports.Principal, error) {
	return ports.Principal{}, fmt.Errorf("oidc: not configured (E6.4)")
}
