# HITL 风险分层（对照业界，落到 idev）

对照：风险档位闸门、闸门放在**不可逆动作之前**、审批须带证明物（非摘要橡皮图章）。  
本页只讲**为什么**这样放。每个档位停哪里、怎么签、何时 `AUTO`，只在 [chat-confirm-signoff.md](chat-confirm-signoff.md)。

## 原则

1. **可逆、低爆破**可快路径（P2 / lite-change）。解封、回退、promote、生产写、push、经验入库必须人点名。`sealed` / `accepted` / `aligned` 在检查通过且没有未决分叉时写入。
2. 闸门放在**副作用前**：先让 Agent 起草 plan / 跑自测 / 写报告。检查通过就写 `sealed` / `accepted` / `aligned`。`promote.sh` 仍等人点名。
2a. **不清楚处先 grilling：** 边界、异议或分叉没订死，先自动唤起 grilling。没有分叉不要送人盖章。
3. 真要问的那一次必须带**证明上下文**（见 [chat-confirm-signoff.md](chat-confirm-signoff.md) §证明上下文），避免只批摘要。
4. 进度信任：周审计里「`AUTO` / `[非承重]` 后被推翻」的次数，才是再加停点的依据。交付主路径不为确认停。promote 仍等人点名。
5. 停问看信号，不看位置：AI 拿不准（`BLOCKED(logic)`、`[承重]` 假设、`ARTIFACT: UNKNOWN`）或卡住时才问；机检能判的点不让人盖章。当前工程的人岗关系先认出来，交互按这个编制收束。做法只在 [chat-confirm-signoff.md](chat-confirm-signoff.md)。

档位的典型：P0 鉴权 / 数据面 / 跨仓契约；P1 默认功能票；P2 文档 / 小修 / 低爆破。

## 与开源 SDD 的对齐（不换栈）

| 业界 / 开源 | idev 对应 |
|-------------|-----------|
| Spec Kit：specify → plan → tasks → implement → converge | 密封基线 → req → arch → code。取舍全文 [spec-kit-mapping.md](spec-kit-mapping.md) |
| OpenSpec：提案/规格/设计后再任务 | grilling + arch.accepted 后才 code |
| Promote / 巡检包 | `verify/scripts/promote.sh`（人触发） |
| CI 绿 + 证明物 | `check-feature` + plan evidence；**不**替代仓内 CI |

idev **不**内置并行 PR 阶段机；仓内 CI/MR 仍是产品仓责任。配方里同一 `group`、`writes` 不相交的 verify 步骤可以同时开，那是订死写集之后的一波。
