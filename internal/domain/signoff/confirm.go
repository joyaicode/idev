// Package signoff decides whether a recorded approval was really given by a
// person, and whether what they wrote was really a confirmation.
//
// This is the Go half of a pair. scripts/lib/workflow_spec.py is the other,
// and both are driven by test/signoff/cases.yaml so they cannot disagree
// while both exist (design §20.2). When the Python side retires, this
// becomes the only implementation and the cases file stays.
//
// The rule being enforced is small and the stakes are not: the previous
// implementation tested whether a quote *started with* a confirming word, so
// "确认不了" (I can't confirm), "同意吗" (do you agree?) and "LGTM but wait"
// were all recorded as approvals. A prefix cannot distinguish a sentence
// from its first two characters, so the whole sentence is parsed and
// anything left over is a refusal.
package signoff

import (
	"regexp"
	"strings"

	"golang.org/x/text/unicode/norm"
)

// Reason says why a quote was not a confirmation. Callers show it to the
// person: "needs confirm words" sends them to retype the same sentence.
type Reason string

// The reasons a quote can fail. Every one of them was a silent `true` under
// the old prefix matcher.
const (
	ReasonOK              Reason = "ok"
	ReasonNoVerb          Reason = "no-verb"
	ReasonQuestion        Reason = "question"
	ReasonNegation        Reason = "negation"
	ReasonHesitation      Reason = "hesitation"
	ReasonUnparsedTail    Reason = "unparsed-tail"
	ReasonKeywordMismatch Reason = "keyword-mismatch"
)

// GateType names the gates that demand a keyword in the quote.
type GateType string

// The two destructive gates. Both roll back work that was already signed
// off, so neither is allowed to pass on a bare 确认.
const (
	GateDefectOrigin   GateType = "defect_origin"
	GateReopenBaseline GateType = "reopen_baseline"
)

var (
	confirmVerbs = []string{"确认", "全签", "同意", "lgtm"}
	rejectVerbs  = []string{"驳回"}

	// After NFKC the full-width separators fold onto ASCII, so this list is
	// shorter than it looks.
	seps = []string{" ", "，", ",", "：", ":"}

	// The only qualifiers a confirmation may carry. Anything else means the
	// person wrote prose, and prose is not a signoff.
	tokens = []string{
		"origin=req", "origin=arch", "origin=code",
		"解除密封", "reopen", "sealed", "accepted", "aligned", "resolved",
		"plan", "方案", "拆解", "基线", "提测",
	}

	questionMarks = []string{"?", "？", "吗", "么", "嘛", "呢", "是否", "能否", "可否", "要不要"}
	negationCJK   = []string{"不", "没", "别", "未", "否", "勿"}
	hesitation    = []string{"先", "等", "再说", "待定", "也许", "可能", "吧"}

	negationASCII = regexp.MustCompile(`\b(?:not|no|don't|wait|but|hold|later)\b`)

	trailing = "。.!~ "
	spaces   = regexp.MustCompile(`\s+`)
)

// Result is the verdict on one quote.
type Result struct {
	OK     bool
	Reason Reason
	Tokens []string
}

// Normalize folds a quote to the form the grammar is written against: NFKC,
// trimmed, lowercased, trailing punctuation dropped, whitespace collapsed.
func Normalize(quote string) string {
	s := norm.NFKC.String(quote)
	s = strings.ToLower(strings.TrimSpace(s))
	s = spaces.ReplaceAllString(s, " ")
	return strings.TrimRight(s, trailing)
}

// parseGrammar matches VERB ( SEP TOKEN )* over the whole string.
// A nil token slice with a non-empty verb means the tail did not parse.
func parseGrammar(text string, verbs []string) (verb string, toks []string, ok bool) {
	for _, v := range verbs {
		if !strings.HasPrefix(text, v) {
			continue
		}
		rest := text[len(v):]
		out := []string{}
		for rest != "" {
			sep := ""
			for _, s := range seps {
				if strings.HasPrefix(rest, s) {
					sep = s
					break
				}
			}
			if sep == "" {
				return v, nil, false
			}
			rest = strings.TrimLeft(rest[len(sep):], " ")
			tok := ""
			for _, t := range tokens {
				if strings.HasPrefix(rest, t) {
					tok = t
					break
				}
			}
			if tok == "" {
				return v, nil, false
			}
			out = append(out, tok)
			rest = rest[len(tok):]
		}
		return v, out, true
	}
	return "", nil, false
}

func containsAny(text string, needles []string) bool {
	for _, n := range needles {
		if strings.Contains(text, n) {
			return true
		}
	}
	return false
}

// ParseConfirm decides whether `quote` approves `gate`. For a defect_origin
// gate, `origin` is the origin the gate is asking about: a quote naming a
// different one is a mismatch, not an approval.
func ParseConfirm(quote string, gate GateType, origin string) Result {
	text := Normalize(quote)
	if text == "" {
		return Result{Reason: ReasonNoVerb}
	}
	// Questions first: 同意吗 should report that it is a question, not that
	// its tail failed to parse.
	if containsAny(text, questionMarks) {
		return Result{Reason: ReasonQuestion}
	}
	verb, toks, ok := parseGrammar(text, confirmVerbs)
	if verb == "" {
		return Result{Reason: ReasonNoVerb}
	}
	if !ok {
		return Result{Reason: ReasonUnparsedTail}
	}
	// Unreachable while every token above is free of these markers; kept so
	// that adding a token cannot quietly open a hole.
	if containsAny(text, negationCJK) || negationASCII.MatchString(text) {
		return Result{Reason: ReasonNegation}
	}
	if containsAny(text, hesitation) {
		return Result{Reason: ReasonHesitation}
	}

	switch gate {
	case GateDefectOrigin:
		want := "origin=" + strings.ToLower(strings.TrimSpace(origin))
		if !contains(toks, want) {
			return Result{Reason: ReasonKeywordMismatch, Tokens: toks}
		}
	case GateReopenBaseline:
		if !contains(toks, "解除密封") && !contains(toks, "reopen") {
			return Result{Reason: ReasonKeywordMismatch, Tokens: toks}
		}
	}
	return Result{OK: true, Reason: ReasonOK, Tokens: toks}
}

// IsConfirm is ParseConfirm for gates with no keyword requirement.
func IsConfirm(quote string) bool { return ParseConfirm(quote, "", "").OK }

// IsReject reports whether the quote refuses. 驳回 is the only verb.
func IsReject(quote string) bool {
	verb, _, ok := parseGrammar(Normalize(quote), rejectVerbs)
	return verb != "" && ok
}

func contains(xs []string, want string) bool {
	for _, x := range xs {
		if x == want {
			return true
		}
	}
	return false
}
