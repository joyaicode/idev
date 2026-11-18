// Package tools hosts ideva's built-in tool implementations. The registry
// itself is loop.Tool; each file here is one concrete tool with the same
// shape the subagent definitions already describe (agents/*.md frontmatter
// `tools:` names map onto these).
//
// What every tool here observes, inherited from the kernel's rules:
// no signoff fields may be written anywhere (that is the conductor's and a
// person's job), and shell output goes to disk with a path in the result —
// a subagent returning a log path, not a log, is already the kernel's
// evidence convention (agents/idev-coder.md「命令输出落盘再给路径」).
package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// Bash runs one shell command under a timeout. This is the delegation
// layer's workhorse — and the one tool whose boundaries the kernel never
// trusted to a prompt, which is why the deny list here is code, not text.
type Bash struct {
	// WorkDir is where commands run; zero means the process cwd.
	WorkDir string
	// Timeout bounds one command. Zero means 120s.
	Timeout time.Duration
	// LogDir is where full output goes; the result carries the path.
	LogDir string
	// Deny is compiled once at startup: the same oversteps the Python
	// pre_tool hook refuses — signoff-field writes in ticket/run YAML,
	// and engine fallbacks that would skip the store checks. Code-level,
	// because "a prompt the model can ignore" is what the review replaced
	// everywhere else.
	Deny []DenyRule
}

// DenyRule refuses commands matching Pattern for the stated Reason.
type DenyRule struct {
	Pattern string
	Reason  string
}

// DefaultDenyRules are the oversteps hooks/pre_tool.py has been
// refusing all along, restated as host-level code. When ideva is the
// host, the model cannot talk its way past these.
func DefaultDenyRules() []DenyRule {
	return []DenyRule{
		// The engine fallbacks would skip the store checks entirely.
		{Pattern: `(^|[\s;|&])IDEV_ENGINE\s*=\s*python`, Reason: "the Go engine is required; the python fallback skips store checks"},
		{Pattern: `(^|[\s;|&])IDEV_BIN\s*=\s*(off|none|0)`, Reason: "IDEV_BIN=off skips the store checks"},
		// Signoff fields are the person's and the conductor's; sed-ing
		// them into ticket YAML is the classic overstep.
		{Pattern: `(sealed|accepted|aligned|resolved)\s*:`, Reason: "signoff fields are written by the conductor after checks pass, never from a shell"},
	}
}

// Name implements loop.Tool.
func (t *Bash) Name() string { return "bash" }

// Description implements loop.Tool.
func (t *Bash) Description() string {
	return "在仓库里跑一条 shell 命令并返回输出。命令输出超长时落盘并返回日志路径。禁止改签字字段。"
}

// ParametersJSON implements loop.Tool.
func (t *Bash) ParametersJSON() json.RawMessage {
	return json.RawMessage(`{
		"type": "object",
		"properties": {
			"command": {"type": "string", "description": "要跑的命令，单条"},
			"timeout_s": {"type": "integer", "minimum": 1, "maximum": 600, "description": "可选超时秒数，缺省 120"}
		},
		"required": ["command"]
	}`)
}

// ReadOnly implements loop.Tool: bash can write, so no.
func (t *Bash) ReadOnly() bool { return false }

// Execute implements loop.Tool.
func (t *Bash) Execute(ctx context.Context, args json.RawMessage) (string, error) {
	var in struct {
		Command  string `json:"command"`
		TimeoutS int    `json:"timeout_s"`
	}
	if err := json.Unmarshal(args, &in); err != nil {
		return "", fmt.Errorf("bash: args: %w", err)
	}
	if strings.TrimSpace(in.Command) == "" {
		return "", fmt.Errorf("bash: empty command")
	}
	for _, rule := range t.Deny {
		if rule.Pattern == "" {
			continue
		}
		if matches(in.Command, rule.Pattern) {
			return "", fmt.Errorf("bash: refused: %s", rule.Reason)
		}
	}
	timeout := t.Timeout
	if in.TimeoutS > 0 {
		timeout = time.Duration(in.TimeoutS) * time.Second
	}
	if timeout <= 0 {
		timeout = 120 * time.Second
	}
	runCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	cmd := exec.CommandContext(runCtx, "bash", "-c", in.Command)
	if t.WorkDir != "" {
		cmd.Dir = t.WorkDir
	}
	out, err := cmd.CombinedOutput()
	summary := string(out)
	// Long output goes to disk and the model gets the head plus the path —
	// the evidence convention (a path in the report) inverted into the
	// tool itself.
	const head = 2000
	if len(out) > head {
		summary = string(out[:head]) + "\n… (truncated)"
		if t.LogDir != "" {
			if err := os.MkdirAll(t.LogDir, 0o755); err == nil {
				path := filepath.Join(t.LogDir, fmt.Sprintf("bash-%d.log", time.Now().UnixMilli()))
				if os.WriteFile(path, out, 0o644) == nil {
					summary += fmt.Sprintf("\nfull log: %s", path)
				}
			}
		}
	}
	if err != nil {
		// A failed command is a result the model must see, not a tool
		// error: the exit code and output ARE the answer.
		return fmt.Sprintf("exit=%v\n%s", exitCode(err), summary), nil
	}
	return fmt.Sprintf("exit=0\n%s", summary), nil
}

func exitCode(err error) string {
	var ee *exec.ExitError
	if errorsAs(err, &ee) {
		return fmt.Sprintf("%d", ee.ExitCode())
	}
	return fmt.Sprintf("%v", err)
}

// matches is a tiny regex wrapper so the deny rules stay declarative.
func matches(command, pattern string) bool {
	return reMatch(pattern, command)
}

// Read returns a file's content, line-numbered, capped like the kernel's
// two-stage reads (context-stage.py loads at most 80 lines): a tool result
// is context, and unbounded file reads are how loops die.
type Read struct{}

// Name implements loop.Tool.
func (t *Read) Name() string { return "read" }

// Description implements loop.Tool.
func (t *Read) Description() string {
	return "读一个文件的内容，带行号。默认读前 2000 行；带 offset/limit 读区间。"
}

// ParametersJSON implements loop.Tool.
func (t *Read) ParametersJSON() json.RawMessage {
	return json.RawMessage(`{
		"type": "object",
		"properties": {
			"path": {"type": "string", "description": "文件路径"},
			"offset": {"type": "integer", "minimum": 1, "description": "起始行，1 起"},
			"limit": {"type": "integer", "minimum": 1, "maximum": 2000, "description": "最多读多少行"}
		},
		"required": ["path"]
	}`)
}

// ReadOnly implements loop.Tool.
func (t *Read) ReadOnly() bool { return true }

// Execute implements loop.Tool.
func (t *Read) Execute(ctx context.Context, args json.RawMessage) (string, error) {
	var in struct {
		Path   string `json:"path"`
		Offset int    `json:"offset"`
		Limit  int    `json:"limit"`
	}
	if err := json.Unmarshal(args, &in); err != nil {
		return "", fmt.Errorf("read: args: %w", err)
	}
	body, err := os.ReadFile(in.Path)
	if err != nil {
		return "", fmt.Errorf("read: %w", err)
	}
	lines := strings.Split(string(body), "\n")
	start := in.Offset
	if start < 1 {
		start = 1
	}
	limit := in.Limit
	if limit < 1 || limit > 2000 {
		limit = 2000
	}
	end := start + limit - 1
	if end > len(lines) {
		end = len(lines)
	}
	var b strings.Builder
	for i := start; i <= end; i++ {
		fmt.Fprintf(&b, "%d|%s\n", i, lines[i-1])
	}
	if end < len(lines) {
		fmt.Fprintf(&b, "TRUNCATED next=%s:%d:%d\n", in.Path, end+1, len(lines))
	}
	return b.String(), nil
}

// Write creates or replaces one file. Full stop is deliberate: append and
// partial-edit semantics are how a model quietly rewrites history; a
// whole-file write is the operation that matches what the diff review
// can actually check.
type Write struct{}

// Name implements loop.Tool.
func (t *Write) Name() string { return "write" }

// Description implements loop.Tool.
func (t *Write) Description() string {
	return "把整段内容写入一个文件（创建或整文件替换）。禁止写签字字段值。"
}

// ParametersJSON implements loop.Tool.
func (t *Write) ParametersJSON() json.RawMessage {
	return json.RawMessage(`{
		"type": "object",
		"properties": {
			"path": {"type": "string"},
			"content": {"type": "string"}
		},
		"required": ["path", "content"]
	}`)
}

// ReadOnly implements loop.Tool.
func (t *Write) ReadOnly() bool { return false }

// Execute implements loop.Tool.
func (t *Write) Execute(ctx context.Context, args json.RawMessage) (string, error) {
	var in struct {
		Path    string `json:"path"`
		Content string `json:"content"`
	}
	if err := json.Unmarshal(args, &in); err != nil {
		return "", fmt.Errorf("write: args: %w", err)
	}
	if in.Path == "" {
		return "", fmt.Errorf("write: empty path")
	}
	// Signoff fields stay out of what this tool will write: the regex is
	// the same one the pre_tool hook applies to ticket YAML edits, kept
	// here as a second layer for the files the hook naming can't reach.
	if reMatch(`(?m)^\s*(sealed|accepted|aligned|resolved|reopen_baseline)\s*:\s*(true|yes)`, in.Content) {
		return "", fmt.Errorf("write: refused: signoff fields are written by the conductor after checks pass")
	}
	if err := os.MkdirAll(filepath.Dir(in.Path), 0o755); err != nil {
		return "", fmt.Errorf("write: dir: %w", err)
	}
	if err := os.WriteFile(in.Path, []byte(in.Content), 0o644); err != nil {
		return "", fmt.Errorf("write: %w", err)
	}
	return fmt.Sprintf("wrote %d bytes to %s", len(in.Content), in.Path), nil
}

// Grep is a bounded pattern search: the model's eyes, not its firehose.
type Grep struct{}

// Name implements loop.Tool.
func (t *Grep) Name() string { return "grep" }

// Description implements loop.Tool.
func (t *Grep) Description() string {
	return "在目录里按正则搜索文件内容，返回匹配行（路径:行号:内容），上限 200 行。"
}

// ParametersJSON implements loop.Tool.
func (t *Grep) ParametersJSON() json.RawMessage {
	return json.RawMessage(`{
		"type": "object",
		"properties": {
			"pattern": {"type": "string", "description": "正则表达式"},
			"path": {"type": "string", "description": "搜索根目录或单文件"}
		},
		"required": ["pattern"]
	}`)
}

// ReadOnly implements loop.Tool.
func (t *Grep) ReadOnly() bool { return true }

// Execute implements loop.Tool.
func (t *Grep) Execute(ctx context.Context, args json.RawMessage) (string, error) {
	var in struct {
		Pattern string `json:"pattern"`
		Path    string `json:"path"`
	}
	if err := json.Unmarshal(args, &in); err != nil {
		return "", fmt.Errorf("grep: args: %w", err)
	}
	if in.Pattern == "" {
		return "", fmt.Errorf("grep: empty pattern")
	}
	if _, err := compileRegex(in.Pattern); err != nil {
		return "", fmt.Errorf("grep: pattern: %w", err)
	}
	root := in.Path
	if root == "" {
		root = "."
	}
	re := compileRegexMust(in.Pattern)
	var b strings.Builder
	count := 0
	err := filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil // unreadable subtree: skip, the search goes on
		}
		if d.IsDir() {
			name := d.Name()
			if name == ".git" || name == "node_modules" || name == "target" || name == "dist" {
				return filepath.SkipDir
			}
			return nil
		}
		if count >= 200 {
			return filepath.SkipAll
		}
		body, err := os.ReadFile(path)
		if err != nil {
			return nil
		}
		for i, line := range strings.Split(string(body), "\n") {
			if re.MatchString(line) {
				fmt.Fprintf(&b, "%s:%d:%s\n", path, i+1, clip(line, 300))
				count++
				if count >= 200 {
					fmt.Fprintf(&b, "… (limit 200 reached)\n")
					return filepath.SkipAll
				}
			}
		}
		return nil
	})
	if err != nil && err != filepath.SkipAll {
		return "", fmt.Errorf("grep: %w", err)
	}
	if count == 0 {
		return "no matches", nil
	}
	return b.String(), nil
}

func clip(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
