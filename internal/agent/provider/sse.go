package provider

import (
	"bufio"
	"io"
	"strings"
)

// sseReader reads an SSE body line by line, yielding only the payload of
// `data:` lines. SSE framing is trivial but easy to get subtly wrong
// (CRLF, comment lines, multi-line data); this keeps that in one place.
type sseReader struct {
	sc *bufio.Scanner
}

func newSSEReader(r io.Reader) *sseReader {
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 64*1024), 4<<20)
	return &sseReader{sc: sc}
}

// Next returns the next data payload, or io.EOF at the end. Event lines,
// comments, and blank lines are skipped: chat-completions streams carry
// only data payloads that matter.
func (r *sseReader) Next() (string, error) {
	for r.sc.Scan() {
		line := strings.TrimRight(r.sc.Text(), "\r")
		if line == "" || strings.HasPrefix(line, ":") {
			continue
		}
		if after, ok := strings.CutPrefix(line, "data:"); ok {
			return strings.TrimSpace(after), nil
		}
	}
	if err := r.sc.Err(); err != nil {
		return "", err
	}
	return "", io.EOF
}
