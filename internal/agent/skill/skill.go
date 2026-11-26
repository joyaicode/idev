// Package skill mounts the kernel's prompt assets into an ideva system
// prompt. The kernel already defines what a host loads and when — SKILL.md
// is the entry, agent-brief.md is the cold start, references/ pages are
// lazy — and the delegation packet's `步进:`/`请求头:` lines are the
// working precedent for excerpting and freezing. This package is the
// first-party host's implementation of that contract.
//
// The assembler never invents text: it concatenates kernel pages in the
// order the kernel itself prescribes, records what it froze (the sha256
// request-header precedent), and stops there.
package skill

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// ColdStart is the assembly of a conductor system prompt.
type ColdStart struct {
	// SystemPrompt is what goes in as the system message.
	SystemPrompt string
	// Pages lists each kernel page folded in, with its sha256 — the
	// `请求头` precedent: a frozen record of what this prompt was built
	// from, so a later comparison can say "the definition changed".
	Pages []Page
}

// Page is one folded kernel page.
type Page struct {
	Path   string
	SHA256 string
	Lines  int
}

// frontmatterRE finds the YAML block at the top of a skill page. Only the
// delimiters matter here: the fields inside are the host's to render or
// ignore, and ideva ignores them (the description is for host skill
// listings; ideva loads by name).
var frontmatterRE = regexp.MustCompile(`(?s)\A---\n(.*?)\n---\n`)

// FrontmatterBody strips the frontmatter block and returns it plus the
// body. A page without frontmatter returns ("", whole page) — the kernel
// convention is that skills carry it, but a missing block is not an
// error, just a page that starts at line one.
func FrontmatterBody(page string) (string, string) {
	m := frontmatterRE.FindStringSubmatch(page)
	if m == nil {
		return "", page
	}
	return m[1], page[len(m[0]):]
}

// Excerpt takes the first lines of a page the way the delegation packet's
// `步进:` does (step_packet.py: 80 lines / 4000 chars) — a preview the
// model can decide to follow up on, not the whole page in context.
const (
	ExcerptLines = 80
	ExcerptChars = 4000
)

// AssembleConductor builds the ideva conductor's system prompt from the
// kernel checkout: SKILL.md (the entry and the only routing authority)
// plus agent-brief.md (the declared cold-start companion). Both pages
// stay whole — they are the resident context, sized and budgeted by the
// kernel's own cold-start tooling (cold-start-size.py guards 24000 chars
// and these two pages are what it counts).
//
// repoRoot is the kernel checkout; missing pages are an error, not a
// degraded prompt: a conductor that silently lost its routing page is a
// conductor routing by vibes.
func AssembleConductor(repoRoot string) (ColdStart, error) {
	var cs ColdStart
	paths := []string{"SKILL.md", filepath.Join("references", "agent-brief.md")}
	var b strings.Builder
	for i, rel := range paths {
		body, err := readPage(repoRoot, rel)
		if err != nil {
			return cs, err
		}
		_, content := FrontmatterBody(body)
		if i > 0 {
			b.WriteString("\n\n---\n\n")
		}
		b.WriteString(content)
		digest := sha256.Sum256([]byte(body))
		cs.Pages = append(cs.Pages, Page{
			Path:   rel,
			SHA256: hex.EncodeToString(digest[:]),
			Lines:  len(strings.Split(strings.TrimRight(content, "\n"), "\n")),
		})
	}
	cs.SystemPrompt = b.String()
	return cs, nil
}

// AssembleExecutor builds a subagent system prompt from its definition
// file: frontmatter out, body in, tools narrowed by the host (the
// frontmatter `tools:` line is a declaration everywhere and an enforced
// whitelist here — the one thing a first-party host can do that a
// third-party one cannot).
func AssembleExecutor(repoRoot, agentName string) (ColdStart, string, []string, error) {
	var cs ColdStart
	rel := filepath.Join("agents", agentName+".md")
	body, err := readPage(repoRoot, rel)
	if err != nil {
		return cs, "", nil, err
	}
	front, content := FrontmatterBody(body)
	tools := parseToolsLine(front)
	cs.SystemPrompt = content
	digest := sha256.Sum256([]byte(body))
	cs.Pages = append(cs.Pages, Page{
		Path:   rel,
		SHA256: hex.EncodeToString(digest[:]),
		Lines:  len(strings.Split(strings.TrimRight(content, "\n"), "\n")),
	})
	return cs, front, tools, nil
}

var toolsLineRE = regexp.MustCompile(`(?m)^tools:\s*(.*)$`)

// parseToolsLine reads the comma-separated tool names from frontmatter.
// An empty `tools:` line means no narrowing — the kernel's own agents all
// declare lists, but an undeclared one is not an error in the file format;
// the host treats it as full access and that fact is visible here.
// Names are lowercased: the definition files declare them capitalized
// ("Read, Grep, Glob, Bash, Write" — the Claude Code spelling) while the
// host's tool registry keys are lowercase, and this line is the only
// bridge between the two spellings.
func parseToolsLine(frontmatter string) []string {
	m := toolsLineRE.FindStringSubmatch(frontmatter)
	if m == nil {
		return nil
	}
	parts := strings.Split(m[1], ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if t := strings.ToLower(strings.TrimSpace(p)); t != "" {
			out = append(out, t)
		}
	}
	return out
}

func readPage(repoRoot, rel string) (string, error) {
	path := filepath.Join(repoRoot, filepath.FromSlash(rel))
	body, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("skill: read %s: %w", rel, err)
	}
	return string(body), nil
}
