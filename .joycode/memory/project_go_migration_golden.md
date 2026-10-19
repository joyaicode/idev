---
name: Go 迁移 golden 安全网机制
description: >-
  Python→Go 迁移期间，cases.yaml 双端共享 + 50 个 golden 快照 + record.sh PYTHONUNBUFFERED
  确定性锁定的验证机制（2026-10-19 全链验证通过）
type: project
---

安全网三部分，改动任一部分必须全链验证：
1. test/signoff/cases.yaml：Python（test_signoff.py）与 Go（signoff_test.go）共同读取，改用例双端跑。
2. test/golden/legacy/：50 个 .txtar，record.sh --verify 校验。39→50 的 11 个增量为 2026-10-19 签字信号提案（gate-auto/decide/delegation-signal 等系列）。
3. record.sh 顶部 PYTHONUNBUFFERED=1 锁 stdout/stderr 交错（块缓冲曾致 2026-10-17 两个伪 DIFF）。

**Why:** golden 锁定行为供 Go 对拍，伪 DIFF 破坏对拍可信度。

**How to apply:** 改 CLI 脚本输出或 cases.yaml 后，pytest + go test signoff + record.sh --verify 三绿才算过。注入码点不得与既有节（U+200B、U+1F44D）重复，不可见字符一律 \uXXXX 转义。

2026-10-19 基线（b96b6c9 后全量）：golden 50/50、go test 22 包、selfcheck 26 锁、agent-smoke 481、test_signoff 165（105/7/53）、test_signals 6、gate-channel 14、lease-channel 13、refs/syntax/agents/gen-kinds PASS。D 组不动。