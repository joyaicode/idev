# idev 细则（SKILL.md 共享硬规则的展开版）

> **权威关系：** 共享硬规则的一句话版在 `SKILL.md`，本页是其展开；二者冲突时以 `SKILL.md` 为准并把冲突记入 trace。红绿只走 verify，不准第二套测试框架或分数门禁。历史修订说明见 [changelog.md](changelog.md)。
> 先读 [agent-brief.md](agent-brief.md) 与 [glossary.md](glossary.md)。

## 先读（降认知负荷）

**冷启动只读两页：** [agent-brief.md](agent-brief.md) + `SKILL.md` 决策树。其余按场景懒加载（模块 SKILL 顶部「本阶段 5 步」→ 需要时再开 how-to / gates）。

1. **命令速查（指针目录）** [operator-cheatsheet.md](operator-cheatsheet.md) — 路由仍以 `SKILL.md` 为准；认票/H1–H6 在 [invoke.md](invoke.md)。
2. **真源** `~/.cursor/skills/idev/`（实目录）；aliases 必须是 symlink。companion：grilling + setup-agents-docs。
3. 周审计 / 自进化 / 自检：`audit-traces.sh` · `evolve-review.sh` · `healthcheck.sh`（含 late-lifecycle / second-product smoke）。Linux 调度：[linux-schedulers.md](linux-schedulers.md)。可移植：[portability-checklist.md](portability-checklist.md)。

**唯一顶层 Skill**；conventions / docs / deliver / verify / ops 是内部模块。[docs/SKILL.md](../docs/SKILL.md) 管产线文档落点，写文档时与当前执行模块一起打开。闭环真源 [conventions/evidence.md](../conventions/evidence.md)。idev 不绑产品仓，产品依赖 idev。使用中的中间文件在产品仓 `.idev/`，不进内核。禁止 `.scratch/`。分工：[conventions/scope.md](../conventions/scope.md)。

```
诉求 → 评审密封 → 拆解 → 架构 → 编码/自测 → 提测 → 投产
                                              ⇄ 排障/巡检
```

## 先认场景，再对类，再路由

1. **认场景**（S1–S8，见 `SKILL.md` 决策树）。混合意图：交付做到哪一格用 deliver；其中红绿 **调用** verify。投产现象先 ops。说不清先看 `scripts/lib/doc_home.py --key deliver` 指向的 `stage`。
2. **对类**：S1 / S4 / S6 先读 [conventions/SKILL.md](../conventions/SKILL.md) 再开该类一页。S2 / S3 / S5 能定类则**只开该类一页**；定不了再读 `conventions/SKILL.md` 一次。违反该类硬规则 = 拒过。
3. 只打开 **一个** 执行模块。不要把 deliver / verify / ops 一起加载。场景不要再打开第二张场景表。认票与 H1–H6 用到时打开 [invoke.md](invoke.md)。不要每轮打开 lifecycle / trace.md / cohesion。

下表只定必开 / 禁开。何时走哪一场景以 `SKILL.md` 决策树为准。

| 码 | 模块 | 必开 | 禁开 |
|----|------|------|------|
| S1 | **deliver** `req-review` | `conventions/SKILL` → 能定类则该类页；[deliver/SKILL.md](../deliver/SKILL.md)；**必须自动打开** [docs/SKILL.md](../docs/SKILL.md) 与 `~/.cursor/skills/grilling/SKILL.md`（缺则先 `scripts/link-companion-skills.sh`）；未 grill 完不准请签 `sealed` | verify / ops / lifecycle / ADR |
| S2 | 当前阶段模块 | 该类一页；当前模块 SKILL；`deliver.yaml`；签字时 chat-confirm；**若有未清异议/open_questions/边界含糊 → 先自动 grilling，再请签** | conventions 长文；另一模块；how-to / experts / gates（本轮请签除外） |
| S3 | **verify** | [verify/SKILL.md](../verify/SKILL.md) + `plan.yaml` | deliver 阶段机、grilling、conventions 长文 |
| S4 | **conventions** | [conventions/evidence.md](../conventions/evidence.md)；改代码再开该类页 | deliver / verify（除非人要进阶段机）；S8 `code-review` |
| S5 | **产线文档** | [docs/SKILL.md](../docs/SKILL.md) | deliver / verify / ops、conventions 长文 |
| S6 | **ops** | [ops/SKILL.md](../ops/SKILL.md) | deliver 编码阶段 |
| S7 | 交出口 | 当前产品 `.idev/marker.yaml` 为 `marker: idev` 时，读 `.idev/handoff.yaml` 里的 Skill | idev 三模块正文 |
| S8 | **workflow** 逐步执行 | 当前 step 对应模块一页；[references/workflow-schema.md](workflow-schema.md)；产品流水线在 `<repo>/.idev/workflows/`，能力配方在 idev `workflows/` | 一次打开多模块；跳过签字 kind；未点名恰好一个产品仍开跑 UI/启停 |

产线别名写在该仓 `.idev/workflows/<id>.yaml`，不写进本页。签字仍人确认。

前端验证要登录态：走当前产品 `.idev/handoff.yaml` 里的取 Cookie Skill，取到后仍回 verify。

**认票与 H1–H6**全文见 [invoke.md](invoke.md)。无停问点不请签、不擅自 promote、不为观测再停。`done` 后改 goal 须人说「解除密封」或 `reopen`。

全图：[references/lifecycle.md](lifecycle.md) · 停问：[references/invoke.md](invoke.md) · 签字：[references/chat-confirm-signoff.md](chat-confirm-signoff.md) · 内聚：[references/cohesion.md](cohesion.md) · 观测：[references/trace.md](trace.md) · 公共规约：[conventions/SKILL.md](../conventions/SKILL.md)

## 共享硬规则（全文）

1. **先守公共规约。** 按场景对类后执行（S2/S3/S5 不强制先读 conventions 长文）。通用闭环打架改 [conventions/evidence.md](../conventions/evidence.md)。产品专有摘要留在该仓。**从产品沉淀到 idev 核心之前，先剔除该产品专有逻辑**；剥不干净只留在该产品仓。
2. **分析 / 论证 / 推测须辅助证据。** 见 [conventions/evidence.md](../conventions/evidence.md)：AI 反馈与文档**不可信**；代码逻辑可信，仍须用例证明。每一步先设计用例证明，再推下一步，直到根因。
2a. **边界未订死必须自动唤起 grilling**（`~/.cursor/skills/grilling/SKILL.md`；S1 未清异议、`open_questions`/边界含糊、请签前有分叉、架构真有分叉、`code` 疑基线错）。不准自拷问顶替。需求把本轮问题一次问完；frontier 空之前禁止写 sealed。答问不是另一次确认。触发细则：[cheatsheet §7.2](operator-cheatsheet.md)。
3. 尺是密封基线。签字按 [references/chat-confirm-signoff.md](chat-confirm-signoff.md)：无本轮确认用语不得写 `sealed` / `accepted` / `aligned` / `resolved` / `reopen_baseline` / `semantic_gate.*.passed`；有确认用语则只代写**当前停问点**（含对应 `semantic_gate`）并立刻下一步。`继续` 不算。不准用确认改 goal。
4. 红绿只走 verify。不准第二套测试框架或分数门禁。
5. 签字前：`bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> <stage>`。`verify-plan` 只在起草或调整用例、请人 `accepted` 时跑；已 accepted 的 plan 再 `run` 不重跑、不请签。
6. 巡检包：`bash ~/.cursor/skills/idev/verify/scripts/promote.sh <feature>`。人没提提升 / 巡检包 / promote 则不问、不跑。
7. 改本 Skill：提案 + 拷问后只改真源 `~/.cursor/skills/idev/`（勿改 `~/.agents` / `~/.joycode` 副本；二者应为 symlink）。平台改了通用禁令 → 回填 `conventions/`。不要把本 Skill 登记成平台规约类。
8. **每轮路由后输出决策（schema v2）。** 落盘完整 v2；对话短表：S2/S3/S5 只打 trigger / route / stop / next，其余全表。写 `route.scenario: S1`…`S8`（**必写**；缺省当 S1）。`bash ~/.cursor/skills/idev/scripts/trace.sh append` 在产品仓落到 `<repo>/.idev/traces/`，不进 idev 内核。导体自身会话才落到内核 `state/traces/`。必写 `invoke.trigger` / `invoke.matched`、`thinking.summary`，以及本轮真实 `calls[]` / `opened[]`。不为观测另停、不准伪造调用。技能怎么调起、委派给谁、模型与一行思考、组件从哪跳到哪，有就写进 `invoke.how` / `invoke.skills[]`、`decisions` 的 `delegate` / `model`、`calls` 的 `from` / `to` / `model` / `thinking`；缺了不挡本轮。契约：[references/trace.md](trace.md) · 场景 / 认票 / 停问：[references/invoke.md](invoke.md)。写完后在对话展示一行**运行路径**（trigger → 场景/模块 → skills / choices / hops → next）；可用 `scripts/path-view.sh`（`path-view.sh stats` 热路径，含技能入口、委派、模型与组件跳的次数）。运行中打开中控台：`python3 ~/.cursor/skills/idev/scripts/console.py`。路由前 `console.py pending` 有未读则当作本轮人话，处理完 `reply --text`；派 agent 前 `live --add`，`record` 后 `live --clear`。控制台不写签字。不为观测另停（H5）。

## 产品工程 `.idev`（非核心）

进入阶段先跑 `scripts/session-context.py`（它列出本轮要打开的 `OPEN` 行）。点了产品名就加 `--product`。路径写入 trace 的 `extensions`（没有页就写 `extensions: []`）和 `opened`。清单在扩展根的 `.idev/extensions.yaml`；本仓 marker 可以用相对路径 `extension_root` 指向那份清单。还没有标记，就只走内核。边界在 [scope.md](../conventions/scope.md)。
