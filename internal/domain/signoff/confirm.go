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
	confirmVerbs = []string{
		"就按建议", "按建议", "按推荐", "听你的",
		"选a", "选b", "选c", "选d", "选1", "选2", "选3", "选4", "选5",
		"按这个方案", "按这个", "没问题", "无异议", "就这样", "可以",
		"架构通过", "需求通过", "实现通过", "提测通过", "审核通过",
		"确认", "全签", "同意", "lgtm", "通过",
	}
	plainAgree = map[string]bool{
		"可以": true, "就这样": true, "按这个": true, "按这个方案": true,
		"没问题": true, "无异议": true, "行": true,
		"就按建议": true, "按建议": true, "按推荐": true, "听你的": true,
		"a": true, "b": true, "c": true, "d": true,
		"1": true, "2": true, "3": true, "4": true, "5": true,
		"选a": true, "选b": true, "选c": true, "选d": true,
		"选1": true, "选2": true, "选3": true, "选4": true, "选5": true,
	}
	rejectVerbs = []string{"驳回"}

	// After NFKC the full-width separators fold onto ASCII, so this list is
	// shorter than it looks.
	seps = []string{" ", "，", ",", "：", ":"}

	// The only qualifiers a confirmation may carry. Anything else means the
	// person wrote prose, and prose is not a signoff.
	tokens = []string{
		"不用一直询问", "不用再问",
		"重新打开基线", "打开基线",
		"回退到需求", "回退到架构", "回退到实现",
		"问题在需求", "问题在架构", "问题在编码", "问题在代码",
		"缺陷在需求", "缺陷在架构", "缺陷在实现",
		"origin=req", "origin=arch", "origin=code",
		"解除密封", "reopen", "sealed", "accepted", "aligned", "resolved",
		"plan", "方案", "拆解", "基线", "提测",
		"continue", "okay", "继续", "好的", "收到", "next", "ok", "go", "嗯", "好",
	}
	negationExempt = []string{"没问题", "无异议", "不用一直询问", "不用再问"}
	originPhrases  = []struct{ origin, phrase string }{
		{"req", "origin=req"}, {"req", "回退到需求"}, {"req", "问题在需求"}, {"req", "缺陷在需求"},
		{"arch", "origin=arch"}, {"arch", "回退到架构"}, {"arch", "问题在架构"}, {"arch", "缺陷在架构"},
		{"code", "origin=code"}, {"code", "回退到实现"}, {"code", "问题在编码"}, {"code", "问题在代码"}, {"code", "缺陷在实现"},
	}
	reopenPhrases = []string{"解除密封", "reopen", "重新打开基线", "打开基线", "解封"}

	questionMarks = []string{"?", "？", "吗", "么", "嘛", "呢", "是否", "能否", "可否", "要不要"}
	negationCJK   = []string{"不", "没", "别", "未", "否", "勿"}
	hesitation    = []string{"先", "等", "再说", "待定", "也许", "可能", "吧"}

	negationASCII = regexp.MustCompile(`\b(?:not|no|don't|wait|but|hold|later)\b`)
	choiceSpace   = regexp.MustCompile(`^选\s+([a-d1-5])$`)

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
		rest = strings.TrimPrefix(rest, "了")
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

func foldChoice(text string) (string, bool) {
	m := choiceSpace.FindStringSubmatch(text)
	if m == nil {
		return text, false
	}
	return "选" + m[1], true
}

func scanText(text string) string {
	for _, phrase := range negationExempt {
		text = strings.ReplaceAll(text, phrase, "")
	}
	return text
}

// namedAction reports a rollback origin or an unseal when the reply names it.
// kind is "origin" or "reopen".
func namedAction(text string) (kind, value string, ok bool) {
	for _, item := range originPhrases {
		if strings.Contains(text, item.phrase) {
			return "origin", item.origin, true
		}
	}
	if containsAny(text, reopenPhrases) {
		return "reopen", "", true
	}
	return "", "", false
}

func withCanonical(toks []string, text string) []string {
	out := append([]string{}, toks...)
	kind, value, ok := namedAction(text)
	if !ok {
		return out
	}
	if kind == "origin" {
		key := "origin=" + value
		if !contains(out, key) {
			out = append(out, key)
		}
		return out
	}
	if !contains(out, "解除密封") && !contains(out, "reopen") {
		out = append(out, "解除密封")
	}
	return out
}

func finishGate(gate GateType, origin string, toks []string, text string) Result {
	kind, value, named := namedAction(text)
	canon := withCanonical(toks, text)
	switch gate {
	case GateDefectOrigin:
		want := strings.ToLower(strings.TrimSpace(origin))
		if !named || kind != "origin" || value != want {
			return Result{Reason: ReasonKeywordMismatch, Tokens: canon}
		}
		return Result{OK: true, Reason: ReasonOK, Tokens: canon}
	case GateReopenBaseline:
		if !named || kind != "reopen" {
			return Result{Reason: ReasonKeywordMismatch, Tokens: canon}
		}
		return Result{OK: true, Reason: ReasonOK, Tokens: canon}
	}
	if gate != "" && named {
		return Result{Reason: ReasonKeywordMismatch, Tokens: canon}
	}
	return Result{OK: true, Reason: ReasonOK, Tokens: canon}
}

// ParseConfirm decides whether `quote` shows agreement with `gate`.
// Agreement is the person's words making the same picture. A question, a
// refusal, a hesitation or a stray character is not agreement. For a
// defect_origin gate, `origin` is the origin the gate is asking about.
func ParseConfirm(quote string, gate GateType, origin string) Result {
	text := Normalize(quote)
	if folded, ok := foldChoice(text); ok {
		text = folded
	}
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
		if _, _, named := namedAction(text); named && gate != "" {
			if r, refused := refusal(text); refused {
				return r
			}
			return finishGate(gate, origin, nil, text)
		}
		if plainAgree[text] {
			if gate == GateDefectOrigin || gate == GateReopenBaseline {
				return Result{Reason: ReasonKeywordMismatch}
			}
			return Result{OK: true, Reason: ReasonOK}
		}
		return Result{Reason: ReasonNoVerb}
	}
	if !ok {
		return Result{Reason: ReasonUnparsedTail}
	}
	if r, refused := refusal(text); refused {
		return r
	}
	return finishGate(gate, origin, toks, text)
}

// refusal reports a negation or a hesitation in the reply. It applies to a
// reply that only names the action as much as to one with a verb.
func refusal(text string) (Result, bool) {
	scan := scanText(text)
	if containsAny(scan, negationCJK) || negationASCII.MatchString(scan) {
		return Result{Reason: ReasonNegation}, true
	}
	if containsAny(scan, hesitation) {
		return Result{Reason: ReasonHesitation}, true
	}
	return Result{}, false
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
