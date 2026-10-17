---
name: Go 迁移 golden 安全网机制
description: >-
  Python→Go 迁移期间，cases.yaml 双端共享 + 39 个 golden 快照 + record.sh PYTHONUNBUFFERED
  确定性锁定的验证机制（2026-10-17 全链验证通过）
type: project
---

Go 迁移（P1 起）的安全网由三部分组成，改动任一部分都必须全链验证：
1. test/signoff/cases.yaml：Python（scripts/test_signoff.py）与 Go（internal/domain/signoff/signoff_test.go）共同读取——改用例必须双端跑。
2. test/golden/legacy/：39 个 .txtar 快照，`bash test/golden/record.sh --verify` 校验（差异即 exit 1）。
3. record.sh 顶部 export PYTHONUNBUFFERED=1：锁 stdout/stderr 交错顺序（$(...) 捕获下块缓冲会导致顺序随环境漂移，2026-10-17 曾出 2 个 golden 伪 DIFF）。

**Why:** golden 锁定当前行为供 Go 端对拍，伪 DIFF 会破坏对拍可信度。

**How to apply:** 改 CLI 脚本（workflow.py/delegation.py/check-feature.py/stage-gate.py/trace.py）输出或 cases.yaml 后：pytest + go test signoff + record.sh --verify 三者全绿才算过。注入用例：码点不得与既有注入节（U+200B、U+1F44D）重复；不可见字符一律 \uXXXX 转义。

2026-10-17 基线（提交 3132a79 后）：go test ./... -race 全绿 + pytest scripts/ 62 passed + record.sh --verify 39 same 0 different。验收就绪，D 组不动。