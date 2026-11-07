---
name: Python C9 存量清理收口
description: 2026-11-07 清零 Python C9 嵌套债务，并修正表达式 if 误报；C7/C12 仍另算
type: project
---

2026-11-07 执行 trace `20261105-004` 的推荐，完成 Python C9 存量清理。重构前 16 个目标文件有 91 个正则命中，AST 审计后确认 84 个真实 `if` 语句、7 个表达式 `if` 误报；当前 168 个 Python 文件 C9=0。

**Why:** C9 已在 `conventions/coding-tables.md` 定义，缺的是执行。为降噪放宽规则会把真实三层嵌套放走；不修检测器则会把三元表达式与 comprehension 续行误报成债务。

**How to apply:** 修改 Python 时保持 `if` 嵌套不超过两层，优先用守护子句、阶段函数或判定 helper 拆平；`scripts/plugin/python_inspect.py` 已用 `ast.If` 行号过滤表达式 `if`，命中即视为真实控制流问题。剩余 C7/C12 是独立债务，勿与 C9 混为一轮。证据见 `state/traces/20261107-001.yaml`。
