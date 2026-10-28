#!/usr/bin/env python3
"""Path view keeps each hop's thought, observation, and the react file."""
from __future__ import annotations

import unittest

import trace

TEXT = """\
schema_version: 2
at: "2026-10-26T14:00:00+08:00"
feature: demo
intent: "看这一跳"
react: state/react/demo--look.yaml
invoke:
  trigger: "看"
  matched: "关节"
  how: explicit
route:
  module: deliver
  scenario: S1
  why: "要看见每一跳"
calls:
  - kind: tool
    name: stage-gate
    from: react:look
    to: tool:stage-gate
    why: "gate looks red"
    result: "gate red"
    duration_s: "1.2"
  - kind: script
    name: test_trace_view.py
    from: conductor
    to: script:test_trace_view.py
    thinking: "keep the old note"
    result: "ok"
"""


class TraceView(unittest.TestCase):
    def test_each_hop_keeps_thought_and_observation(self):
        shown = trace.render_path(TEXT, name="demo.yaml")
        self.assertIn("react:    state/react/demo--look.yaml", shown)
        self.assertIn("追踪:", shown)
        self.assertIn("1. react:look → tool:stage-gate", shown)
        self.assertIn("why: gate looks red", shown)
        self.assertIn("result: gate red", shown)
        self.assertIn("1.2s", shown)
        self.assertIn("why: keep the old note", shown)
        hops = trace.hops_line(trace.dash_maps(TEXT, "calls"))
        self.assertIn("「gate looks red」", hops)
        self.assertIn("「keep the old note」", hops)


if __name__ == "__main__":
    unittest.main()
