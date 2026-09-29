# 端到端交付契约（schema_version 2）

编排现有资产，不另起规格树或第二套测试框架。v2 增加密封基线与 `req-review`。旧 v1 文件缺 `baseline.yaml` 时从 `req-review` 补，不准把已有 `req.yaml` 当成已评审基线。

`<票目录>` 只认 `scripts/lib/doc_home.py --key task`。人读规格只认 `--key spec`。已有规范文档时，这两条才分别落在 `docs/task/<feature>/` 与 `docs/spec/<feature>.md`（仓声明 `docs/specs/` 时是复数）。还没有时落在 `.idev/` 下的同名相对路径。只写在一边的票留在原处。

| 阶段产物 | 路径 | 已有家 |
|----------|------|--------|
| 人读规格 | `doc_home.py --key spec` | **只复述**密封基线；冲突以 baseline 为准，改规格 |
| **密封基线** | `<票目录>/baseline.yaml` | 本契约；`sealed: true` 后下游只读 |
| 机读拆解 | `<票目录>/req.yaml` | 基线的译文，不得增删 must |
| 方案叙述 | `<票目录>/design.md` | 平台级取舍另写 ADR |
| 机读架构 + 用例意图 | `<票目录>/arch.yaml` | 本契约 |
| 阶段指针 / 回退 | `<票目录>/deliver.yaml` | 本契约 |
| 可执行验收 | `<票目录>/verify/plan.yaml` | idev verify 模块 |
| 未决问句 | `<票目录>/grill.md` | grilling 的问句；`sealed: true` 时 frontier 必须已空 |
| Review | `<票目录>/review.md` | code 阶段对照基线。不是 `reviews/`，也不是 `.idev/reviews/` |
| 阶段计数 | `<票目录>/deliver-eval.md` | 每阶段结束；只计件数 |
| 排障单 | `<票目录>/ops.yaml` | ops 模块；红绿仍在 verify |

扩展加本文件登记表。不兼容升 `schema_version` + ADR。未知字段忽略。  
专家拒过清单：[experts.md](experts.md)。

## 阶段（只许向前一格或回退到 defect_origin）

| stage | 入口门槛 | 本阶段交付 | 人确认后才能离开 |
|-------|----------|------------|------------------|
| `req-review` | 人给 feature + 原始诉求 | `baseline.yaml` + 规格正文；拷问至无 `open` / 无异议 | `sealed: true` |
| `req` | 基线已密封 | `req.yaml`（每条 slice 挂 `baseline_item_id`） | `accepted: true` |
| `arch` | `req.accepted` | `design.md` + `arch.yaml` | `accepted: true` |
| `code` | `arch.accepted` | 代码 + Review + **verify `logic`/`selftest`** | 自测门 |
| `test` | 自测门 | **verify `mode=test`**，对齐基线 item | 提测门 |
| `done` | 提测门 + 人 `aligned: true` | 基线未 reopen 则不再改原文 | 人签 |
| `ops` | 已是 `done`，或交付中途就地 debug（不改 stage） | `ops.yaml` 分类；verify `debug`/`patrol` 或 handoff | 人写 `resolved` 或确认 `defect_origin` |

禁止跳阶段。禁止把 `done` 当成 AI 盖章。`ops` 不是缺陷 origin。

`deliver.yaml.risk_tier`：`P0` \| `P1` \| `P2`，默认 `P1`。停问次数见入口 `invoke.md`；放置与证明见 [hitl-risk-tiers.md](../../references/hitl-risk-tiers.md)。verify 被本阶段机调用时，`plan.goal` / `non_goal` **复制**密封基线，不准另写一套意图。

## `deliver.yaml` `semantic_gate`

每人签离开一阶段时，与 `sealed` / `accepted` / `aligned` **同一次确认**写入对应子键（见 [chat-confirm-signoff.md](../../references/chat-confirm-signoff.md)）。`by` 必须是人名。

| 子键 | 何时写入 | 下一阶段 `check-feature` 必有 |
|------|----------|-------------------------------|
| `req-review` | 人 `sealed` | `req` / `arch` / `code` / `test` |
| `req` | 人 `accepted` 拆解 | `arch` / `code` / `test` |
| `arch` | 人 `accepted` 方案 | `code` / `test` |
| `code` | 进 `test` 时可选同记 | 不挡 `check-feature test`（自测门仍走 verify） |

```yaml
semantic_gate:
  req-review:
    passed: true
    by: example-owner
```

脚本另锁：`req.yaml` 每条 `slice.must` 与对应 item 的 `must`（无则 `must_not`）原文一致（空白归一）。人检表仍见 [semantic-gate.md](semantic-gate.md)。

## 密封基线（后续不得推翻）

`baseline.yaml`：`goal` / `non_goal` / `items[]` / `boundaries` / `details` / `review_questions` / `objections`。新的未决问句写 `grill.md`，不要在 `review_questions` 里再开一份。残留的 `status: open` 或 `objections` 仍使检查失败。

- `sealed: true` 人手改 YAML，或本轮确认用语按 [chat-confirm-signoff.md](../../references/chat-confirm-signoff.md) 代写。密封后拆解、架构、编码、测试、反馈 **不准改这些字段**。
- 下游只许引用 `items[].id`（`baseline_item_id`）。验收尺是基线，不是后来的口头或切片发挥。
- 切片译错、方案错、代码错：回退 `req` / `arch` / `code`，**重译或重做，不改基线**。
- 实现与基线打架：标 `baseline-conflict`，**停**。两条路：在基线内改实现，或人写 `reopen_baseline: true` 回到 `req-review` 再拷问。Agent 不得自行 unseal。
- `defect_origin` **不得**是 `req-review`，除非人已 `reopen_baseline`。
- reopen：`revision + 1`；**禁止**用旧 `items[].id` 装新 must。旧 id 的 slice / case 全部作废（证据保留，status 不改写为 PASS）。

## 回退

反馈 `defect_origin`: `req` \| `arch` \| `code`（`req-review` 仅 reopen）。  
拷问确认 origin 之后：

1. `deliver.yaml.stage` 回到 origin（reopen 则回 `req-review` 并 `sealed: false`）。
2. origin **之后**的 accepted / aligned 失效（写 `revisions`，不删证据）。基线正文仅在 reopen 时解封。
3. 从 origin 再向后走。不得只改代码假装基线已变。

未拷问确认 origin 前，不准回退、不准继续向后。

## `baseline.yaml`

| 字段 | 约束 |
|------|------|
| `items[]` | `id` + `must` 或 `must_not`；评审对象 |
| `review_questions[]` | 保持空。未决问句在 `grill.md` |
| `objections[]` | 保持空。异议写进 `grill.md`，清空后再密封 |
| `sealed` | 人改 true，或确认用语代写 |

正确、合理、边界、细节：拷问到人无异议。与 CONTEXT / ADR 冲突必须进 `grill.md`，禁止默认为「就这么做」。文件合同见 [docs/SKILL.md](../../docs/SKILL.md)。

## `req.yaml`

| 字段 | 约束 |
|------|------|
| `baseline_revision` | 必须等于当前密封基线 revision |
| `slices[]` | `id` + `baseline_item_id` + `must` + `must_not` + `accept_hint` |
| `open_questions[]` | 只许问**译法**，不许改基线义务 |
| `accepted` | 人改 true，或确认用语代写 |

- 每个 `baseline.items` 至少一条 slice；每个 slice 恰好挂一条 `baseline_item_id`。
- slice.must 必须与对应 item 的 `must`（无则 `must_not`）原文一致（空白归一）。超出 / 换词 = 拒过，回拆解，不改基线。
- 结合整仓是为了译准和找风险，不是为了加需求。

## `arch.yaml`

| 字段 | 约束 |
|------|------|
| `baseline_revision` / `req_revision` | 对应当时密封本与拆解 |
| `approach` / `non_approach` | 不得改写基线 goal/non_goal |
| `impact_candidates` | hop ≤ 1，人 `include` |
| `case_intents[]` | `id` + `slice_id` + `baseline_item_id` + `dimension` + `hint` |
| `accepted` | 人改 true，或确认用语代写 |

每个 include 的影响面、每条基线 item 至少一条 `case_intents`。

## 自测门 / 提测门

尺是**密封基线**，不是 slices 自己长出来的句子。

**自测门**：verify selftest/logic 已 run；无 FAIL；能跑的必覆盖维不是假 UNPROVEN；每条基线 item 至少一 case；无确认用语不写人签。

**提测门**：自测门仍在；`mode=test`；每条基线 item 至少一 test case；UNPROVEN 仅缺基线场景或基线里已写明的 non_goal；无未关闭 origin；无 `baseline-conflict`。

`aligned: true` 人手改 YAML，或提测停问点确认用语代写。

## 反馈标签

| tag | 默认 origin | 可否改基线 |
|-----|-------------|------------|
| `req-gap` / `req-ambiguous` | `req`（译法） | 否 |
| `baseline-conflict` | 停；等人选「基线内修」或 reopen | 仅 reopen |
| `arch-mismatch` | `arch` | 否 |
| `code-defect` | `code` | 否 |
| `case-misaligned` | `arch` 或 `code` | 否 |
| `prod-regression` | `code`（默认；人可改） | 否 |
| `ops-handoff` | 不回退；交给当前产品 `.idev/handoff.yaml` 里的 Skill | 否 |
| `ops-env-mismatch` | 停；先对齐环境/产物 | 否 |

改 Skill 的标签仍走 verify evolve，不走本表。
