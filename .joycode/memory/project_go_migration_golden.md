---
name: Go 迁移 golden 安全网机制
description: >-
  Python→Go 迁移期间，cases.yaml 双端共享 + 39 个 golden 快照 + record.sh PYTHONUNBUFFERED
  确定性锁定的验证机制（2026-10-17 状态）
type: project
---

Go 迁移（P1 起）的安全网由三部分组成，改动任一部分都必须全链验证：
1. test/signoff/cases.yaml：112 用例行（confirm 105 + reject 7）+ 44 身份行，被 Python（scripts/test_signoff.py，12 tests）和 Go（internal/domain/signoff/signoff_test.go）共同读取——改用例必须双端跑。
2. test/golden/legacy/：39 个 .txtar 快照（workflow/delegation 21 + ticketless 3 + check-feature 六阶段 7 + delegation 三退出码 3 + trace 5），`bash test/golden/record.sh --verify` 校验。
3. record.sh 顶部 export PYTHONUNBUFFERED=1：锁 stdout/stderr 交错顺序（$(...) 捕获下 Python stdout 块缓冲会导致 OK/HINT 与 FAIL/STOP 顺序随环境漂移）。

**Why:** golden 的目的是锁定当前行为供 Go 端对拍；2026-10-17 曾因缓冲环境差异出现 2 个 golden 伪 DIFF。

**How to apply:** 改 CLI 脚本（workflow.py/delegation.py/check-feature.py/stage-gate.py/trace.py）输出或 cases.yaml 后：双端跑 test_signoff + go test signoff + record.sh --verify，三者全绿才算过。注入用例约束：码点不得与既有注入节（U+200B、U+1F44D）重复；不可见字符一律 \uXXXX 转义；regression 标记集合恰为 {"确认不了","同意吗","LGTM but wait","确认？","idev-coder","Claude"}。