---
name: idev
description: >-
  人机共驾的端到端交付生命周期导体（评审密封、拆解、架构、编码自测、提测、巡检、投产后排障）与共享规约；
  内核 S8 配方：lite-change、dev-selftest、dev-logic、test-pack、deliver-next、debug-repro、patrol-replay、code-review、docs-feature、docs-contract、repo-commit-push、path-view、weekly-trace-audit、self-evolve-review。
  产线自己的流水线在当前产品仓 .idev/workflows/。产线可在那里定义 UI、启停、多角色等快捷配方，别名写在该配方里；这类指令必须点明恰好一个产品名。适用所有端到端交付产品。产线特性在 .idev/，不在导体里。
  触发词：端到端交付、需求评审、密封基线、拆解、架构方案、提测、verify plan、自测、巡检包、promote、投产后排障、排查闭环、分析论证、导体评审、代码审查、快捷工作流、idev。
  不用：产品专属脚手架/接入排障/集群事故正文（交出口）、仓内 CI/MR 门禁、把「综合评审 skill/导体」当成 code-review。
---

# idev（端到端交付生命周期，唯一入口）

**产品目标：** 人机共驾的 AI 端到端交付。交付阶段检查过了、没有未决分叉，就写下这一关并继续。解封、回退、发布仍要点名。**不是**无人值守自动 seal→promote。使用说明：[references/guide.md](references/guide.md)。

**Agent 先读：** [references/agent-brief.md](references/agent-brief.md)（最小执行回路 / 何时必须停问人 / 冲突时听谁 / 编号只认一处）· [references/glossary.md](references/glossary.md)（术语表，不认识的词先查，别猜）。本页决策树是**路由的唯一权威**，其它页的路由表只是摘要。

## 你是谁：skill 与 agent 分工

**你是被 `/idev` 加载的 skill，你是导体。** `agents/` 下的五个执行者是 subagent，它们不是你。

| | 你（skill / 导体） | 它们（agent / 执行者） |
|---|---|---|
| 做 | 认票 · 认场景 · 路由 · 组委派包 · 验收回报 · 记账 | 在落点页里干活 · 产出工件 · 给证据路径 |
| 独占 | **签字权** · 与人交互（请签 / 停问 / 唤起 grilling） · 写 trace | 独立上下文（互不污染） |
| 不能 | 亲自执行已委派的 step | 签字 · 问人 · 写 trace |

**为什么导体这件事不能也委派出去：** subagent 看不到本轮检查和未决分叉，写不了这一关。
`scripts/lib/workflow_spec.py` 的 `is_human()` 按词表 `AGENT_WORDS` 拒绝 agent / 模型 / 角色名
（整名与分词都匹配），存在 `config/people.yaml` 时还须在白名单里——**agent 名字落在 `by` 上在代码层就被拒**。
检查过了由你写下这一关，不问人确认。

五个执行者：`idev-deliver`（需求/架构/文档）· `idev-coder`（编码/构建/提交）·
`idev-reviewer`（审查）· `idev-verifier`（红绿/环境）· `idev-ops`（排障/论证）。
每个执行者都能沿交付链读上游的尺和下游的后果；本领域以拒过清单为下限；指导别的角色只经导体转达。
完整职责分离、四条硬依据、角色能力，以及两者之间仅有的三样接口：[references/agents.md](references/agents.md)。
**怎么用**（何时走 `/idev`、何时直接点 agent、委派包最常漏什么、出问题按什么顺序查）：
[references/agents-playbook.md](references/agents-playbook.md)。

S8 每步按 `workflow.py next` 打印的 `DELEGATE` 行派活；`DELEGATE none` 表示这一步你自己做
（`human.gate` 永远是 none）。`next` 打出 `PARALLEL` 时，先跑 `workflow.py delegate --open`，再把这一波里的每个 `DELEGATE` 派出去，每个回报只 `record` 自己的 step。`verify.plan` / `verify.run`，以及写集不是单独一份 `review.md` 的 `review.report`，还会打出 `FANOUT_ASSESS`：先跑那条 `fanout.py assess`。`SERIAL` 仍一步一个 agent。`FANOUT` 时同一条消息派每个 `SHARD`，并对每片 `workflow.py delegate <step> --shard <id>`（验证租约只覆盖该片路径），各片只写自己的 `WRITES`。assess 若打出 `MERGE` 且没有 `SHARD`，分片草稿已经齐了，跑那条 merge，不要再派执行者去写总账。导体 `fanout.py merge` 后再把这一步 `record` 一次。根因定位看假设台账，用 `--activity rootcause`，不挂在定界用的 `route.s4` 上。委派后按 [references/agents-evolve.md](references/agents-evolve.md)
落一份留痕，它是这一层可调试的全部前提。

## 提效三板斧

把规约里**已经要求、但以前只能靠自觉**的事变成可执行、可机检、可计数。不新增门禁，不打分。

| 阶段 | 执行者 | 做什么 |
|---|---|---|
| 编码 | `idev-coder` | `coding.md` 文首底线 + §0 三项交代（`CHANGE_KIND`/`CANON_TRIGGER`/`TABLE_HIT`）+ codegraph 影响面 + 增量自测 |
| 测试 | `idev-verifier` | 维度表先铺满用例骨架 + 失败签名归一化（`scripts/failure_signature.py`） |
| 根因 | `idev-ops` | 假设台账（`scripts/hypothesis.py`）+ 证据链 + 有界修复红线自动计数 |

要算数就写代码，不要口算：`scripts/repl.py` 把计算的源码与输出落成票目录里的证据
（[references/code-agent.md](references/code-agent.md)）——散文推理不是证据，
算出来的结果加上能重跑的脚本才是。

`verify/SKILL.md` 硬规则 5 原文就是「有 codegraph 就用」，`conventions/evidence.md` 第 5 步
原文就定了三条有界修复红线 —— 这三板斧只是让它们**判得出来**。细则
[references/boost.md](references/boost.md)；待办与验证状态
[references/agents-todo.md](references/agents-todo.md)。

## 回合预算

聊天回合先让人看见一句，再去做会堵住的事。一条助手消息是一个回合，里面有几次只读都算一个。

1. `block_until_ms` 大于 30000 的命令发出之前，先写一句：命令、预算、在等什么。`scripts/selfcheck.sh`、`test/golden/record.sh`、`test/gate-channel.sh`、`test/lease-channel.sh` 同样先写这一句，再放后台，结束再报。
2. 连续 8 个只有工具、没有正文的回合之后，先写一句现状再继续。
3. 不用 `claude -p` 或 `agent -p` 做存活探测。存活是一次不调用工具的一行回复。`scripts/healthcheck.sh` 和 `scripts/agent-smoke.sh` 是全量检查，与下面四条套件一样先说一句再放后台。
4. 结构问题先跑 `scripts/codegraph-sync.sh`，再一次 `codegraph_context`。查不到就停并写明查不到。时刻和 `reason` 只认 [boost.md](references/boost.md)「索引何时更新」。代码有没有变动由脚本判定，没变就跳过。

`scripts/turn-budget.py` 对一份转录判这些事，无正文回合默认超过 8 即失败：第一句之前的无正文回合、连续无正文回合、`block_until_ms` 大于 30000 且这一条和上一条助手消息都没有正文、命令里出现 `claude -p` 或 `agent -p`。`selfcheck.sh`、`test/golden/record.sh`、`test/gate-channel.sh`、`test/lease-channel.sh`、`healthcheck.sh`、`agent-smoke.sh` 的 `block_until_ms` 大于 30000 也失败，先说一句不算放过。有没有把多次只读并进一条消息，不是通过或失败的条件。结构问题先更新索引再 `codegraph_context`、查不到就停，这是做法，不进这个脚本。

```bash
python3 scripts/turn-budget.py [--max 8] <transcript.jsonl>
```

## 分阶段的能力(按需查阅，细节在落点页)

决策树定路由；下面这些是**每一格该用什么**。每行的全文在它的落点页，
入口只留一句话和命令 —— 需要时再展开，不必通读。

| 阶段 | 做什么 | 入口命令 | 全文 |
|---|---|---|---|
| `req-review` | 需求落到既有代码：落点 / 影响面 / 与存量冲突 / 边界 / 演进方向 + 竞品对比 | `req-ground.py --feature <f> --probe` | [附录](#需求要落到这个工程上密封前) |
| `req-review` | 界面需求细到交互层，派生 json-render spec + 零依赖预览 | `ui-spec.py --feature <f>` | [附录](#需求细到交互层界面类需求) |
| `arch` | 影响范围内先审既有问题。判据唯一就写入 `scope_debt.decision`。定不了才并进当前编制的一次决策包 | — | [deliver/SKILL.md](deliver/SKILL.md) |
| 触及 Vue | UI 设计、编码、自测、测试、UI 自动化、根因：先打开语言尺，再按它点名的技能做 | `vue-skills.py --repo <仓> --stage <阶段>` | [vue.md](conventions/vue.md) |
| 每一格 | 七视角专业拒过清单里可机检的那一半（`--list` 看各档查什么） | `stage-gate.py --feature <f> --all` | [experts.md](deliver/references/experts.md) |
| `code` | 准确率护栏：SCOPE / READ / REVERT / RED_FIRST / ASSUMED | 回报字段，`delegation.py` 机检 | [agent-accuracy.md](references/agent-accuracy.md) |
| `code` / `test` / `ops` | 自测、用例设计与执行、根因、审查深读：先评估再决定要不要多分片 | `fanout.py assess --feature <f> --activity selftest\|plan\|run\|rootcause\|report` | [agents.md](references/agents.md) |
| `test` | UI 剧本生命周期 create→read→change→restore→cleanup | `ui-playbook.py --repo <仓>` | [附录](#ui-剧本覆盖整个生命周期测试阶段) |
| `test` | 写剧本时查状态冲突，提 branch / reorder | `ui-evolve.py --repo <仓>` | [附录](#ui-剧本覆盖整个生命周期测试阶段) |
| `ops` | 根因六条强约束 + 报告三问 | `hypothesis.py check --feature <f>` | [rootcause-guards.md](references/rootcause-guards.md) |
| `ops` | 产物与源码是否同源（读源码之前先问这个） | `artifact-match.py --artifact <jar>` | [boost.md](references/boost.md) |
| `ops` | 经验台账：六问必答，候选→人确认+复现→权威 | `lessons.py recall --scope <域>` | [rootcause-guards.md](references/rootcause-guards.md) |
| 需求订正后 | 全线重新对准，七类漂移 + 重做顺序 | `realign.py --feature <f>` | [feedback-loop.md](references/feedback-loop.md) |
| 交付后 | reopen 次数 / 签字后被推翻次数 → 改**关口**而非单张票 | `ticket-metrics.sh --repo <仓>` | [feedback-loop.md](references/feedback-loop.md) |
| 动态关节 | 声明了 `react` 的步骤，`next` 打出 `REACT_OPEN` 到 `REACT_SHOW`；用尽走 `on_exhaust`，失败走 `on_fail`；缺槽位先 `ASK`，用 `param` 写回；`next` 打 `DIGEST` 和 `LOOP`，都不挡步骤 | `react_loop.py` | [workflow-schema.md](references/workflow-schema.md) |
| 流水线 | 步骤可写 `tool` / `tool_group` / `use`，并用 `adjust` 跳过、排序、替换、追加。工具命令只打印 | `workflow.py` | [workflow-schema.md](references/workflow-schema.md) |
| 外部工具 | Langfuse 只导出 · promptfoo 只断言不打分 · **不装 DSPy** | — | [external-tools.md](references/external-tools.md) |

**一条贯穿所有阶段的规矩：** 这些工具的 PASS 都只说明「没撞上已知的硬错」，
**不说明做对了**。每个工具在 PASS 时都会把这句话打出来 —— 因为一个声称能判质量的门禁，
会让人停止自己看。

## 决策树（输入 → 场景 → 模块 → 第一步命令）

| 输入 | 场景 | 模块（只开一个） | 第一步 |
|------|------|------------------|--------|
| **小改** / 轻量 / 不改 goal 的已有票 | **S8** `lite-change` | 当前 step 一页 | **必须绑票**，先 `bash ~/.cursor/skills/idev/scripts/s8-preflight.sh <feature> lite-change`；无票先认票，不裸改 |
| 其它快捷别名（跑自测 / 提测包 / 逻辑验 / 回填契约…） | **S8** | 当前产品 `.idev/workflows/<id>.yaml`，没有再看 idev `workflows/` | `s8-preflight.sh <feature> <id> [--product <点名的产品>]`；UI/启停须点名恰好一个产品 |
| 新需求 / 无 `deliver.yaml` / 另开票 | **S1** | deliver `req-review` + 产线文档 + grilling | 先读 `conventions/SKILL.md` 定类；落盘前打开 `docs/SKILL.md`；缺同伴技能 → `scripts/link-companion-skills.sh` |
| 票已有 `stage`、往下推，或本轮确认当前停问点 | **S2** | 当前阶段模块 | `scripts/lib/doc_home.py --feature <feature> --key deliver`；签字前 `scripts/check-feature.sh <feature> <stage>` |
| plan / run / 红绿 / promote / clean | **S3** | verify | 读 `verify/SKILL.md` + `plan.yaml` |
| 分析论证 / 综合评审 skill·导体 / `done` 后不改 goal | **S4** | conventions | 读 `conventions/evidence.md`（不走 S8 `code-review`） |
| 契约 / 经验回填 | **S5** | 产线文档 | 打开 `docs/SKILL.md` |
| 线上 / 联调现象 | **S6** | ops | 读 `ops/SKILL.md` |
| 产品专属接入 / 脚手架 / 集群排障 | **S7** | 交出口 | `scripts/bootstrap-outbound.sh`，再开产品 handoff Skill |
| 说不清 | — | — | 先看 `deliver.yaml` 的 `stage`；仍不清则按编制把问题一次问全 |

小改不要无故从 S1 重开。签字只在固定的 A 类点，拿不准时按信号停问；哪些点、哪个档位可 `AUTO` 只看 [chat-confirm-signoff.md](references/chat-confirm-signoff.md)。边界不清先 grilling。每轮末 `scripts/trace.sh append`。

## 场景（S1–S8）一句话

S1 新票→deliver `req-review`（必开 `docs/SKILL.md` 与 grilling）· S2 推进当前 stage · S3 verify 红绿/promote · S4 分析论证→conventions/evidence · S5 契约/经验回填→`docs/SKILL.md` · S6 线上现象→ops · S7 产品专属→交出口 handoff · S8 命中 `workflows/<id>` 别名→`scripts/workflow.py` 按配方逐步驱动。
认场景 → 对类（S1/S4/S6 先读 [conventions/SKILL.md](conventions/SKILL.md)）→ **只开一个**执行模块，不要把 deliver / verify / ops 一起加载。各场景必开/禁开全表：[references/skill-details.md](references/skill-details.md)。
**配方命中：** 原话子串命中配方 id 或其别名 → S8。当前产品 `.idev/marker.yaml` 为 `marker: idev` 时，先看该仓 `.idev/workflows/`，再看 idev `workflows/`（编排能力）。同 id 用产品仓那份。多条取最长别名，优先于仅含 stage 动词的 S2/S3。配方要求 `product` 时，原话必须点明恰好一个产品名，否则不启动、不猜。构建出来的流水线写在产品仓 `.idev/workflows/`，不写进 idev。

认票五步与非门禁不停（H1–H6）全文只在 [invoke.md](references/invoke.md)。无停问点不请签、不擅自 promote、不为观测另停。`done` 后改 goal 须人说「解除密封」或 `reopen`。

## 共享硬规则（一句话版，全文见 [skill-details](references/skill-details.md)）

1. 先守公共规约（[conventions/SKILL.md](conventions/SKILL.md)）。产线做端到端交付时先走内核。idev 识别产线侧特性，需要保存时写入该工程 `.idev/`（含 `marker: idev`），后续会话再读。写产线文档前打开 [docs/SKILL.md](docs/SKILL.md)（目录认 setup-agents-docs，问句认 grilling）。进入阶段先跑 `scripts/session-context.py`，只打开它列出的 `OPEN` 行；点了产品名就加 `--product`。人说「提升到内核」并完成产品剥离后，才写进内核。详见 [conventions/scope.md](conventions/scope.md)。
2. **证据优先**：AI 反馈与文档不可信，代码逻辑可信仍须用例证明；每步先设计用例再推下一步。[conventions/evidence.md](conventions/evidence.md)
2a. **边界未订死必须自动唤起 grilling**（`~/.cursor/skills/grilling/SKILL.md`），不准自拷问顶替。能问的按当前编制一次列全，条件后续写在同一轮；只有回答打开没写过的新分叉才再开一轮。能按判据决定的不问。答问不是签字。frontier 空之前禁止写 sealed。架构先出完整方案，只有真有分叉才拷问。触发细则 [cheatsheet §7.2](references/operator-cheatsheet.md)，问谁见 [chat-confirm-signoff.md](references/chat-confirm-signoff.md)。
3. 尺是密封基线。交付主路径不再为确认停，也不解析原话。`check-feature` 过了、没有未决分叉，就写 `sealed`/`accepted`/`aligned`/`resolved`/`semantic_gate.*.passed` 并进入下一阶段。不问确认。检查没过不写。否决用 `record FAIL` 或 `idev gate reject`。不准用落笔改 goal。plan 在机检无信号时写 `auto:`。[references/chat-confirm-signoff.md](references/chat-confirm-signoff.md)
3a. **架构与设计质量**：`arch` 阶段和任何“加层 / 拆分 / 缓存 / 队列 / 重写”念头，先按 [conventions/canon.md](conventions/canon.md) §1 协议执行（T1–T12、A1–A8）；命中即停按动作做，落到 P/C/R；不新增强门禁。
4. 红绿只走 verify。不准第二套测试框架或分数门禁。
5. 签字前 `bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> <stage>`；已 accepted 的 plan 再 `run` 不重跑 verify-plan。
6. 巡检包 `verify/scripts/promote.sh <feature>`：人没提 promote / 巡检包则不问、不跑。
7. **改本 Skill 只改真源** `~/.cursor/skills/idev/`（`~/.claude`、`~/.agents`、`~/.joycode` 是 symlink，勿复制第二份）；提案 + 拷问后再改。
8. **每轮路由后写 trace（schema v2）**：`bash ~/.cursor/skills/idev/scripts/trace.sh append`。产品仓会话落 `<repo>/.idev/traces/`，不写进 idev 内核；只有导体自身会话才落内核 `state/traces/`。必写 `route.scenario`、`invoke.trigger`/`matched`、`thinking.summary`、真实 `calls[]`/`opened[]`，不准伪造调用，不为观测另停。技能怎么调起、委派给谁、模型与一行思考、组件从哪跳到哪，有就写进 `invoke.how` / `invoke.skills[]`、`decisions` 的 `delegate` / `model`、`calls` 的 `from` / `to` / `model` / `thinking`；缺了不挡本轮。对话给一行运行路径（`scripts/path-view.sh`）。运行中打开中控台：`python3 ~/.cursor/skills/idev/scripts/console.py`。路由前若 `python3 ~/.cursor/skills/idev/scripts/console.py pending` 有未读，当作本轮人话，处理完 `reply --text` 写回；派 agent 前 `live --add --feature --step --agent`，`record` 后 `live --clear`。停问和签字规则不变，控制台不写签字，不为观测另停。[references/trace.md](references/trace.md) · [references/invoke.md](references/invoke.md)

## 链接

先读 [使用说明](references/guide.md) · [operator-cheatsheet](references/operator-cheatsheet.md) · 细则 [skill-details](references/skill-details.md) · 新票 vs 小改 [s1-vs-s8](references/s1-vs-s8-playbook.md) · HITL [hitl-risk-tiers](references/hitl-risk-tiers.md) · 全图 [lifecycle](references/lifecycle.md) · 内聚 [cohesion](references/cohesion.md) · 自进化 [self-evolution](references/self-evolution.md) · 可移植 [portability-checklist](references/portability-checklist.md) · Linux 调度 [linux-schedulers](references/linux-schedulers.md) · aisel 对照 [aisel-mapping](references/aisel-mapping.md) · 自检 `scripts/syntax-check.sh` → `scripts/agents-check.py` → `scripts/agent-smoke.sh` → `scripts/healthcheck.sh`（含 late-lifecycle / second-product smoke）· 周审计 `scripts/audit-traces.sh 50`

---

# 附录：分阶段能力细则

## 根因分析:六条强约束

> 最危险的不是「没有答案」，而是**「给出一个听起来合理但无法验证的答案」**。

| 约束 | 挡什么 |
|---|---|
| 服务名必须有来源 | 凭记忆说出一个服务名，再围绕它推理一整轮 —— 而它可能不存在 |
| 时间窗必须可追溯 | 把范围放宽到「正好能解释现象」，无关证据就卷进来了 |
| 调用链必须穿透 | 把中间服务的报错当根因 —— 它常是在转述上游的失败 |
| 关键判断至少双证据 | 单一信号配一个说得通的故事 |
| 快照不等于根因 | 现象发生过 ≠ 解释了为什么 |
| 排除也要举证 | 排除了没写依据，下一轮重走同一条路 |

根因报告先回答三问：**根因是什么 / 影响是什么 / 建议怎么做**，再展开证据链。
经验沉淀走「候选 → 旁路复现 → 人工确认 → 入库」—— 错误结论一旦入库会被反复引用。

全文 [references/rootcause-guards.md](references/rootcause-guards.md)。

### 经验沉淀:候选 ≠ 权威

```bash
python3 scripts/lessons.py recall --scope <域> --symptom <现象>  # 排查前召回
python3 scripts/lessons.py add --feature <f> ...                 # 记成候选（六问必答）
python3 scripts/lessons.py promote --id L1 --by <人> --repro <复现>  # 确认后入库
```

六问：范围 · 现象 · 证据 · 动作 · 结果 · **何时不适用**（最常被跳过，而它正是边界）。
新记的一律是候选，**没有参数能直接写成权威**；升级要人确认 + 旁路复现，
`--by` 不能是 `agent`/`ai`（与签字同一条黑名单）。手工改文件绕过门禁会被 `check` 识破。

召回给的是**建议与约束，不是答案** —— 一条短路掉证据链的经验，比没有经验更糟。

## 运维:先确认源码就是跑着的那一份

排障最该先问的不是「代码怎么写的」，是**「我读的代码是不是线上跑的那一份」**。
`evidence.md` 要求「先认环境/产物」，但以前只能读源码树 —— 于是「认产物」是一句
声明，不是一次核对。

```bash
python3 scripts/artifact-match.py --artifact <线上那个 jar> --repo <源码仓>
```

从制品自己携带的身份读（`git.properties` → `MANIFEST.MF` → class 时间戳）：
`MATCH` 可以信源码 · `AHEAD` **会列出这期间动过的文件**，那就是排查第一优先级 ·
`UNKNOWN` **不是放行**，结论只能限制在产物自身的可观察行为内。

有源码时把 codegraph 用深：`trace` 查流程路径、`impact --depth 1` 查波及、
`explore` 一次拿多个符号的实现。查不到（动态分发/反射/配置路由）就**明说查不到**。
细则 [references/boost.md](references/boost.md) 第零节。

## 双向反馈:下游可以质疑上游

任何阶段发现需求有问题 → 标 `baseline-conflict` 并**停**，不自己改基线
（`deliver-schema.md`：Agent 不得自行 unseal）。反馈要带依据，不是「我觉得不合理」。

需求订正后，**全线重新对准**——最危险的是一条 `PASS` 还挂在已删除的 item 上，
于是新需求被旧证据验收：

```bash
python3 scripts/realign.py --feature <f>          # 哪里没对准（七类漂移）
python3 scripts/realign.py --feature <f> --plan   # 按什么顺序重做
```

交付后持续跟进：`ticket-metrics.sh` 的 **reopen 次数**与**签字后被推翻次数**
就是需求质量的事后信号；有硬信号走 `agent-review.sh` 起草提案 → grill → 人确认 →
改**关口**（而不是只修这一张票）。

全环：[references/feedback-loop.md](references/feedback-loop.md)。

## 需求要落到这个工程上(密封前)

**需求不能脱离代码谈。** 基线一密封就是尺，而影响面评估原本要到 `arch` 才做 ——
那时发现和存量逻辑冲突，只能 `reopen`：`revision + 1`，旧 slice / case **全部作废**。
读代码一小时，发现晚了一整轮。所以前移。

每条 item 的 `grounding`：`touches`（落在哪些 `file:symbol`）· `impact`（谁被波及，
`codegraph_impact --depth 1` 提名）· `conflicts`（与存量哪里相悖）· `boundary`
（**明确不做什么** —— 后面「为『更好』扩大范围」的闸）· `direction`（与哪条 ADR 的关系）。
市场驱动的再加 `comparison`：竞品怎么做、我们哪里**有意**不同、为什么。

**冲突和竞品差异必须挂 grill 问句** —— `experts.md`：「和已锁契约冲突却不写进问题」
是拒过项。拷问到所有细节明确无疑，这是和人的对话，不是填字段。

```bash
python3 scripts/req-ground.py --feature <f> --probe  # 要读什么
python3 scripts/req-ground.py --feature <f>          # 校验落地
```

验收标准同样在这一格定死（`stage-gate` 查主观词与可量化指标），后续所有阶段以它为准。

## 需求细到交互层(界面类需求)

`baseline.yaml` 的 item 下写 `ui` 块：screen / intent / fields（含校验与 `on_invalid`）/
actions（含 `on_success`、`on_failure`、`on_pending`）/ states（`loading`、`error`）。
**说规则，不选控件** —— 写「填错时字段下方红字并保持焦点」，不写「用 el-form 的 rules」。

```bash
python3 scripts/ui-spec.py --schema            # 格式
python3 scripts/ui-spec.py --feature <f>       # 校验 + 生成可视化
```

产出 `<票目录>/ui/<f>.spec.json`（json-render flat 格式，产线用自己的 catalog 映射到
既有组件库）与同名 `.html`（零依赖预览，评审时直接打开）。

**预览不是实现，也不是尺** —— 验收的尺永远是 `baseline.yaml`，基线一变就重新生成。
`stage-gate` 的 `ui-not-specified` 会对看起来是界面需求却没有 `ui` 块的 item 报错；
纯后端需求不受此约束。

## UI 剧本:覆盖整个生命周期(测试阶段)

剧本不是「把界面点一遍」，是**围绕一个自己造的实体走完它的一生**：

```
create → read → change → restore → cleanup
```

实体名带 `AUTOTEST`/`E2E_` 标记（**没标记的测试实体和真实数据分不开**，
清理不敢做）；`read` 在 `change` 之前（否则分不清写没写进去）；`cleanup` 放
`afterEach`/`finally`（中途失败也要执行）；不可逆的操作可以不归位，但要写明预期。

```bash
python3 scripts/ui-playbook.py --schema         # 契约
python3 scripts/ui-playbook.py --repo <仓>      # 校验生命周期
python3 scripts/ui-playbook.py --repo <仓> --plan  # 还有哪些交互面没覆盖
```

**写剧本时查状态冲突**（编写阶段，不是等跑红）：一个 flow 开了鉴权、下一个需要它关着，
**这类失败重跑不会好**。凡是改变后续前置条件的操作都声明 `// @switch: auth on`、
`// @requires: auth off`、`// @order: last`：

```bash
python3 scripts/ui-evolve.py --schema        # 开关契约
python3 scripts/ui-evolve.py --repo <仓>     # 边写边查
```

冲突有两种改法，它**提方案不改文件**：**branch**（按开关拆两个自洽 flow，剧本翻倍但
互不依赖）或 **reorder**（动开关的排最后，前面都在默认状态下跑 —— 复杂度最低）。

交互面清单由 `ui-surface-scan.py` 扫、`ui-coverage-check.py` 锁（required 要挂 wave）；
本工具管 flow 自身的生命周期完整性。**阶段齐 ≠ 测得对** —— 断言是否有意义要人评审。

## 每道关:七视角的专业性把关

`deliver/references/experts.md` 按产品 / 设计 / 架构 / 开发 / 测试 / 交付 / 排障
七档给拒过清单。其中**可机检的那一半**由 `scripts/stage-gate.py` 执行：
验收含主观词 · 解决方案冒充需求 · slice 不挂基线 · 无回退路径 · 弱断言 ·
根因未复现 ……每条都说明**为什么**不可接受。

```bash
python3 scripts/stage-gate.py --feature <f> --all
```

**机检没发现 ≠ 这一关过了** —— 另一半（拆解是否忠实 / 架构是否合理 / 用例是否有
意义）只能人过 + grill 拷问。请签前三道一起过：`check-feature.sh`（结构）+ 
`stage-gate.py`（专业硬错）+ 人按 `experts.md` 过清单。

## 准确率护栏

借 Cursor / Claude Code 在编码/测试/根因上**让它们准的机械约束**，翻译成这一层的
回报字段 + 机检：`SCOPE`/`CHANGED` 挡范围蔓延 · `READ` ⊇ `CHANGED` 挡盲改 ·
`REVERT` 给撤销锚点 · `RED_FIRST` 要求修之前见它红过 · `ASSUMED` 把猜测浮出来。
根因上用**二分**而非通读；探测用**一条消息并发**而非串行等待。

六条机检与借鉴来源：[references/agent-accuracy.md](references/agent-accuracy.md)。

## 外部工具

Langfuse（只做离线导出，不在交付路径上加网络依赖）· promptfoo（只做回报格式与边界的
回归断言，不打分）· DSPy（**不装** —— 它的 optimizer 正是内核禁的「自动改 Skill +
分数选优」，有效成分已落在回报格式、`agent-metrics` 件数、以及提案→拷问→人确认这条线上）。

接外部工具的三条判据与四处内核禁令：[references/external-tools.md](references/external-tools.md)。
