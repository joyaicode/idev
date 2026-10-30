---
audience: AI models and agents that load idev
authority: normative（术语定义以本页为准；引用处不得另行解释）
---

# idev 术语表

| 词 | 含义 | 出处 |
|----|------|------|
| 使用说明 | idev 的目标、架构思路，以及产线交付时怎么接上 `.idev/` 与文档路径 | [guide.md](guide.md) |
| 导体 | idev 内核：产品依赖它的通用工具；不含产品会话的中间文件 | `SKILL.md` |
| 内核 | `~/.cursor/skills/idev/` 真源（即 `IDEV_ROOT` 指向的 checkout）。产品中间文件不进这里；Go CLI 的数据在 `IDEV_DATA`（`~/.idev`），不在内核 | [scope.md](../conventions/scope.md) |
| `.idev` | idev 在产线交付中识别出的特性，以及需要保存的状态。写在产线工程里，供后续 idev 会话参考或使用 | [scope.md](../conventions/scope.md) |
| 标识 | idev 写入 `.idev/marker.yaml` 的 `marker: idev`。后续会话靠它认出这份持久化；`evolve: pilot` 的仓进入自进化。`extension_root` 是指向另一标记仓的相对路径 | [extension-config.md](extension-config.md) |
| 阶段页 | `.idev/extensions.yaml` 里某一阶段要打开的产线文件。进入阶段用 `session-context.py`，点名的产品传 `--product` | [extension-config.md](extension-config.md) |
| 执行产物 | idev 跑阶段时留下的 trace、复盘、inbox。在产线 `.idev/`，给定自进化参考；`docs/task/` 不是执行产物。过时原件先摘要进 `memory.md` 再删 | `scripts/execution-clean.sh` |
| memory.md | 产线 `.idev/` 里纳入版本库的摘要。自进化引用满 2 次或满 3 代时更新。外部清理忽略目录时靠 `!.idev/memory.md` 留下来。它不是用户画像，也不进代码检索 | `.idev/memory.md` |
| 跨会话的三层 | 原始证据只追加，知识要人确认，索引从源码重建。互相矛盾的轨迹并列留下 | [self-evolution.md](self-evolution.md) |
| 提升到内核 | 人主动要求后，剥离产品专有内容，`kernel-promote-check.sh` 通过，才写入内核 | [scope.md](../conventions/scope.md) |
| 试点例 | 核心页里若需要对照，必须带的标注。不是「某一个产品才是 pilot」 | `scripts/core-strip-check.sh` |
| 票 / feature | 一次交付的单位。`<票目录>` 只认 `doc_home.py --key task`。已有规范文档时这一目录是 `docs/task/<feature>/`，否则是 `.idev/task/<feature>/`。状态在 `deliver.yaml` | `scripts/lib/doc_home.py` |
| stage | 票所处阶段：`req-review → req → arch → code → test → done ⇄ ops` | [deliver/SKILL.md](../deliver/SKILL.md) |
| 前置 | 架构方案 `design.md` 里、六节之前的一节。写影响范围内的既有问题、需求行数和既有问题行数。有既有问题就问人。小于本需求改动的 1/5 或边界分得开，只用来建议本次不修。判据只在 deliver 的架构阶段 | [deliver/SKILL.md](../deliver/SKILL.md) |
| ReAct 关节 | 配方步骤上可选的 `react`。动作只能来自该步候选，且候选必须已在 `references/tools.yaml` 登记；用尽或工具失败走 `human` 或 `stop`。没声明的步骤不进循环 | [workflow-schema.md](workflow-schema.md) |
| 流水线引用 | 步骤写 `use: <配方 id>` 引用另一条配方。`tool` / `tool_group` 把已登记工具当成步骤。`adjust` 只改这一次的成员、顺序和 `label`/`with`/`react` | [workflow-schema.md](workflow-schema.md) |
| 密封基线 / seal / `sealed` | 人确认后的目标与验收基准（“尺”）；之后不得靠确认改 goal | `SKILL.md` 硬规则 3 |
| 停问点 | 阶段机里必须由人回答/确认才能继续的位置；**没有当前停问点就不请签** | [invoke.md](invoke.md) |
| 签字类状态 | `sealed` / `accepted` / `aligned` / `resolved` / `reopen_baseline` / `semantic_gate.*.passed`，只能人确认后代写 | `SKILL.md` 硬规则 3 |
| `risk_tier` | 人在 `deliver.yaml` 定的风险档：P0 鉴权/数据面/跨仓契约；P1 默认功能票；P2 文档/小修/低爆破。决定停问次数。注意：此处 P0–P2 与 coding 的模式 P1–P17 **无关** | [hitl-risk-tiers.md](hitl-risk-tiers.md) |
| 产线文档技能 | 交付时归类和落盘文档的同伴技能。目录认 setup-agents-docs，问句认 grilling | [docs/SKILL.md](../docs/SKILL.md) |
| grilling | 把边界、异议、分叉按当前编制一次问完的拷问；工具是 `~/.cursor/skills/grilling/` | [chat-confirm-signoff.md](chat-confirm-signoff.md) |
| frontier | grilling 里“尚未回答的问题集合”。一轮按当前编制把能问的都问完，挂在选项上的后续写在同一轮。frontier 为空后，需求通过那一次确认才写共享理解 | [chat-confirm-signoff.md](chat-confirm-signoff.md) |
| 编制 | 当前工程里岗位和人的对应。一个人兼任七岗，或多人各管一段。交互按它收束 | [chat-confirm-signoff.md](chat-confirm-signoff.md) |
| plan / accepted | verify 的测试计划；人确认后为 `accepted` | [verify/SKILL.md](../verify/SKILL.md) |
| selftest / test | plan 的两种 mode：selftest=开发自测（证明实现不漂基线）；test=提测。自测过后人没说「提测」不进 test | [operator-cheatsheet.md](operator-cheatsheet.md) §3 |
| aligned | 人签的“与基线对齐”；**不会**由跑绿自动产生 | 同上 |
| promote | 把快照 plan 提升为巡检包，人触发，另一刀，不随 aligned 自动发生 | 同上 |
| trial / ga | verify 的成熟度阶段；H3 只在 trial 且入口直达 verify 时才问 feedback tag | [invoke.md](invoke.md) |
| trace / v2 | 每轮把 scenario/trigger/route/stop/next 写入的运行记录。技能调起、委派、模型与组件跳是可选细节；`scripts/trace.sh append` | [trace.md](trace.md) |
| `GUIDE` | 执行者回报里给别的角色的本领域约束和证据路径。没有写「无」。导体原样抄进下一委派包的 `领域约束:`。这个字段不承担 `SUGGEST` 的含义 | [agents.md](agents.md) |
| `BLOCKED(domain)` | 本步做不下去，因为问题在另一个执行者的领域。`DOMAIN` 点名那一个。导体咨询一次，不问人 | [agents.md](agents.md) |
| 中控台 | 本机页面。看当前任务、架构、agent、耗时、skill 调起，并把窗口内的件数摊开。点一件数可带上依据，写下改关口、改这一步、补观测或质疑基线。下一轮由导体读取。不签字、不派工、不打分 | `scripts/console.py` |
| S1–S8 | 场景码，见 `SKILL.md` 决策树 | `SKILL.md` |
| H1–H6 | 非门禁不停规则（旧称 C1–C6） | [invoke.md](invoke.md) |
| P/C/R | 编码模式/气味/重构条件（P1–P17、C1–C15、R1–R6） | [coding-tables.md](../conventions/coding-tables.md) |
| T/A/F | 架构范式/出门问题/AI 失败模式 | [canon.md](../conventions/canon.md) |
| S8 配方 | 一条可被 AI 识别的流水线。产品构建的在 `<repo>/.idev/workflows/<id>.yaml`；idev `workflows/` 只留编排能力 | [workflow-schema.md](workflow-schema.md) |
| 浏览器程序 | 一次提交的一段页面操作。回执按任务和请求号保存。会改页面的同一段程序只跑一次。失败后的下一段由该页的 `advise` 给出。不绑定某一个浏览器 | [browser-program.md](browser-program.md) |
| 两阶段读 | 先列出符号和路径的薄目录，再加载一个行区间。本地 Milvus 用词和汉字双字两路召回后重排，正文仍从文件读 | [context-stage.md](context-stage.md) |
| 知识沉淀 | 可重跑的做法先记成程序候选。两条内容不同的结果且经人确认才留下。事实仍走经验账。不执行脚本，不改提示词 | [sediment.md](sediment.md) |
| 分片 | 同一步里按需拆开的独立工作。`fanout.py assess` 打出 `FANOUT` 才同时派多个 agent；每片只写自己的路径，导体 `merge` 后这一步只记一次。`SERIAL` 仍是一个 agent。第二份 run、人闸并行、产品代码写租约并行不做。验证租约可以按片发，每片只锁自己的路径 | `scripts/fanout.py` |
| 再派 | 再开一个执行者。只在它能带回上一手生成时拿不到的信息：跑出来的结果、独立读到的产物和尺、写集不相交的另一片、带证据路径的领域约束。`STATUS: PASS` 是提议，批准在检查和证据上。下一轮只接失败项和证据路径 | [agents.md](agents.md) |
| 交出口 / handoff | 产品专属、集群、脚手架类问题，交给对应产品 Skill | `SKILL.md` S7 |
| UNPROVEN | 在 canon 自问里答不出时的标记，表示“未被证据证明”，须写进 RECORD | [canon.md](../conventions/canon.md) §5 |
| `IDEV_ROOT` | 内核 checkout（`~/.cursor/skills/idev` 指向的这份）。Python 脚本用它整个挪走内核，agent 委派包里必填 | `scripts/lib/roots.py` |
| `IDEV_DATA` | Go CLI 的数据根（默认 `~/.idev`）：SQLite 库与凭据在这里，与内核 checkout 分开 | `internal/adapters/local/local.go` |
| 引擎 / `IDEV_ENGINE` | `workflow.py` 走哪条签字通道：默认 `go`（gate/lease 经 `cmd/idev`），`python` 为回退（`--by`/`--quote`）。golden 与 selfcheck 驱动段钉死 `python` | `scripts/workflow.py` |
