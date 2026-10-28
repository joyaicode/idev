package postgres_test

import (
	"context"
	"errors"
	"testing"

	"github.com/idev/internal/adapters/store/postgres"
)

func TestOpenSkipsWithoutURL(t *testing.T) {
	t.Setenv("IDEV_POSTGRES_URL", "")
	err := postgres.Open(context.Background(), "")
	if !errors.Is(err, postgres.ErrNotConfigured) {
		t.Fatalf("got %v, want ErrNotConfigured", err)
	}
}
