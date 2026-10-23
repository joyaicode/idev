# 怎么唤起

只有 **`idev`** 是顶层 Skill。先认场景，再对类，再开一个执行模块。  
产品旧名不写在本页。旧触发词记在当前产品仓 `.idev/pack/README.md`。

## 场景

何时走 S1–S8 只看 `SKILL.md` 决策树，以及决策树后的「配方命中」。本页不列第二张场景表。

最常用三行（摘要；与决策树冲突时以 `SKILL.md` 为准）：

| 输入 | 走 |
|------|-----|
| 小改 / 轻量 / 不改 goal 的已有票 | S8 `lite-change`（必须绑票） |
| 原话命中配方别名 | S8，最长别名优先于只含 stage 动词的 S2/S3 |
| 综合评审 skill / 导体 | S4；产品仓代码审查走 S8 `code-review`（不审导体） |

产线自己的「自进化 / 建设剧本」类配方按产品仓配方别名走 S8，不要当成 `self-evolve-review`。

**自检：** `bash ~/.cursor/skills/idev/scripts/healthcheck.sh`。

**周审计（滚动 50，不回填历史）：** 原话含「周审计 / 审计 traces / weekly audit」→ S8 `workflows/weekly-trace-audit.yaml`。

**运行路径：** 原话含「运行路径 / 路径视图 / path view / 观测路径」→ S8 `workflows/path-view.yaml`。写完 trace 后对话回显一行路径（见 [operator-cheatsheet.md](operator-cheatsheet.md) §5）。

**自进化复盘：** 原话含「自进化 / 进化复盘 / evolve review / hermes 复盘」→ S8 `workflows/self-evolve-review.yaml`（只写提案草稿，不改 Skill）。详见 [self-evolution.md](self-evolution.md)。

**小改捷径：** 原话含「轻量改动 / 小改 / 小修 / lite change」→ 优先 S8 `workflows/lite-change.yaml`（见 [operator-cheatsheet.md](operator-cheatsheet.md) §3、[lite-change-pitfalls.md](lite-change-pitfalls.md)）。不改 goal/baseline；禁止跳签与自动 promote。


混合意图：交付做到哪一格用 deliver；红绿只**调用** verify。说不清先看 `<票目录>/deliver.yaml` 的 `stage`。

## 认票

1. 人原话点了 slug → 用它
2. 否则 `python3 ~/.cursor/skills/idev/scripts/session-context.py --list-open --repo <仓根>`，用打出的 `OPEN_TICKET`（`stage` 不是 `done`）
3. 多于一张 → 问一句
4. 再没有 → 最近一条 trace 的 `feature`
5. 仍没有 → `feature: -`；新诉求走 S1，不要猜已 `done` 的票

## 打开预算

入口 `SKILL.md` 的决策树是打开清单真源。S1 / S4 / S6 先读 `conventions/SKILL.md`；S2 / S3 / S5 能定类则只开该类一页。必开 / 禁开见 [skill-details.md](skill-details.md)。认票与 H1–H6 用本页；不要为了路由再打开 lifecycle / trace.md / cohesion。

S8：只打开**当前 step** 对应模块一页 + `references/workflow-schema.md`（首次本轮）+ 本轮 `workflows/<id>.yaml` 与 `<票目录>/workflow/run.yaml`。禁止一次加载 deliver+verify+ops。命中与产品名规则见 `SKILL.md`「配方命中」。

## 自动唤起 grilling（订死边界）

grilling 不是可选追问，而是**订死边界与不清楚处**的默认动作。Agent 在下列触发出现的**同一轮**必须打开 `~/.cursor/skills/grilling/SKILL.md` 并跑 frontier：

1. S1 / `req-review` 需求分析（正确性、合理性、边界、非目标）。本轮能问的一次问完，编号并给出推荐答案；回答打开新问题就再来一轮。不要一问一签。
2. 任意阶段：`open_questions`、`objections`、baseline-conflict、目标/范围含糊
3. `arch` 已经交出方案之后，仍有未决分叉。没有分叉就不要为了过门造一轮问句
4. 人原话表达不确定、要定界、要拷问细节

**frontier 未空之前：** 不要请签需求通过，不要代写 `sealed` / `accepted`。共享理解由需求通过那一次确认写入，不单独再请一次。

## 自动打开产线文档技能

写需求、规格、测试设计、票目录，或做 S5 回填时，同一轮打开 `~/.cursor/skills/idev/docs/SKILL.md`。它再打开 setup-agents-docs（目录）和 grilling（问句）。缺同伴技能先跑 `scripts/link-companion-skills.sh`。不要另写一套目录。

## 门禁停问（`risk_tier`，默认 P1）

每个档位停哪里（A 类签字）、什么信号才停（B 类决策）、何时 `AUTO`：只在 [chat-confirm-signoff.md](chat-confirm-signoff.md)「档位 ↔ 停问点」。为什么这样放：[hitl-risk-tiers.md](hitl-risk-tiers.md)。

## 非门禁不停（H1–H6；旧称 C1–C6，已改名以免与编码气味 C1–C15 撞号）

| 码 | 做法 |
|----|------|
| H1 | 无当前停问点：不请签，不说「请确认」 |
| H2 | 人没提提升 / 巡检包 / promote → 不问 `promote.sh` |
| H3 | 导体 feedback tag：仅入口**直接**落到 verify 且 trial；deliver / ops 调用 verify 不问 |
| H4 | 已 accepted 的 plan 再 `run`：不重跑 `verify-plan`、不请再签 |
| H5 | 写 trace 不为观测再停 |
| H6 | 自测跑完后停在实现审核，不另问「要不要提测」。审核确认后才把 `plan.mode` 改成 `test` |

停问请签时必须回显一行 `将代写: <字段>`（见 [chat-confirm-signoff.md](chat-confirm-signoff.md)）。

`done` 后不改 goal → S4；要改 goal 必须人说「解除密封」或 `reopen`。

## 唤起后立刻做的思考（写入 trace）

进入本 Skill 后、动手改仓前，按顺序想清楚并记进 v2 trace：

1. **scenario**：命中 S1–S8 哪一条？写入 `route.scenario`
2. **trigger**：用户原话里哪几个词把你拉进来？是否旧名别名？
3. **matched**：对照场景表，命中哪一行？
4. **signals**：认到的 slug、`deliver.yaml.stage`、plan 是否 accepted？
5. **excluded**：为什么不走其它场景 / 模块 / 交出口？
6. **module + convention_class**：按打开预算实际打开哪一页？
7. **calls / opened**：本轮实际打开或执行了什么？

这些不是给用户看长文。S2 / S3 / S5 对话短表只打 trigger / route / stop / next；落盘仍全量。

## 签字前

```bash
bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> <stage>
```

`stage`：`req-review` \| `req` \| `arch` \| `code` \| `test` \| `verify-plan` \| `ops`。非 0 退出不准签字（含对话确认代写）。  
`verify-plan` **只在起草或调整用例、请人 `accepted`（或 P1/P2 记 `AUTO`）时**跑。已 accepted 的 plan 再 `run` 不重跑、不请签。

签字与决策怎么记：[chat-confirm-signoff.md](chat-confirm-signoff.md)。

## 快捷工作流（S8）

配方：有 `.idev/marker.yaml` 且 `marker: idev` 时，产品流水线在当前仓 `.idev/workflows/*.yaml`；编排能力在 `~/.cursor/skills/idev/workflows/*.yaml`。契约：[workflow-schema.md](workflow-schema.md)。同 id 用产品仓那份。
校验：

```bash
bash ~/.cursor/skills/idev/scripts/workflow-check.sh
```

执行由 `scripts/workflow.py` 驱动：`start` 写 `run.yaml`，`next` 给出当前步骤与要打开的页，做完用 `record` 记结果（签字步骤要人名与确认原话）。不要手写 `run.yaml`；修正只追加 `revisions[]`。用法见 [workflow-schema.md](workflow-schema.md)「编排工具」。试运行 feedback 复用 verify inbox（文件名前缀 `wf-`）。禁止跳过签字 / 自动 seal。
产线配方（UI、启停、多角色等）在产品仓 `.idev/workflows/`，执行说明是配方的 `doc`：`session-context.py --workflow <id>` 列出的 `OPEN` 行就是要读的页。配方要求 `product` 时原话必须点明恰好一个产品名。`自进化` 单独仍是 `self-evolve-review`。
整仓提交推送：`repo-commit-push`（见 [workflow-repo-commit.md](workflow-repo-commit.md)）；含 replace / lint-fix / Java 构建 / 敏感配置屏蔽还原。
整仓代码审查：`code-review`（见 [workflow-code-review.md](workflow-code-review.md)）；先报告再签收，再 selftest 验收。

## 每轮观测

每轮路由后输出决策（对话短表 + 本机 traces），不为观测另停：

```bash
bash ~/.cursor/skills/idev/scripts/trace.sh append < trace.yaml
bash ~/.cursor/skills/idev/scripts/trace.sh last
```

新痕迹必须 `schema_version: 2`（含 `invoke` / `thinking`）。**必写** `route.scenario`（缺省当 S1）。技能调起、委派、模型与组件跳是可选观察字段，缺了不挡本轮。契约：[trace.md](trace.md)。

改检查脚本后：

```bash
bash ~/.cursor/skills/idev/scripts/selfcheck.sh
```

## 路由

路由以 `SKILL.md` 决策树为准。本页开头三行只是摘要。一次只开一个执行模块。拿不准先看 `<票目录>/deliver.yaml` 的 `stage`。
