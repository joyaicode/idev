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

**产品目标：** 人机共驾的 AI 端到端交付（关键状态须人确认）。**不是**无人值守自动 seal→promote。使用说明：[references/guide.md](references/guide.md)。

**Agent 先读：** [references/agent-brief.md](references/agent-brief.md)（最小执行回路 / 何时必须停问人 / 冲突时听谁 / 编号只认一处）· [references/glossary.md](references/glossary.md)（术语表，不认识的词先查，别猜）。本页决策树是**路由的唯一权威**，其它页的路由表只是摘要。

## 你是谁：skill 与 agent 分工

**你是被 `/idev` 加载的 skill，你是导体。** `agents/` 下的五个执行者是 subagent，它们不是你。

| | 你（skill / 导体） | 它们（agent / 执行者） |
|---|---|---|
| 做 | 认票 · 认场景 · 路由 · 组委派包 · 验收回报 · 记账 | 在落点页里干活 · 产出工件 · 给证据路径 |
| 独占 | **签字权** · 与人交互（请签 / 停问 / 唤起 grilling） · 写 trace | 独立上下文（互不污染） |
| 不能 | 亲自执行已委派的 step | 签字 · 问人 · 写 trace |

**为什么导体这件事不能也委派出去：** subagent 看不到对话历史，无法与人往复确认；而
`scripts/lib/workflow_spec.py` 的 `is_human()` 黑名单正是 `{agent, ai, cursor, assistant}`——
**agent 签字在代码层就被拒**。你是唯一能听到人说「确认」的一方，所以签字只能你代写。

五个执行者：`idev-deliver`（需求/架构/文档）· `idev-coder`（编码/构建/提交）·
`idev-reviewer`（审查）· `idev-verifier`（红绿/环境）· `idev-ops`（排障/论证）。
完整职责分离、四条硬依据、以及两者之间仅有的三样接口：[references/agents.md](references/agents.md)。
**怎么用**（何时走 `/idev`、何时直接点 agent、委派包最常漏什么、出问题按什么顺序查）：
[references/agents-playbook.md](references/agents-playbook.md)。

S8 每步按 `workflow.py next` 打印的 `DELEGATE` 行派活；`DELEGATE none` 表示这一步你自己做
（`human.gate` 永远是 none）。委派后按 [references/agents-evolve.md](references/agents-evolve.md)
落一份留痕，它是这一层可调试的全部前提。

## 提效三板斧

把规约里**已经要求、但以前只能靠自觉**的事变成可执行、可机检、可计数。不新增门禁，不打分。

| 阶段 | 执行者 | 做什么 |
|---|---|---|
| 编码 | `idev-coder` | `coding.md` §0 三项交代（`CHANGE_KIND`/`CANON_TRIGGER`/`TABLE_HIT`）+ codegraph 影响面 + 增量自测 |
| 测试 | `idev-verifier` | 维度表先铺满用例骨架 + 失败签名归一化（`scripts/failure_signature.py`） |
| 根因 | `idev-ops` | 假设台账（`scripts/hypothesis.py`）+ 证据链 + 有界修复红线自动计数 |

要算数就写代码，不要口算：`scripts/repl.py` 把计算的源码与输出落成票目录里的证据
（[references/code-agent.md](references/code-agent.md)）——散文推理不是证据，
算出来的结果加上能重跑的脚本才是。

`verify/SKILL.md` 硬规则 5 原文就是「有 codegraph 就用」，`conventions/evidence.md` 第 5 步
原文就定了三条有界修复红线 —— 这三板斧只是让它们**判得出来**。细则
[references/boost.md](references/boost.md)；待办与验证状态
[references/agents-todo.md](references/agents-todo.md)。

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

## 每道关:七视角的专业性把关

`deliver/references/experts.md` 按产品 / 设计 / 架构 / 开发 / 测试 / 交付 / 排障
七档给拒过清单。其中**可机检的那一半**由 `scripts/stage-gate.py` 执行（21 条）：
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
| 说不清 | — | — | 先看 `deliver.yaml` 的 `stage`；仍不清问一句 |

小改不要无故从 S1 重开。签字（sealed/accepted/aligned/resolved）永远人确认；边界不清先 grilling。每轮末 `scripts/trace.sh append`。

## 场景（S1–S8）一句话

S1 新票→deliver `req-review`（必开 `docs/SKILL.md` 与 grilling）· S2 推进当前 stage · S3 verify 红绿/promote · S4 分析论证→conventions/evidence · S5 契约/经验回填→`docs/SKILL.md` · S6 线上现象→ops · S7 产品专属→交出口 handoff · S8 命中 `workflows/<id>` 别名→`scripts/workflow.py` 按配方逐步驱动。
认场景 → 对类（S1/S4/S6 先读 [conventions/SKILL.md](conventions/SKILL.md)）→ **只开一个**执行模块，不要把 deliver / verify / ops 一起加载。各场景必开/禁开全表：[references/skill-details.md](references/skill-details.md)。
**配方命中：** 原话子串命中配方 id 或其别名 → S8。当前产品 `.idev/marker.yaml` 为 `marker: idev` 时，先看该仓 `.idev/workflows/`，再看 idev `workflows/`（编排能力）。同 id 用产品仓那份。多条取最长别名，优先于仅含 stage 动词的 S2/S3。配方要求 `product` 时，原话必须点明恰好一个产品名，否则不启动、不猜。构建出来的流水线写在产品仓 `.idev/workflows/`，不写进 idev。

认票五步与非门禁不停（H1–H6）全文只在 [invoke.md](references/invoke.md)。无停问点不请签、不擅自 promote、不为观测另停。`done` 后改 goal 须人说「解除密封」或 `reopen`。

## 共享硬规则（一句话版，全文见 [skill-details](references/skill-details.md)）

1. 先守公共规约（[conventions/SKILL.md](conventions/SKILL.md)）。产线做端到端交付时先走内核。idev 识别产线侧特性，需要保存时写入该工程 `.idev/`（含 `marker: idev`），后续会话再读。写产线文档前打开 [docs/SKILL.md](docs/SKILL.md)（目录认 setup-agents-docs，问句认 grilling）。进入阶段先跑 `scripts/session-context.py`，只打开它列出的 `OPEN` 行；点了产品名就加 `--product`。人说「提升到内核」并完成产品剥离后，才写进内核。详见 [conventions/scope.md](conventions/scope.md)。
2. **证据优先**：AI 反馈与文档不可信，代码逻辑可信仍须用例证明；每步先设计用例再推下一步。[conventions/evidence.md](conventions/evidence.md)
2a. **边界未订死必须自动唤起 grilling**（`~/.cursor/skills/grilling/SKILL.md`），不准自拷问顶替；未到 frontier 空且人未确认前**禁止**写 sealed/accepted/aligned/resolved、禁止进下一阶段。触发细则 [cheatsheet §7.2](references/operator-cheatsheet.md)。
3. 尺是密封基线。无本轮确认用语不得写 `sealed`/`accepted`/`aligned`/`resolved`/`reopen_baseline`/`semantic_gate.*.passed`；`继续` 不算；不准用确认改 goal。[references/chat-confirm-signoff.md](references/chat-confirm-signoff.md)
3a. **架构与设计质量**：`arch` 阶段和任何“加层 / 拆分 / 缓存 / 队列 / 重写”念头，先按 [conventions/canon.md](conventions/canon.md) §1 协议执行（T1–T12、A1–A8）；命中即停按动作做，落到 P/C/R；不新增强门禁。
4. 红绿只走 verify。不准第二套测试框架或分数门禁。
5. 签字前 `bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> <stage>`；已 accepted 的 plan 再 `run` 不重跑 verify-plan。
6. 巡检包 `verify/scripts/promote.sh <feature>`：人没提 promote / 巡检包则不问、不跑。
7. **改本 Skill 只改真源** `~/.cursor/skills/idev/`（`~/.agents`、`~/.joycode` 是 symlink，勿复制第二份）；提案 + 拷问后再改。
8. **每轮路由后写 trace（schema v2）**：`bash ~/.cursor/skills/idev/scripts/trace.sh append`。产品仓会话落 `<repo>/.idev/traces/`，不写进 idev 内核；只有导体自身会话才落内核 `state/traces/`。必写 `route.scenario`、`invoke.trigger`/`matched`、`thinking.summary`、真实 `calls[]`/`opened[]`，不准伪造调用，不为观测另停；对话给一行运行路径（`scripts/path-view.sh`）。[references/trace.md](references/trace.md) · [references/invoke.md](references/invoke.md)

## 链接

先读 [使用说明](references/guide.md) · [operator-cheatsheet](references/operator-cheatsheet.md) · 细则 [skill-details](references/skill-details.md) · 新票 vs 小改 [s1-vs-s8](references/s1-vs-s8-playbook.md) · HITL [hitl-risk-tiers](references/hitl-risk-tiers.md) · 全图 [lifecycle](references/lifecycle.md) · 内聚 [cohesion](references/cohesion.md) · 自进化 [self-evolution](references/self-evolution.md) · 可移植 [portability-checklist](references/portability-checklist.md) · Linux 调度 [linux-schedulers](references/linux-schedulers.md) · aisel 对照 [aisel-mapping](references/aisel-mapping.md) · 自检 `scripts/syntax-check.sh` → `scripts/agents-check.py` → `scripts/agent-smoke.sh` → `scripts/healthcheck.sh`（含 late-lifecycle / second-product smoke）· 周审计 `scripts/audit-traces.sh 50`
