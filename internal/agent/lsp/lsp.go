// Package lsp is a Language Server Protocol client skeleton: initialize
// over stdio, then diagnostics. The grilling put LSP on the list as a
// protocol surface — the useful slice for an agent is "what does the
// language server think is wrong with this file", which is exactly what
// a coding executor would ask before claiming a fix.
//
// Scope honesty: initialize + textDocument/didOpen + publishDiagnostics
// notification handling. Completion/hover/rename stay unimplemented —
// an agent host adds them when an executor needs them, not before.
package lsp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"sync"
)

// Client speaks LSP over stdio to one language server process.
type Client struct {
	cmd    *exec.Cmd
	stdin  chan jsonRPC
	mu     sync.Mutex
	nextID int
	// Diagnostics carries the last publishDiagnostics payload per file.
	Diagnostics map[string][]Diagnostic

	// onServerMessage is the raw notification pump, wired in tests.
	responses map[int]chan json.RawMessage
	events    chan notification
}

// jsonRPC is the wire frame; Content-Length headers are the transport's,
// the JSON body is ours.
type jsonRPC struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      *int            `json:"id,omitempty"`
	Method  string          `json:"method,omitempty"`
	Params  json.RawMessage `json:"params,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
}

type notification struct {
	Method string
	Params json.RawMessage
}

// Diagnostic is the subset of LSP's Diagnostic an agent reads.
type Diagnostic struct {
	Range struct {
		Start struct {
			Line      int `json:"line"`
			Character int `json:"character"`
		} `json:"start"`
	} `json:"range"`
	Severity int    `json:"severity"`
	Source   string `json:"source"`
	Message  string `json:"message"`
}

// Start launches the server and performs the LSP initialize handshake.
func Start(ctx context.Context, command string) (*Client, error) {
	fields := strings.Fields(command)
	cmd := exec.CommandContext(ctx, fields[0], fields[1:]...)
	stdinPipe, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdoutPipe, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("lsp: start %s: %w", fields[0], err)
	}
	c := &Client{
		cmd:         cmd,
		Diagnostics: map[string][]Diagnostic{},
		responses:   map[int]chan json.RawMessage{},
		events:      make(chan notification, 64),
		nextID:      1,
	}
	// The write side: one writer goroutine so request ordering is
	// program-order, which LSP servers expect for initialize.
	c.stdin = make(chan jsonRPC)
	go func() {
		enc := json.NewEncoder(stdinPipe)
		for frame := range c.stdin {
			_ = enc.Encode(frame)
		}
	}()
	// The read side: Content-Length framing, responses matched by id,
	// notifications into the events channel.
	go func() {
		sc := bufio.NewReader(stdoutPipe)
		for {
			header, err := readHeader(sc)
			if err != nil {
				return
			}
			body := make([]byte, header.length)
			if _, err := ioReadFull(sc, body); err != nil {
				return
			}
			var frame jsonRPC
			if err := json.Unmarshal(body, &frame); err != nil {
				continue
			}
			if frame.ID != nil && frame.Method == "" {
				c.mu.Lock()
				ch, ok := c.responses[*frame.ID]
				c.mu.Unlock()
				if ok {
					ch <- frame.Result
				}
				continue
			}
			if frame.Method != "" {
				select {
				case c.events <- notification{Method: frame.Method, Params: frame.Params}:
				default: // a slow consumer drops notifications; diagnostics refire
				}
			}
		}
	}()
	if err := c.initialize(ctx); err != nil {
		_ = cmd.Process.Kill()
		return nil, err
	}
	go c.pump()
	return c, nil
}

func (c *Client) initialize(ctx context.Context) error {
	params := map[string]any{
		"processId": nil,
		"rootUri":   nil,
		"capabilities": map[string]any{
			"textDocument": map[string]any{
				"publishDiagnostics": map[string]any{"relatedInformation": false},
			},
		},
	}
	_, err := c.request(ctx, "initialize", params)
	return err
}

func (c *Client) request(ctx context.Context, method string, params any) (json.RawMessage, error) {
	c.mu.Lock()
	id := c.nextID
	c.nextID++
	ch := make(chan json.RawMessage, 1)
	c.responses[id] = ch
	c.mu.Unlock()
	defer func() {
		c.mu.Lock()
		delete(c.responses, id)
		c.mu.Unlock()
	}()
	select {
	case c.stdin <- jsonRPC{JSONRPC: "2.0", ID: &id, Method: method, Params: mustMarshal(params)}:
	case <-ctx.Done():
		return nil, ctx.Err()
	}
	select {
	case result := <-ch:
		return result, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

func (c *Client) notify(method string, params any) {
	c.stdin <- jsonRPC{JSONRPC: "2.0", Method: method, Params: mustMarshal(params)}
}

// DidOpen opens a file, which triggers a publishDiagnostics for it.
func (c *Client) DidOpen(uri, languageID, text string) {
	c.notify("textDocument/didOpen", map[string]any{
		"textDocument": map[string]any{"uri": uri, "languageId": languageID, "text": text, "version": 1},
	})
}

// pump folds publishDiagnostics notifications into the Diagnostics map.
func (c *Client) pump() {
	for ev := range c.events {
		if ev.Method != "textDocument/publishDiagnostics" {
			continue
		}
		var params struct {
			URI         string      `json:"uri"`
			Diagnostics []Diagnostic `json:"diagnostics"`
		}
		if err := json.Unmarshal(ev.Params, &params); err != nil {
			continue
		}
		c.mu.Lock()
		c.Diagnostics[params.URI] = params.Diagnostics
		c.mu.Unlock()
	}
}

// Close ends the session (the context's cancel handles the process).
func (c *Client) Close() {
	close(c.stdin)
	_ = c.cmd.Wait()
}

func mustMarshal(v any) json.RawMessage {
	blob, err := json.Marshal(v)
	if err != nil {
		return json.RawMessage("{}")
	}
	return blob
}

func ioReadFull(sc *bufio.Reader, buf []byte) (int, error) {
	n := 0
	for n < len(buf) {
		m, err := sc.Read(buf[n:])
		n += m
		if err != nil {
			return n, err
		}
	}
	return n, nil
}

func readHeader(sc *bufio.Reader) (struct{ length int }, error) {
	var out struct{ length int }
	for {
		line, err := sc.ReadString('\n')
		if err != nil {
			return out, err
		}
		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			return out, nil
		}
		if after, ok := strings.CutPrefix(line, "Content-Length:"); ok {
			fmt.Sscanf(strings.TrimSpace(after), "%d", &out.length)
		}
	}
}
