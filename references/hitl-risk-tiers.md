# HITL 风险分层（对照业界，落到 idev）

对照：风险档位闸门、闸门放在**不可逆动作之前**、审批须带证明物（非摘要橡皮图章）。  
本页只讲**为什么**这样放。每个档位停哪里、怎么签、何时 `AUTO`，只在 [chat-confirm-signoff.md](chat-confirm-signoff.md)。

## 原则

1. **可逆、低爆破**可快路径（P2 / lite-change）；**不可逆**必须人闸（seal / aligned / promote / 生产写）。
2. 闸门放在**副作用前**：先让 Agent 起草 plan / 跑自测 / 写报告；人确认后再写 `sealed`/`accepted`/`aligned` 或跑 `promote.sh`。
2a. **不清楚处先 grilling：** 需求分析与任何确认闸前，若边界/异议/分叉未订死，先自动唤起 grilling；不要把含糊摘要直接送人盖章。
3. 请签必须带**证明上下文**（见 [chat-confirm-signoff.md](chat-confirm-signoff.md) §证明上下文），避免只批摘要。
4. 进度信任：周审计里「`AUTO` / `[非承重]` 后被推翻」的次数低，才考虑再降停问。交付主路径每个档位停四次：需求通过、架构通过、实现审核、提测结果。promote 在每个档位都留下人的确认。
5. 停问看信号，不看位置：AI 拿不准（`BLOCKED(logic)`、`[承重]` 假设、`ARTIFACT: UNKNOWN`）或卡住时才问；机检能判的点不让人盖章。

档位的典型：P0 鉴权 / 数据面 / 跨仓契约；P1 默认功能票；P2 文档 / 小修 / 低爆破。

## 与开源 SDD 的对齐（不换栈）

| 业界 / 开源 | idev 对应 |
|-------------|-----------|
| Spec Kit：specify → plan → tasks → implement | baseline seal → req → arch → code |
| OpenSpec：提案/规格/设计后再任务 | grilling + arch.accepted 后才 code |
| Promote / 巡检包 | `verify/scripts/promote.sh`（人触发） |
| CI 绿 + 证明物 | `check-feature` + plan evidence；**不**替代仓内 CI |

idev **不**内置并行 PR 阶段机；仓内 CI/MR 仍是产品仓责任。
