---
name: idev 设计文档 v3 位置与验收提案结构
description: >-
  重构设计文档已入仓 design/idev-refactor-design-v3.md（提交 b96b6c9，2026-10-19）；验收提案
  state/proposals/ 下 20261016（A/B/C/D 四组）与 20261019（签字按信号，切片 1–3 已落）
type: reference
---

- 重构设计文档：`design/idev-refactor-design-v3.md`（2026-10-19 随提交 b96b6c9 入仓；此前在 ~/Downloads，仓内为权威版，2026-10-17 由 v2 增补质量门章节，只增不改：v1.1 Qodana §6.6、v1.2 e2e §6.7、框架 §6.6.0、§16.5 人签边界、§7.3 DDL、§17.3 配置、§20 任务 T1.9/T2.8–T2.11/T3.7–T3.9/T4.8–T4.9、kinds 29→33）。不要引用 v2 或 ~/Downloads 旧副本。
- 验收提案：`state/proposals/20261016-refactor-capability-acceptance.md`，A/B/C/D 四组（A 迁移验收、B 重构门禁机检、C promptfoo、D 质量门前瞻清单）。D 组全部 PENDING，待 T1.9/T2.8–T2.11 等任务落地时回填；D-0 矩阵的迁移落点已改 00003+（00002 被 gate_subjects 占用）。
- 签字信号提案：`state/proposals/20261019-signoff-by-signal.md`，切片 1–3 已全部落地（b96b6c9），第六节为完成对账表；第五节保留与计划的偏差（保留 step_confirm、不加 decision 类型、只接写租约）与两处未修不一致（lease: verify 时机、runsvc 不自领租约）。
- B 组引用的「§3.4 重构出门」在 `conventions/coding-tables.md`（不是设计文档章节）。

**How to apply:** 讨论质量门/Qodana/e2e 验收时先读仓内 v3 对应章节再对提案 D 组；讨论签字/AUTO 档位/B 类停问时读 20261019 提案第三节（定稿方案）与第六节（完成对账）。