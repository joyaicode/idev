package main

import (
	"strings"
	"testing"
)

// parseFanLines reads fanout.py's stable line protocol. These tests lock
// the three verdicts the wave loop branches on (MERGE / SERIAL / FANOUT
// with shards and a queued tail) and the PREP extraction.
func TestParseFanLines(t *testing.T) {
	merged := parseFanLines(strings.Join([]string{
		"MERGE report shard drafts are in; do not delegate",
		"MERGE python3 scripts/fanout.py merge --feature f --activity report",
		"DOCK reason=MERGE-DUE loop=fanout report shard drafts are in",
	}, "\n"))
	if !merged.merge {
		t.Fatal("merge verdict not parsed")
	}

	serial := parseFanLines("SERIAL report no changed sources to review\nDOCK reason=DELEGATE loop=fanout report stays one agent")
	if !serial.serial || serial.reason != "report no changed sources to review" {
		t.Fatalf("serial verdict wrong: %+v", serial)
	}

	fan := parseFanLines(strings.Join([]string{
		"FANOUT report 5 cap=5",
		"DOCK reason=PARALLEL-WAVE loop=fanout report splits into 5 shards",
		"PREP bash /kernel/scripts/coding-scan.sh /repo",
		"SHARD lens-correctness AGENT idev-reviewer WRITES review/shards/lens-correctness.md",
		"SCOPE 五轴之「正确性」深读全部改动源: mod/A.java",
		"SHARD lens-readability AGENT idev-reviewer WRITES review/shards/lens-readability.md",
		"SHARD lens-architecture AGENT idev-reviewer WRITES review/shards/lens-architecture.md",
		"SHARD lens-security AGENT idev-reviewer WRITES review/shards/lens-security.md",
		"SHARD lens-performance AGENT idev-reviewer WRITES review/shards/lens-performance.md",
		"MERGE python3 scripts/fanout.py merge --feature f --activity report",
	}, "\n"))
	if fan.serial || fan.merge {
		t.Fatalf("fanout verdict misread: %+v", fan)
	}
	if len(fan.shardID) != 5 || fan.shardID[0] != "lens-correctness" {
		t.Fatalf("shard ids wrong: %v", fan.shardID)
	}
	if len(fan.prep) != 1 || !strings.HasSuffix(fan.prep[0], "coding-scan.sh /repo") {
		t.Fatalf("prep wrong: %v", fan.prep)
	}

	queued := parseFanLines(strings.Join([]string{
		"FANOUT report 4 cap=4",
		"SHARD mod-a AGENT idev-reviewer WRITES review/shards/mod-a.md",
		"QUEUED mod-b",
		"QUEUED mod-c",
	}, "\n"))
	if len(queued.queued) != 2 || queued.queued[0] != "mod-b" {
		t.Fatalf("queued tail wrong: %v", queued.queued)
	}
}

// The merge instruction line (MERGE python3 ...) must never read as a
// merge verdict — the verdict only comes with "shard drafts are in".
func TestParseFanLinesMergeInstructionIsNotAVerdict(t *testing.T) {
	p := parseFanLines("MERGE python3 scripts/fanout.py merge --feature f --activity report")
	if p.merge {
		t.Fatal("instruction line parsed as verdict")
	}
}
