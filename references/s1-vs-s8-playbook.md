# 最小跟票剧本：新票 S1 vs 小改 S8

给 Agent / 操作员的一页纸。细节仍以模块 SKILL 为准。  
产品目标：人机共驾；`sealed` / `accepted` / `aligned` 须人确认。

## 先选轨（10 秒）

| 你听到的 | 走 | 不要 |
|----------|----|------|
| 新需求、另开票、没有 `deliver.yaml` | **S1** | 直接 `lite-change` |
| 小改 / 轻量 / 小修；已有票且**不改** goal/baseline/架构 | **S8** `lite-change` | 从 S1 重跑全生命周期 |
| 只跑自测 | **S8** `dev-selftest` | 问要不要提测（除非人说提测） |
| 提测包 / 正式测 | **S8** `test-pack`（须 `stage=test`） | 跳阶段硬推 |
| 说不清 | 读 `doc_home.py --key deliver` 的 `stage` | 猜已 done 的票 |

速查全表：[operator-cheatsheet.md](operator-cheatsheet.md)。

## 轨 A — 新票 S1（最小闭环）

**只开：** `conventions/SKILL.md`（定类）→ `deliver/SKILL.md` → **自动打开** [docs/SKILL.md](../docs/SKILL.md) 与 grilling（缺则先 `scripts/link-companion-skills.sh`）。  
**禁开：** verify / ops / lifecycle 长文。

1. 打开 [docs/SKILL.md](../docs/SKILL.md) 后落票。票里放 `grill.md`、`baseline.yaml`、`deliver.yaml`（`stage: req-review`）。
2. **自动唤起 grilling**：把正确性/合理性/边界/非目标写成 `grill.md`，按当前编制一次问完。只有回答打开这轮没写到的新分叉才再开一轮。回答不是确认。`review_questions` 与 `objections` 保持空。冲突不得默许。frontier 未空不准请签。问谁见 [chat-confirm-signoff.md](chat-confirm-signoff.md)。
3. frontier 空后起草拆解，不在 `req-review` 末另停一次。
4. **需求通过只签一次。** `check-feature.sh <feature> req` 通过后，确认用语同时写 `sealed` 和 `req.accepted`。`继续` 不算。
5. 然后出架构整包等人 Review。后续阶段的停问只认 [chat-confirm-signoff.md](chat-confirm-signoff.md)。

**写 trace：** `route.scenario: S1`，真实 `opened[]` / `calls[]`。

## 轨 B — 小改 S8 `lite-change`（最小闭环）

**前置：**

```bash
bash ~/.cursor/skills/idev/scripts/s8-preflight.sh <feature> lite-change
```

（在产品仓目录执行，或设 `IDEV_REPO`。）BLOCKED → 列缺项后停，不准编造覆盖率。

没有 `PARALLEL` 时只开当前 step 对应的一页。`next` 打出 `PARALLEL` 时，本轮同时派这一波里的每个 `DELEGATE`，每个回报只记自己的 step。

1. `preflight.inputs` — 票/路径可读  
2. `route.s4` — 确认不改 goal/baseline；定界  
3. `deliver.code_pass` — 只改 `include: true`  
4. 同一波 `group: check`：`verify.plan` 写 `verify/plan.yaml`，`verify.run` 写 `verify/selftest.md`，`review.report` 写 `review.md`，验收索引写 `verify/accept.md`  
5. 计划无信号则 `gate-plan` 记 `AUTO`（H4）  
6. `review.fix` 改掉全部 `I*`  
7. `verify.run` 复跑：回写 `plan.yaml` 的 status，并重写 `selftest.md` 与 `accept.md`，然后停在实现审核  
8. **默认结束。** 人没说「提测」不问 `mode=test`（H6）；不自动 promote。

踩坑：[lite-change-pitfalls.md](lite-change-pitfalls.md)。

**写 trace：** `route.scenario: S8`，`invoke.matched: lite-change`。

## 共用硬规则（两轨都守）

- 没有 `PARALLEL` 时每轮一个执行模块；`PARALLEL` 那一波每个 `DELEGATE` 各开自己的页。红绿只走 verify。  
- 边界未订死 / 有 open_questions / 请签前仍有分叉 → **自动 grilling**；未完成前不准请签。  
- 无本轮确认用语不得写 `sealed` / `accepted` / `aligned`。  
- 签字前结构检查 FAIL → 不准请签。  
- 无 Mac 真源 / 无仓路径 → 停，不顶替执行。

## 何时升级 / 换轨

| 情况 | 动作 |
|------|------|
| 小改发现要改 goal / baseline | **停**；人说解除密封 / `reopen` 后回 S1 `req-review` |
| 自测过后人明确「提测」 | S8 `test-pack` 或 S2 推到 `test` |
| 线上/联调现象 | **S6** ops，不要当新需求改 baseline |
