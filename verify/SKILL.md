---
module: verify
parent: idev
---

# Verify 模块（证据导体）

由 `idev` 按内容调起。本目录不是独立 Skill。只跑红绿，不加 mode 就不开新 Skill。

同一循环，五个 **mode**。AI 提名并跑可执行用例；人确认范围、对需求/设计/架构签字。  
**不是**验收权威，不准把无基线写成达标。  
plan / report 所在的票目录由 `scripts/lib/doc_home.py --key task` 解析，不把路径写死成 `docs/task`。

## 本阶段 5 步（先做这些）

1. 读 `plan.yaml`；无 plan 先起草（goal/non_goal 复制密封基线）。票在 `arch` 时就起草，每条 `case_intent` 一条 case（`slice_id` / `baseline_item_id` / `dimension` 一致），不要等到编码之后另起一套。
2. 请人 `accepted` 或记 `AUTO` 前跑 `check-feature.sh <f> verify-plan`（已 accepted 再 run 不重跑）。
3. 按 mode 跑 cases；只许 PASS/FAIL/UNPROVEN；PASS 必须有证据路径。
4. 提测维表六族：`mode: test` + `unproven.md`；人没提 promote 不问不跑。
5. 写 `conductor-eval` 件数；试运行停问 feedback tags；`trace.sh append`。

| Need | Doc |
|------|-----|
| 怎么用 | [references/how-to.md](references/how-to.md) |
| 契约 / 扩展 | [references/plan-schema.md](references/plan-schema.md) |
| 试运行评估 / 进化 | [references/evolve.md](references/evolve.md) |
| 决策 | [0006](references/0006-verify-conductor.md) · [0007](references/0007-verify-conductor-evolve.md) |
| 排障硬规则 | [conventions/evidence.md](../conventions/evidence.md)（通用真源；`verify-with-cases` 只是指针） |
| 端到端阶段机 | `../deliver`（本模块只跑红绿） |
| 投产后排障 | `../ops`（本模块提供 `debug` / `patrol`） |
| 试运行台账 | [入口 state/ledger.yaml](../state/ledger.yaml) |
| 本轮决策观测 | `../references/trace.md`（入口统一写；`conductor-eval` 仍只计件数） |

不要写进产品仓，不要当成平台规约。不准为每个 mode 再开顶层 Skill。

## 何时用

| 场景 | mode |
|------|------|
| 对着 diff 验证刚写的逻辑 | `logic` |
| 开发自测：正确性 + 影响面兼容 | `selftest` |
| 查问题：现象 → 用例 → 复现 → 根因红绿 | `debug` |
| 测试验收（全维度；缺基线必须 `UNPROVEN`） | `test` |
| 重放已登记回归包 | `patrol` |

不要用本模块去实现测试框架、浏览器引擎、或独立 CLI。  
登录态走当前产品 `.idev/handoff.yaml` 里的取 Cookie Skill，本模块只跑带 Cookie 的 `frontend-http`。

## Hard rules

1. **先 plan，`accepted: true` 后才 run。** P0 要人改 YAML 或本轮确认用语全签；P1/P2 `verify-plan` 0 FAIL 且无 `SIGNAL` 时写 `accepted: true` + `auto: <检查输出>`。协议 [chat-confirm-signoff.md](../references/chat-confirm-signoff.md)。`继续` / 口头含糊不算。未勾选不跑，标 `UNPROVEN`。
2. **人必须给 `feature` slug**（分支名可当默认，须点头）。无密封基线时还要 `goal` + `non_goal`。**已有 `baseline.yaml` 且 `sealed`：** `plan.goal` / `non_goal` 复制基线原文，不准另编。`debug` 还要环境/产物 + 可观察物。
3. **`cases[]` 只许 `PASS`/`FAIL`/`UNPROVEN`。** 没跑、无基线、无原型对照 = `UNPROVEN`。禁止「达标」「全面通过」和分数。
4. **`human_signoff[]` 只许 `PENDING`/`ACCEPTED`/`REJECTED`。** 无本轮确认用语不得写成 `ACCEPTED`。
5. **影响面：diff + 调用关系扩一跳**（有 codegraph 就用）。只提名，人 `include`。runner 不算图。
6. **生成测试**只写当事模块 `src/test/java/**/generatedverify/`。**禁止 `git add` 该目录**（仓库未必已 gitignore）。绿了也不入库，除非人 `promote` 勾选。
7. **`patrol` 无 `doc_home.py --key patrol` 指向的巡检包就拒跑**，不准现编巡检。
8. **禁止** `.scratch/`、`docs/verify/`、整仓当入口、一条龙自动开火。
9. **扩展只改登记表**（[plan-schema.md](references/plan-schema.md)）。不复制本模块、不开新 Skill。不兼容修正升 `schema_version` + ADR。
10. **跑测用现有 Maven / 人确认的 shell**，不要第二套断言引擎。
11. **试运行反馈。** 入口直接落到本模块且台账 `trial`：每次 `run` 后写 `feedback.yaml` 并停问导体 tag。**由 deliver / ops 模块调用时**：只写 `conductor-eval`，不为进化再停一次。进化只改真源 `~/.cursor/skills/idev/verify/`，不要写回仓库。禁止分数门禁。导体评审禁止数字总分。
12. **若存在 `<票目录>/deliver.yaml`：** case 必须带 `slice_id` 与 `baseline_item_id`。goal/non_goal 复制基线。**起草或调整 `cases[]` 后、请人 `accepted` 前**跑  
    `bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> verify-plan`  
    FAIL 不准请人 `accepted`。**`run` 不跑这一项、不请签、FAIL 不挡跑。** 禁止为了让测试绿去改 `baseline.yaml`。

## 动作

起草 plan 前先跑 `python3 ~/.cursor/skills/idev/scripts/session-context.py --repo <仓根> --feature <feature> --scenario S3 --stage verify-plan [--product <点名的产品>]`，打开每一行 `OPEN`。路径写入 trace 的 `extensions`（没有页就写 `extensions: []`）和 `opened`。

### 1. plan

1. 要齐：mode、feature；goal/non_goal 按规则 2（复制基线或人写）；`debug` 要环境/产物/可观察物。
2. 列 `impact_candidates`（hop 0 = diff 文件，hop 1 = 扩一跳）。
3. 按 mode 的维度表起草 `cases[]`（能挂上已有 `*Test`/`*IT` 就挂；没有则写人确认后的 `shell`，或生成到 `generatedverify/` 且 `accepted: false` 直到人勾）。
4. 写下 `<票目录>/verify/plan.yaml`（照 [plan.example.yaml](references/plan.example.yaml)）。`accepted: false`。`arch.yaml` 里还有两条以上没有 case 的 `case_intent` 时，先跑 `fanout.py assess --activity plan`。`FANOUT` 时每个分片只写 `verify/shards/plan-<id>.yaml`，不写 `plan.yaml`，不改 `accepted`。导体 `fanout.py merge` 再把草稿收进计划。`SERIAL` 就一个人起草。
5. 起草后或之后改了 `cases[]` / goal：跑 `check-feature.sh <feature> verify-plan`。FAIL 不准请人 `accepted`。
6. **P0，或 P1/P2 有 `SIGNAL`：停，等人改 plan**（勾选 / 删 case / `accepted: true`），或回复确认用语全签（见 [chat-confirm-signoff.md](../references/chat-confirm-signoff.md)）。P1/P2 无 `SIGNAL`：把检查输出存成 `verify/plan-check.log`，写 `accepted: true` + `auto: verify/plan-check.log`，不停。已 `accepted` 且本轮未改用例，不要再走本步。

### 2. run

1. 读 plan：`accepted != true` 则拒跑。**不跑 `check-feature verify-plan`，不把该项 FAIL 当运行门禁，不请人再签。**
2. 只跑 `cases[].accepted == true` 且 runner 可执行的项。日志：`{module}/target/verify/<case-id>/`。开跑前按 mode 跑 `fanout.py assess --activity selftest` 或 `--activity run`。`SERIAL` 就一个 verifier 跑完。`FANOUT` 时每个分片只写自己的 `verify/shards/<activity>-<id>.yaml` 和 `verify/evidence/<case-id>/`，不写 `plan.yaml`。同一 Maven 模块默认不拆；`runner.parallel: true` 才拆，导体先跑 `PREP`。分片如果撞上 `target/` 锁，把这条记成 `FAIL` 并留下日志，由导体单独重跑这一片，不要自己再拉起别的 agent。导体 `merge` 只回写 `status` 和 `evidence`。
3. 回写每条 `status` + `evidence`。追加 `revisions[]`。
4. 写同目录 `report.md`：索引过了什么、`UNPROVEN` 什么、`human_signoff` 仍 `PENDING` 什么。不准把人签项写成 PASS。不重写用例正文。体例见 [docs/SKILL.md](../docs/SKILL.md)。
5. 写 `## conductor-eval` 计数（见 [evolve.md](references/evolve.md)）。诚实性检查失败必须写明，不得用「全面通过」盖住。
6. 若台账 `phase: trial`：写下 `feedback.yaml`（`status: pending`，照 [feedback.example.yaml](references/feedback.example.yaml)），**停问**人要哪些 tag + 一句话。收到后写入，并拷到与 `product_sink.py inbox` 相同的目录（产品工程 `.idev/inbox/`；没有当前产品才是内核 `verify/state/inbox/`）。

`mode=test`：维度表每一维至少一条 case 或显式 `UNPROVEN`（写清缺基线/缺原型）。

`mode=debug`：原现象至少红过一次；根因须能红/绿切换。对不上环境/产物则停，不写结论。修复循环的终止红线（失败签名连续 3 次 / 无有效变化）见 [conventions/evidence.md](../conventions/evidence.md) 第 5 步；命中强制升级人工，不叠补丁。

### 3. promote

```bash
bash ~/.cursor/skills/idev/verify/scripts/promote.sh <feature>
```

把**该次已确认且已 run** 的 plan 快照写成 `doc_home.py --key patrol` 指向的文件。  
生成测试晋升为正式 `*Test`/`*IT` 必须人点名 case id；脚本默认不搬 Java。

### 4. clean

```bash
bash ~/.cursor/skills/idev/verify/scripts/clean.sh
```

删除各模块 `generatedverify/`。不删 `<票目录>/verify/`。

### 5. propose / grill / land（只改导体自身）

人说要改进导体，或 inbox 里同一 tag ≥ 2 条：
也可跑 `bash ~/.cursor/skills/idev/scripts/evolve-review.sh` 或 S8 `self-evolve-review` 先出草稿（仍须 grill+确认才 land）。映射：[../references/self-evolution.md](../references/self-evolution.md)。

1. 草稿写在当前会话的 proposals：产品工程 `.idev/proposals/<NN>-<slug>.md`；没有当前产品才是 `~/.cursor/skills/idev/verify/state/proposals/<NN>-<slug>.md`。人确认剥离之后才改内核真源。
2. **停，按 `~/.cursor/skills/grilling/SKILL.md` 只拷问该提案**。未听到「确认」不准改本机 SKILL.md / schema。
3. 确认后只改真源 `~/.cursor/skills/idev/verify/`，提案标 `landed`，台账 `conductor_revision + 1`。不要把导体改动 PR 进产品仓。
4. `phase: ga` 只能由人在另一次拷问确认后改 ledger。

细则：[evolve.md](references/evolve.md)。

## 不要做

- 用 lint 绿代替正确性
- 无基线仍写性能/并发/UI 达标
- 把上次碰巧的绿自动当巡检包
- 为每个 mode 再写一个 Skill
- 根据一次反馈直接改本 Skill
- 给导体打总分或用 LLM judge 当落地门禁
