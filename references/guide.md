---
audience: 使用 idev 做 AI 端到端交付的人，以及执行 idev 的 Agent
authority: 目标、架构思路与使用说明以本页为准。路由只认 SKILL.md 决策树；认票与 H1–H6 只认 invoke.md；边界细则只认 conventions/scope.md；产线文档放哪只认 docs/SKILL.md。
---

# idev 使用说明

## 核心目标

idev 是人机共驾的 AI 端到端交付导体，面向所有用 AI 做交付的产线。

一次交付从需求走到可投产：密封基线、拆解、架构、编码与自测、提测、巡检，以及投产后的排障。关键状态（密封、接受计划、对齐、结案）由人确认。idev 起草、取证、跑检查、把过程写下来。

产线依赖 idev。idev 保持通用，内核里不放某一条产线的路径、服务码、交出口名单或类页。

## 架构思路

两层，先内核，再产线状态。

**内核**是工具本身：入口、场景路由、deliver / verify / ops、共享规约、编排配方的能力。任何产线都能用同一套生命周期。

**产线工程里的 `.idev/`** 是 idev 自己的记事本。产线用 idev 做交付时，idev 识别产线侧产生的特性（交出口、类页、流水线、只在这条产线上成立的约束）。需要把状态留下来给以后用时，idev 把这一部分写进该工程的 `.idev/`。下一次工作先走内核，再读这里，当作参考或继续使用。

这个目录在第一次需要保存时由 idev 创建，并写上 `.idev/marker.yaml`（`marker: idev`）。以后的会话靠它认出「这里有上次留下的产线状态」。

对所有产线都成立的句子，可以进人内核。人说「提升到内核」之后，先把产品名、仓名、协议字段、服务码剥掉，再跑 `scripts/kernel-promote-check.sh`。剥不干净就继续留在该产线的 `.idev/`。

安装记录 `state/outbound-config.json` 只说明这台机器装过哪次交出口，不决定这一次会话的当前产线。当前产线是这次正在交付的那个工程。

## 和产线的边界

细则与目录表以 [scope.md](../conventions/scope.md) 为准。使用时记住三件事：

| 内容 | 放在哪 |
|------|--------|
| 通用生命周期、签字、红绿、证据、编排能力 | idev 内核 |
| 交付票（基线、阶段、plan、review） | 产线已有 Matt Pocock 与 grilling 文档时在 `docs/task/<feature>/`；否则在 `.idev/task/<feature>/`。只写在一边的旧票留在原处 |
| 人读需求、规格、测试设计 | 同一 `<feature>`。有规范时用 `docs/prd/`、`docs/spec/`、`docs/test-case/`；否则用 `.idev/docs/` 下同名目录 |
| 执行阶段产物（trace、复盘、inbox），供自进化参考 | 该产线工程 `.idev/` 的 `traces/`、`reviews/`、`inbox/` |
| 产线特性（交出口、类页、流水线、`marker.yaml`）和摘要 `memory.md` | 同一个 `.idev/`，清理时不删 |

`.idev` 放执行残留（trace、复盘、inbox）和产线特性。执行残留不进版本库；热集合、引用满 2 次或满 3 代先写入 `memory.md` 再删过时原件。交出口、类页、流水线、`marker.yaml` 和 `memory.md` 不删。人读文档和阶段状态按 [docs/SKILL.md](../docs/SKILL.md)。

还没有 `.idev/` 时，本轮只走内核。一旦要保存产线特性或状态，就写到产线工程下。

## 产线文档

放哪以 [docs/SKILL.md](../docs/SKILL.md) 为准。目录认 `~/.cursor/skills/setup-agents-docs/SKILL.md`（Matt Pocock），问句认 `~/.cursor/skills/grilling/SKILL.md`。交付写文档时打开这份技能，不要另写一套目录。

未决问句只写该票的 `grill.md`。`convention`、`frontier`、`shared_understanding` 各自单独成行；正文用 grilling 的问句行（`❓ **Q1** - **主题**:`）与推荐答案行（`➡️`）。基线 `sealed: true` 时文件必须在，且 `frontier: empty`、`shared_understanding: true`。YAML 里残留的 `status: open` 不会被这份关闭声明盖掉。不使用 `.scratch/`。

## 一次交付怎么用

1. 打开产线工程，从 idev 入口开始。先读本页建立整体图像，再按 [agent-brief.md](agent-brief.md) 的回路执行。
2. 若该工程已有 `.idev/marker.yaml` 且 `marker: idev`，进入阶段时跑 `scripts/session-context.py`，只打开列出的 `OPEN` 行，再干活。点了产品名就加 `--product`。
3. 按 [SKILL.md](../SKILL.md) 决策树认场景，只开一个模块（deliver、verify 或 ops）。认票五步和何时不停，只看 [invoke.md](invoke.md)。
4. 文件按 [docs/SKILL.md](../docs/SKILL.md) 落盘。`<票目录>` 只认 `scripts/lib/doc_home.py --key task`。签字前跑 `scripts/check-feature.sh <feature> <stage>`，点了产品名就加 `--product`。
5. 本轮识别出新的产线特性，或产生了下次还要用的状态时，idev 写回该工程 `.idev/`。每轮路由后 `scripts/trace.sh append`，trace 落在 `.idev/traces/`。
6. 产线专属的接入、脚手架、集群事故走交出口：读 `.idev/handoff.yaml` 里的 Skill 名。名单是 idev 识别后写入的，内核里没有第二份。

快捷流水线：idev 的 `workflows/` 是编排能力。为这条产线构建出来的流水线在扩展根 `.idev/workflows/`。同 id 用产线这份。路径和开关在扩展根 `.idev/workflow-defaults.yaml`。

命令与打开预算见 [operator-cheatsheet.md](operator-cheatsheet.md)。

## 中控台

idev 跑着的时候可以打开本机页面，看当前任务、架构、各 agent 的过程、耗时、skill 怎么被调起，以及一轮的详情。计量把最近窗口里的场景、耗时、观察覆盖、回报、技能和假设摊成件数。点某一格，依据会填进定向调整。

```bash
python3 ~/.cursor/skills/idev/scripts/console.py
```

调整分四类：改关口、改这一步、补观测、质疑基线。这些话写进 console 目录，下一轮由导体读取并回复。件数不是分数，没有阈值。签字和派工仍只走导体。页面只绑本机。

## 后续会话怎么接上

下一次在同一产线工程里使用 idev：

1. 激活内核。
2. 读 `.idev/`。`marker: idev` 表示这份状态是 idev 留下的。
3. 交出口、类页、流水线直接用；trace、提案、复盘、inbox 用来接上上次的上下文。`marker.yaml` 写了 `extension_root` 时，阶段页、流水线、`workflow-defaults.yaml`、交出口和检查都读扩展根：跑 `scripts/session-context.py` 只打开列出的页，不要整包读 `pack/`。trace 与票仍写本仓。票目录用 `scripts/lib/doc_home.py`。
4. 新识别到的特性仍写回这里。

自净化会发现 `evolve: pilot` 的产线，把它们纳入自进化。复盘只把计数记在内核收据里，正文留在各产线的 `.idev/`。不纳入自进化时，标识里是 `evolve: false`，状态仍只给这条产线的后续会话用。说明见 [self-evolution.md](self-evolution.md)。

## 读哪一页

| 要做的事 | 打开 |
|----------|------|
| 目标与本说明 | 本页 |
| 边界目录表、提升到内核 | [scope.md](../conventions/scope.md) |
| 这一轮走哪个场景 | [SKILL.md](../SKILL.md) 决策树 |
| 认票、何时必须停、何时不要停 | [invoke.md](invoke.md) |
| 产线文档目录与未决问题 | [docs/SKILL.md](../docs/SKILL.md)；目录认 setup-agents-docs，问句认 grilling |
| 术语 | [glossary.md](glossary.md) |
| 命令 | [operator-cheatsheet.md](operator-cheatsheet.md) |
| 运行中看 agent、耗时、件数，并写下调整 | `python3 scripts/console.py`，说明见上文「中控台」 |
