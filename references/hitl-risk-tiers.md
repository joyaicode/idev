# HITL 风险分层（对照业界，落到 idev）

对照：风险档位闸门、闸门放在**不可逆动作之前**、审批须带证明物（非摘要橡皮图章）。  
idev 已有 `deliver.risk_tier`（P0/P1/P2）与 chat-confirm；本页钉死**放哪里 / 要什么证明**。

## 原则

1. **可逆、低爆破**可快路径（P2 / lite-change）；**不可逆**必须人闸（seal / aligned / promote / 生产写）。
2. 闸门放在**副作用前**：先让 Agent 起草 plan / 跑自测 / 写报告；人确认后再写 `sealed`/`accepted`/`aligned` 或跑 `promote.sh`。
2a. **不清楚处先 grilling：** 需求分析与任何确认闸前，若边界/异议/分叉未订死，先自动唤起 grilling；不要把含糊摘要直接送人盖章。
3. 请签必须带**证明上下文**（见 [chat-confirm-signoff.md](chat-confirm-signoff.md) §证明上下文），避免只批摘要。
4. 进度信任：同一配方连续绿可减少 P2 停问，**不得**减少 P0 的 seal/aligned/promote。

## 档位 ↔ 动作

| 档 | 典型 | Agent 可自跑 | 必须人闸（副作用前） |
|----|------|--------------|----------------------|
| P0 | 鉴权/数据面/跨仓契约 | 起草、自测、报告 | seal、arch accept、plan accept、aligned、promote、ops resolved、origin 回退 |
| P1 | 默认功能票 | 同上 + lite-change 编码 | 同 P0 减「拆解可与评审同停」；promote 仍须人提 |
| P2 | 文档/小修/低爆破 | lite-change 全路径至 selftest | 评审（可并拆解）、plan、aligned；promote 仍须人提（H2） |

停问次数细表仍以 [invoke.md](invoke.md)「门禁停问」为准；本页管**放置与证明**。

## 与开源 SDD 的对齐（不换栈）

| 业界 / 开源 | idev 对应 |
|-------------|-----------|
| Spec Kit：specify → plan → tasks → implement | baseline seal → req → arch → code |
| OpenSpec：提案/规格/设计后再任务 | grilling + arch.accepted 后才 code |
| Promote / 巡检包 | `verify/scripts/promote.sh`（人触发） |
| CI 绿 + 证明物 | `check-feature` + plan evidence；**不**替代仓内 CI |

idev **不**内置并行 PR 阶段机；仓内 CI/MR 仍是产品仓责任。
