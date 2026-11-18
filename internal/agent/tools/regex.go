package tools

import (
	"errors"
	"regexp"
	"sync"
)

// A tiny cache: deny rules and read/write signoff patterns compile at
// first use and never again — these run on every tool call, and regexp
// compilation is not free.
var (
	reCacheMu sync.Mutex
	reCache   = map[string]*regexp.Regexp{}
)

func reMatch(pattern, subject string) bool {
	return compileRegexMust(pattern).MatchString(subject)
}

func compileRegex(pattern string) (*regexp.Regexp, error) {
	return regexp.Compile(pattern)
}

func compileRegexMust(pattern string) *regexp.Regexp {
	reCacheMu.Lock()
	defer reCacheMu.Unlock()
	if re, ok := reCache[pattern]; ok {
		return re
	}
	re := regexp.MustCompile(pattern)
	reCache[pattern] = re
	return re
}

func errorsAs(err error, target any) bool {
	return errors.As(err, target)
}
