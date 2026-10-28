package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"strings"
	"time"

	"github.com/idev/internal/adapters/workspace"
)

func (a app) workspaceLocate(args []string) error {
	fs := flag.NewFlagSet("workspace locate", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	repo := fs.String("repo", ".", "repository root")
	feature := fs.String("feature", "", "feature id")
	key := fs.String("key", "task", "layout|task|deliver|plan|prd|spec|test-case|patrol")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	path, err := workspace.Local{}.LocateTicket(context.Background(), *repo, *feature, *key)
	if err != nil {
		return err
	}
	fmt.Fprintln(a.stdout, path)
	return nil
}

func (a app) workspaceManifest(args []string) error {
	fs := flag.NewFlagSet("workspace manifest", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	repo := fs.String("repo", ".", "repository root")
	feature := fs.String("feature", "", "feature id")
	ticket := fs.String("ticket", "", "ticket directory (skips locate when set)")
	revision := fs.Int("revision", 0, "override revision (0 = from baseline.yaml)")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	at := time.Now().UTC()
	if strings.TrimSpace(*ticket) != "" {
		if *feature == "" {
			return usageError{"workspace manifest --ticket needs --feature"}
		}
		man, err := workspace.FromTicket(*feature, *ticket, *repo, *revision, at)
		if err != nil {
			return err
		}
		return json.NewEncoder(a.stdout).Encode(man)
	}
	if *feature == "" {
		return usageError{"workspace manifest needs --feature (or --ticket)"}
	}
	man, err := workspace.Local{}.Manifest(context.Background(), *repo, *feature, *revision)
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(man)
}

func (a app) workspaceDiff(args []string) error {
	fs := flag.NewFlagSet("workspace diff", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	repo := fs.String("repo", ".", "repository root")
	base := fs.String("base-ref", "", "git ref to diff against")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	if *base == "" {
		return usageError{"workspace diff needs --base-ref"}
	}
	changed, err := workspace.Local{}.ChangedSince(context.Background(), *repo, *base)
	if err != nil {
		return err
	}
	head, dirty, err := workspace.Local{}.Head(context.Background(), *repo)
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{
		"changed_files": changed,
		"dirty":         dirty,
		"head":          head,
	})
}

func (a app) workspaceHead(args []string) error {
	fs := flag.NewFlagSet("workspace head", flag.ContinueOnError)
	fs.SetOutput(a.stderr)
	repo := fs.String("repo", ".", "repository root")
	if err := fs.Parse(args); err != nil {
		return usageError{err.Error()}
	}
	head, dirty, err := workspace.Local{}.Head(context.Background(), *repo)
	if err != nil {
		return err
	}
	return json.NewEncoder(a.stdout).Encode(map[string]any{"head": head, "dirty": dirty})
}
