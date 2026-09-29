# 核心 vs 产品工程

idev 是通用工具。所有产品都可以依赖它。它不依赖任何一个产品。

产线用 idev 做 AI 端到端交付时，先走通用内核。idev 识别产线侧产生的特性；需要保存状态时，把这部分写进该产线工程的 `.idev/`。下一次 idev 工作先读这里，作为参考或继续使用。使用说明：[references/guide.md](../references/guide.md)。

这个目录由 idev 在交付中写下。交付会话的当前产品是这个仓。导体改内核、且没有当前产品时，才使用内核 `state/`。安装记录不是当前产品。

## 边界

| 放在产品工程 `.idev/` | 留在 idev 内核 |
|------|--------|
| 执行产物（自进化参考，可清理）：`traces/`、`reviews/`、`inbox/` | 通用能力：入口、模块、脚本、编排契约、不绑产品的配方 |
| 提案：`proposals/`（打开的留下；已关闭的先摘要再删） | 导体自己改内核时的 `state/`（没有当前产品） |
| 可延续摘要：`memory.md`（纳入版本库） | 摘要留在产线，不进内核 |
| 产品特性：`marker.yaml`、`extensions.yaml`、`handoff.yaml`、`pack/`、`workflows/`、`workflow-defaults.yaml`、`checks/` | 产线已有 Matt Pocock 与 grilling 文档时，交付票在 `docs/task/<feature>/`。还没有时在 `.idev/task/`。只写在一边的旧票留在原处 |

idev 第一次把该产线的状态写入 `.idev/` 时，一起写下 `marker.yaml`（`marker: idev`）。之后的会话靠它认出「这里有上次留下的产线特性」。自净化读到 `evolve: pilot` 就把该仓纳入自进化；`evolve: false` 则只留着给本仓后续会话用。缺 `evolve` 键也是 `false`，不会被当成试点。还没有这份目录时，本轮只走内核；一旦要保存产线特性或状态，就写到产线工程的 `.idev/`。第一次 `--mkdir` 保存会写下 `marker.yaml`（`evolve: false`）、空的 `extensions.yaml`、`checks/.gitkeep`、`strip-tokens.txt`，并在仓 `.gitignore` 追加保留 `!.idev/memory.md`、`!.idev/task/`、`!.idev/docs/` 的块；已有 `marker.yaml` 不改写，缺的放行行会补上。

`marker.yaml` 可写相对路径 `extension_root`，指向另一个带 `marker: idev`、自己不再委派的仓；绝对路径拒绝。阶段页、流水线、交出口、检查读扩展根，trace 仍写会话仓。`extensions.yaml` 的页可写字符串（所有产品都开），或 `{path, products: [id]}`。过滤用 `--product` 点名的产品；没点名时用会话仓 marker 的 id，不是扩展根的 id。产品仓 `.idev/traces/` 的 trace 必须有 `extensions` 字段（没有页就写 `[]`）；有列表时每一项都必须出现在 `opened`，否则审计 HARD。

产线文档在交付时打开 [docs/SKILL.md](../docs/SKILL.md)。目录认 setup-agents-docs（Matt Pocock），问句认 grilling。已经有这两套时，交付记录和人读文档用 `docs/task/<feature>/`、`docs/prd`、`docs/spec`、`docs/test-case`；同一文件也在 `.idev/` 时，规范目录优先。还没有这套文档时，阶段状态写 `.idev/task/<feature>/`，不在仓库根新建 `docs/`。只写在一边的票留在原处。目录由 `scripts/lib/doc_home.py` 解析。

执行产物（`traces/`、`reviews/`、`inbox/`）不进版本库。自进化读它们。热集合始终留下：最新 20 条 trace、带 `latest` 或 `status.env` 的复盘、未消费的 inbox、仍打开的提案。除此之外，同一文件被复盘或提案点名满 2 次，或距上次整理已满 3 代（每次真实 `evolve-review` 算一代），先把一行摘要写入 `.idev/memory.md`，再删除原件。已关闭提案走同一条。超 30 天且在最新 50 条以外的残留，仍可由 `execution-clean.sh` 按时间窗清理，删除前同样写入 `memory.md`。默认只预览，`--apply` 才删除。真实复盘结束时对当前产品和已发现的试点自动 `--compact --apply`。`memory.md` 与交出口、流水线、类页、`marker.yaml` 纳入版本库，不在删除范围内。产品仓用 `.idev/*` 忽略残留时，必须保留 `!.idev/memory.md`，这样 `git clean` 清掉忽略文件时摘要还在。

**提升到内核**只有人主动说「提升到内核」才发生。先把草稿里的产品名、仓名、协议字段、服务码剥成对所有产品成立的句子，再跑 `scripts/kernel-promote-check.sh <file>`。不过就不写入内核。剥不干净就留在该产品的 `.idev/`。

## 记下产线特性

只在这条产线成立的约束（流水线、开发规范、交出口、检查）写入扩展根：正文放 `.idev/pack/<name>.md`（流水线、交出口、检查仍放 `workflows/`、`handoff.yaml`、`checks/`），并在 `.idev/extensions.yaml` 的当前阶段下列出相对 `.idev/` 的路径。字符串页对所有产品 id 打开；`{path, products: [id]}` 只在点名的产品（缺省是会话仓 marker 的 id）命中时打开。

空的 `stages: {}` 表示这一阶段没有产线页。识别到特性却不写入 `extensions.yaml`，后续会话不会打开它。对所有产线都成立的句子不写进 pack。

## 试点 → 核心：先剥离

从任一产品往 idev **核心**放知识之前，先写成对所有产品成立的句子。写不出 = 不进核心，只留在该产品仓。

必须剥掉：

- 产品名、仓名、服务码、样板间
- 协议字段与头、环境 URL、云厂商账号模型
- 具体类名 / YAML 键 / 路由 path
- 「只在该产品这样配」的取值

可进核心的形状：生命周期、签字、红绿、证据、打开预算；「身份在 N 处必须同一字符串」（不写那一串是什么）；「不要叠第二套鉴权 / CORS 客户端」（不写具体 Filter 名）。

核心页里的产品专有标识符必须带对照标注（「试点例」/「试点：」/「例：」/e.g.）。正文规则不得依赖某一个产品。门禁：[scripts/core-strip-check.sh](../scripts/core-strip-check.sh)。

门禁两层：**L1** 三张契约页（evidence / coding / java）零产品 token，连举例都不许；**L2** 更广核心区（conventions / references / 模块 SKILL）里产品专有标识符必须带对照标注（「试点例」/「试点：」/「例：」/e.g.），无标注 = 泄漏 FAIL。词来自各 `evolve: pilot` 仓的 `.idev/strip-tokens.txt`，一行一个，内核不再内置某一条产线的词表。修法：挪到该产品仓 `.idev/pack/`，或给该行加「试点例：…」标注。

## 核心（所有产品）

| 内容 | 真源 | 产品仓怎么放 |
|------|------|----------------|
| 排查闭环（证据分级 + 逐步用例 + 七步） | **本模块** [evidence.md](evidence.md) | 只留指针，禁止再写证据表 / 七步 |
| 先对类（元规则） | 本模块 [SKILL.md](SKILL.md) | 可留产品自己的分类表；不要重复证据正文 |
| 编码规范（场景匹配 + 气味纠正） | **本模块** [coding.md](coding.md) + [coding-tables.md](coding-tables.md) | 不要把 23 模式名录抄进仓。**P/C/R 表号只认 coding.md §3.5** |
| 文档路径 / 票 | [docs/SKILL.md](../docs/SKILL.md)：目录认 setup-agents-docs，问句认 grilling | 还没有这套文档时阶段状态在 `.idev/task/`；禁止 `.scratch/` |
| 一站式脚手架 / 接入排障 / 集群事故 | 该产品的交出口 Skill | **不搬进 idev**（handoff） |

## 产品类页

当前产品的专有类在扩展根的 `.idev/pack/`。哪一阶段打开哪一页，写在扩展根的 `.idev/extensions.yaml`。进入阶段跑 `scripts/session-context.py`：它调用 `scripts/stage-extensions.py`，过滤用 `--product`，没点名时用会话仓 marker 的 id。idev 不收录任何产品的身份、配置、前端、落地或交出口名单。没有标记就只读上面的核心类。产品自己的检查放在扩展根的 `.idev/checks/`。脚本可以用 `# idev-stages: arch code` 声明适用阶段；`check-feature` 按当前阶段调用 `scripts/product-checks.sh`，并把 `--product` 传给阶段页。`from: product` 与启停命令读扩展根的 `.idev/workflow-defaults.yaml`，不在会话仓再抄一份。没有 `commands.lint_fix` 就问人。
