package runyaml_test

import (
	"testing"

	"github.com/idev/internal/adapters/runyaml"
)

func TestStepChangesNamesWhatEachWriteDidToAStep(t *testing.T) {
	pending := runyaml.Step{ID: "fix", Kind: "review.fix"}
	delegated := runyaml.Step{ID: "fix", Kind: "review.fix", Writer: "idev-coder", LeaseID: "L1"}
	failed := runyaml.Step{ID: "fix", Kind: "review.fix", Writer: "idev-coder", Status: "FAIL", At: "t1"}
	passed := runyaml.Step{ID: "fix", Kind: "review.fix", Writer: "idev-coder", Status: "PASS", At: "t2", VerifiedBy: "idev-reviewer"}
	skipped := runyaml.Step{ID: "fix", Kind: "review.fix", Status: "SKIPPED", At: "t1", Evidence: "nothing signed"}

	for _, tc := range []struct {
		name       string
		prev, next runyaml.Step
		verb       runyaml.Verb
		from       string
	}{
		{name: "delegating is not a record", prev: pending, next: delegated},
		{name: "first record", prev: delegated, next: failed, verb: runyaml.VerbRecorded},
		{name: "a FAIL recorded again as PASS", prev: failed, next: passed, verb: runyaml.VerbRecorded, from: "FAIL"},
		{name: "same status, new verification", prev: passed, next: func() runyaml.Step {
			s := passed
			s.VerifiedBy = "idev-ops"
			return s
		}(), verb: runyaml.VerbAmended, from: "PASS"},
		{name: "skipped", prev: pending, next: skipped, verb: runyaml.VerbSkipped},
		{name: "a record cleared for another attempt", prev: failed, next: delegated, verb: runyaml.VerbRetried, from: "FAIL"},
		{name: "unchanged", prev: passed, next: passed},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got := runyaml.StepChanges(runyaml.Doc{Steps: []runyaml.Step{tc.prev}}, runyaml.Doc{Steps: []runyaml.Step{tc.next}})
			if tc.verb == "" {
				if len(got) != 0 {
					t.Fatalf("want no change, got %+v", got)
				}
				return
			}
			if len(got) != 1 || got[0].Verb != tc.verb || got[0].From != tc.from {
				t.Fatalf("want %s from %q, got %+v", tc.verb, tc.from, got)
			}
		})
	}
}
