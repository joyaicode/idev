---
name: idev 效率根因与删除预算收口
description: 2026-11-07 效率根因提案全项 landed，删除预算唯一真源收敛到 self-evolution
type: project
---

2026-11-07 收口 `state/proposals/20261104-efficiency-root-cause.md`：删除 `references/deletion-budget.md`，删除预算、`skills/` 范围盲点、自建期退出条件与精读沉淀豁免只保留在 `references/self-evolution.md`。

**Why:** 该参考页正文已并入 self-evolution，双处记账会让后续修改只改一处；同时内核自己的规则要求触发删除预算报警后下一刀做 delete pass，而不是继续新增指针。

**How to apply:** 讨论内核删除预算、自建期退出条件或 `skills/` 范围时只读 `references/self-evolution.md`；2026-11-07 起 `skills/` 也计入删除预算，`state/` 仍不计入。新增 `references/` 页前先看外部票占比；落到 `conventions/` 已有页的精读沉淀不受这条约束。证据见 `state/proposals/20261104-efficiency-root-cause.md` 与 `state/proposals/20261107-deletion-budget-skills-scope.md`。
