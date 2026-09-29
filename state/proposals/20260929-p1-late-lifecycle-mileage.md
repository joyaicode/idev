# 提案 P1：后半段生命周期补里程（test → aligned → done → ops/promote）

- status: draft
- scope: 非 idev 源码改动——需在真实产品仓跑一个完整票；idev 侧仅可能微调后半段门禁/文档
- created: 2026-09-29
- signal: 人工审计；后半段实证空洞

## 诊断（证据，非主观）

前半段（req-review→arch→code）有真实产物背书，后半段几乎无真实里程：

1. JoyPaaS 三个真实票全部停在前半段：
   - `joypaas-approval-annotation-receipt`: stage=arch, aligned=false
   - `joypaas-approval-annotation-template`: stage=code, aligned=false
   - `joypaas-approval-pre-post-check`: stage=code, aligned=false
2. **无任何票到 done**（`aligned` 全 false）。
3. 全仓仅 1 个孤立巡检包 `joypaas-product-locks-patrol.yaml`，无对应 ops.yaml，无法证明 promote 是从完整 accepted plan 快照而来。
4. **零 ops.yaml**：ops 模块（分类/debug/handoff/回退 origin）、canon T10（数据系统五项）、T11（可运维性）这些「投产后」规则的真实验证 = 0。

后果：check-feature.py 中 `stage in (test, ops)` 的大量分支、`check_unproven_surfaces` 维表六族、promote 快照逻辑、防伪造 signoff 在 aligned/resolved 上的行为，**从未在真实 diff 上打过**。这是整套 skill 实证最薄的一段。

## 要做什么（这是跑票，不是改 skill）

选一个最接近完成的票（建议 `joypaas-approval-pre-post-check`，已在 code），推完后半段全程，把门禁在真实场景打一遍：

1. code → 起草 verify plan（mode=selftest）→ 人 accepted → run 转绿。
2. 人说「提测」→ plan mode=test，补齐维表六族（correctness 必须可执行用例，其余可 UNPROVEN 但须显式）→ `check-feature.sh <f> test`。
3. 人写 `aligned: true` + by → stage=done。观察 check-feature 对 aligned 的防伪造 by 是否按预期。
4. （可选，人主动提 promote 才做）`promote.sh <f>` 生成巡检包，验证它吃的是快照 plan、拒 FAIL/空 PASS。
5. 若真实场景中触及数据/异步/上线路径，走一遍 canon T10/T11 记账，验证 arch 出门 A4/A6 在真实票里能否答满。

## idev 侧可能的微调（跑票中若发现才改，先记这里）

- 后半段门禁的**误报**：若 test/ops 阶段 check-feature 报了「格式噪音」而非真问题，记下来进 P4 提案。
- 若发现 test→done 的停问点/H6 在真实流里摩擦大，记录，不当场改。

## 不做什么

- 不为了「跑通」而伪造 aligned/PASS/by（那正是 skill 要防的）。
- 不在没有人确认的情况下自动 seal/aligned/promote。
- 不改 JoyPaaS 业务逻辑去迁就门禁——若门禁误伤，改门禁提案，不改业务。

## 验收

- 至少 1 个真实票走到 `stage=done`（aligned=true, 人 by）。
- 后半段每个门禁分支被真实数据触发过至少一次（可用 trace + check-feature 输出证明）。
- 若跑出 promote：巡检包证据链完整（快照 plan + receipt）。
- 跑票产生的经验教训回提为 P4 提案或直接 land（走 grill）。
