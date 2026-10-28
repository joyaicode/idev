# idev 变更记录（给人看，Agent 无需读取）

- 2026-10-28：架构评审三阶段落地。阶段 0：留痕路径、自检/CI、白名单、AUTO 自跑、产物移出跟踪。阶段 1：客户端钩子、`prompts.log` 核对 quote、计时覆盖率、trace 骨架、结构化回报、`idev run write`+`ProjectRunWithAudit`（Go 默认写 YAML，空 expect 也 stale）。阶段 2：outcome 度量、console 在制品老化、timeline 保留结构化字段、A/B 评测夹具、usage-scan/attic、删除预算与 curator。阶段 3 提案 blocked（要触发条件）。人确认阶段 0–2 各提案原话；未提交。

- 2026-10-27：分析代码的步骤里，更新索引写在读代码之前。审查的 `coding-scan`、根因里的 `codegraph_impact`、需求落地、事实工具箱和结构问题原先都是先读后更新。`scripts/test_codegraph_before_read.py` 锁住这个顺序。

- 2026-10-26：缺的槽位用 `workflow.py param` 写回当前开放步骤。工具登记的 `inputs` 缺了也先 `ASK`。`next` 对照 `recipe_digest` 打出 `DIGEST match|drift|missing`，文件变了不改已展开的步骤。声明了 `react` 的步骤打出 `LOOP` 状态，不挡这一步。分支不能落进一组的中间，也不能跳到已经记完的步骤。

- 2026-10-26：步骤可以声明 `slots` 和向前的 `branch`。缺槽位时 `next` 先 `ASK`，不委派。工具失败走 `on_fail`（`human` / `stop` / `skip`），跳数用尽仍走 `on_exhaust`。`skip` 保持循环开着，不写 inbox。工具可以登记 `inputs` / `outputs`，`next` 打出 `IN` / `OUT`。`show` 回放这一跳的 Thought、Observation 和 `TOOL` 命令。`start` 把配方摘要写入 `recipe_digest`。周审计多计工具跳，并点数未消费的关节失败，不进 `HARD_COUNT`。

- 2026-10-26：运行路径在 hops 一行下面按跳列出「追踪」，带上 `why`、`result` 和耗时，并写出顶层 `react:`。控制台把这条链画出来，时间线单独列出工具跳。不打分。

- 2026-10-26：配方步骤可以写 `tool`、`tool_group` 或 `use`。工具和工具组按 `references/tools.yaml` 的步骤协议展开，一条配方可以引用另一条。`adjust` 能跳过、排序、替换 `label`/`with`/`react`，或追加步骤。`next` 对工具步骤只打出 `TOOL` 命令。

- 2026-10-26：声明了 `react` 的步骤，`next` 打出 `REACT_LOG` 绝对路径和 `REACT_OPEN` 到 `REACT_SHOW`。这些行只打印。本轮 trace 的 `react:` 抄 `REACT_LOG`。同类失败标签满两次，`evolve-review` 算热标签并起草提案，不改 Skill。

- 2026-10-26：ReAct 失败的 inbox note 带上 step、工具名和观察摘要。`next` 打出 `REACT_LOG`。`react_loop.py show --feature` 列出该 feature 的每一跳、成败和耗时。

- 2026-10-26：ReAct 候选必须先登记在 `references/tools.yaml`（`id`、`summary`、`command`）。`workflow-check` 和 `react_loop.py open` 拒绝未登记的名字。`act` 打出该工具的 `TOOL` 命令。登记本身不执行命令。

- 2026-10-26：配方步骤可以声明 `react` 关节。循环只在候选工具里走，用尽或工具失败走 `human` 或 `stop`，并把每一跳写入当轮 trace。反馈进 inbox，不自动改配方。没声明的步骤行为不变。人确认：by wangwei794，quote「确认」，2026-10-26T11:28+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：规范插件不再把正确写法报成违规。`===` / `!==` 不算 `==` / `!=`。`try (` 里后面的资源不算漏收的流。Shell 只报会分词的未加引号变量，引号、命令替换里的引号、heredoc、`[[ ]]`、`$(( ))` 不算。Go 不再用正则猜被丢掉的返回值。闸门读标准输入失败时把错误返回去，不再当成空回答。人确认：by wangwei794，quote「确认」，2026-10-25T20:28+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：前置节只要列出既有问题就问人，选项是先修或本次不修。小于本需求改动的 1/5 或边界分得开，只写进 `scope_debt.recommend: mark`，不代替人的选择。一条都没有才直接 `mark`。仍是 B 类决策，不增加第五次签字。人确认：by wangwei794，quote「确认」，2026-10-25T16:09+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：架构方案在六节之前写 `## 前置`。先审影响范围内已经存在的问题。没有重大缺陷，并且规范与质量改动小于本需求改动的 1/5，或者和本次改动分得开，就只在方案里标明，不另开子需求。有重大缺陷，或比例达到 1/5 且分不开，先问人要不要先修；同意则另开缺陷修复或重构子需求，从头做完再实施本需求。不新增机检，不增加第五次签字。判据只在 `deliver/SKILL.md` 的架构阶段。人确认：by wangwei794，quote「确认」，2026-10-25T15:55+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：Python、Go、Shell、JS/Vue 规范扫描只依赖 `scripts/plugin/` 里的 `python_inspect.py`、`go_inspect.py`、`shell_inspect.py`、`js_inspect.py`。`coding-scan.sh` 调用 `lang-scan.sh`。不安装 ruff、golangci-lint、shellcheck、eslint 或 Node，也不下载。插件不在时退出码 2，是 `UNPROVEN`。`python3 -m compileall` 的 0 不是这层扫完。
- 2026-10-25：Java 规范扫描只依赖 `scripts/plugin/java_inspect.py`。`problems-scan.sh` 不再安装 IntelliJ，也不安装 JDK。插件看未收进 `try (` 的流、没有调用的私有方法，以及至少两处调用都是同一字面量的私有形参。插件不在时退出码 2，是 `UNPROVEN`。
- 2026-10-25：编码和 Review 的 Java 规范扫描加上 Qodana。`coding-scan.sh` 调用 `problems-scan.sh`：本机已有 CLI 和检查插件就用；没有就远程安装到 `$HOME/.cache/idev/qodana`；没有网络就用 `offline/qodana`。插件不可用时仍用本机 IntelliJ `idea-inspect.sh`。两个引擎都没有报告是 `UNPROVEN`，不是扫干净。二进制不进 git。

- 2026-10-25：编码和 Review 的 Java 规范扫描由 `coding-scan.sh` 调起 `idea-inspect.sh`。它用本机已安装的 IntelliJ（`IDEA_HOME` 或本机 Applications / Toolbox），profile 名 `Project Default`，不下载，不改 `idea.plugins.path`。没有安装时退出码 2，输出 `UNPROVEN`。`java_hygiene.py` 的 0 仍然不是 Problems 已空。易受攻击的依赖项只计数，不作为这次失败。

- 2026-10-25：架构方案和编码补上码如文字、最小实现。定义仍在 `coding.md` 底线 4、5，已确认的前三条不改。方案和代码顺着读要能指出重点；注释只写代码看不出的为什么。用最少的代码实现目标，只权衡这一轮碰到的性能、并发安全、易使用、易扩展，无基线不优化。文件数和行数说不出换来什么就是膨胀。只有 get/set、没有业务信息的哑对象是拒过；协议形状可以只有字段。`design.md` 方案节和 A1 要答到这一点。不另起编号，不新增机检。人确认：by wangwei794，quote「确认」，2026-10-25T14:35+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：`java_hygiene.py` 报 blocking 0 不能当成 Problems 已空。它只覆盖正则能判定的子集。验收以 IntelliJ「Project Default」对改动模块的 `inspect.sh`（或同一配置下的 Problems）为准。try-with-resources、形参恒定、非 getter 的未使用方法、拼写不在这套正则里。

- 2026-10-25：编码和 Review 守住文首底线三条，定义只在 `coding.md`。大道至简：不把问题做成框架或分层；关键路径（失败会让基线结果错或没有）当轮写失败条件、怎么停或怎么降、日志，其它路径不加 catch / 默认值 / 重试。易用性：人能看出入口和失败时怎样；扩展沿现有类型和契约加，不改已有分支的含义，也不为以后预埋钩子。禁止随意发挥：每段新代码要指得出依据（基线、本轮那句话、第三次重复、或已经看到的失败），指不出就删。命中仍落 `T#`/`C#`/`P#`/`F#`，不另起编号，不新增机检。`idev-coder` 写前过，`idev-reviewer` 先于总则写成 `I*`。人确认：by wangwei794，quote「确认」，2026-10-25T14:15+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：`TaskStore` 的 Problems 仍在时，审查不能报 blocking 0。blocking 补上 `Collections.sort` → `List.sort`、`(a, b) -> a.f.compareTo(b.f)` → `Comparator.comparing`、循环里的 `Thread.sleep`、40 行内相同的日志句子。间隔等待改 `TimeUnit.MILLISECONDS.sleep`。没人用的返回值改 `void`，没人调用的方法删掉。

- 2026-10-25：`TaskExecutor` 的 Problems 仍在时，审查不能报 blocking 0。`Collections.<K, V>emptyMap()` 这类「可以推断」改为 blocking。`src/main` 里简单 getter 没有生产调用记「方法从未使用」（只在测试里调用也算未使用）；模块 pom 已有 Lombok 时，仍被生产调用的 `return field` 记「可以具有 Lombok @Getter」。`Collectors.<T>toList()` 仍是 note。

- 2026-10-25：代码审查先清 java.md 里能机检的黄条，再写内聚和设计模式。`scripts/lib/java_hygiene.py` 扫分支 diff。blocking 是构造上的显式类型参数（`new ArrayList<String>()` → `<>`）、`valueOf`、compiler=8 的 `List.of`；匿名类在 compiler=8 不报。`Collectors.<T>toList()` 只作 note，Java 8 经常推断不出来，不打回。`coding-scan.sh` 会打出这些行。`review.report` 漏记 blocking 的 `file:line`、以及 `code_pass` / `review.fix` 把 blocking 留在 `CHANGED` 里，`delegation.py` 的 `java-hygiene` 打回。不新编号。

- 2026-10-25：五个执行者都能沿交付链读上游的尺和下游的后果，落笔仍只在自己的 kind。本领域以拒过清单为下限。指导别的角色只经导体：回报 `GUIDE` 由导体抄进下一委派包；`BLOCKED(domain)` 才另派一次咨询，不问人，咨询不套娃。`SUGGEST` 仍只说本定义哪一步含糊。`delegation.py write` 把抄约束、咨询、打回打成 `HANDOFF` / `CONSULT` / `REBRIEF`，导体照着做。

- 2026-10-24：中控台加上计量和定向调整。计量把最近窗口的场景、执行者耗时、观察覆盖、回报、技能调起和假设摊成件数，不打分、不设阈值。点某一格，依据写进意见。意见分改关口、改这一步、补观测、质疑基线，仍进 console 线程，下一轮由导体读取。页面不派工、不签字。

- 2026-10-24：分片草稿已经在磁盘上时，`fanout.py assess` 打出 `MERGE`，清单仍保留每一片。不再只留下还没写完的那一片，也不再派一个执行者去重写 `review.md` 或 `plan.yaml`。已经签收的 `review.md` 不会被合并盖掉。

- 2026-10-24：审查和用例起草可以按片派。`review.report` 在写集不是单独一份 `review.md` 时，按改动的顶层模块分片深读，机械扫描仍是一条 `coding-scan.sh`。`verify.plan` 在还没有两条 `case_intent` 时，按已签收的 `I*` 分片，每片只写自己的 shard 和 `verify/checks/<I*>/`。`FANOUT` 时 `delegate <step> --shard <id>` 发的验证租约只覆盖该片路径，不再放大成整棵票目录。留痕落到 `delegations/<run_id>/`，新的一轮不再撞上旧的 `report-1.yaml`。`review.fix` 仍是一个执行者。

- 2026-10-24：外挂 Skill `~/.cursor/skills/super-linter`（包装 upstream Super-Linter）。仓内已有 workflow/env 时由 `coding-scan.sh` 打印 Skill 路径并走本地工具映射；不默认拉镜像。人明确要求容器跑时按 Skill 钉 `v9.0.0`。`link-companion-skills.sh` 可显式链 `super-linter`。命中仍译 P#/C#。
- 2026-10-24：中控台。`python3 scripts/console.py` 在本机打开一页，看各 agent、耗时、skill 调起和详情，并可下达任务、对话。数据仍是 trace、委派留痕、`run.yaml` 和假设台账。页面上的话进 console 目录的线程，导体下一轮读取并回复。派工前记一条进行中，回报后清掉。控制台不签字、不派 agent。

- 2026-10-24：自测、用例设计、用例执行、根因可以按需拆成多个 agent。`fanout.py assess` 先看工作是不是彼此独立：少于两片、写集相交、或同一个 Maven 模块没有 `runner.parallel: true`，就保持一个 agent。`FANOUT` 时同一条消息派每个分片，分片只写自己的路径，导体 `merge` 后这一步只 `record` 一次。仍是一份 run。`verify.plan` / `verify.run` 的 `next` 会打出 `FANOUT_ASSESS`。
- 2026-10-24：波次打开时给票目录留哈希，组外的新文件 `record` 拒绝。`delegate --open` 一次委派当前波的每个 agent 步骤。`steps` 投影带上 `group_id` 和 `writes_json`，读回来的 run 用 `Open`。`design.md` 六节、`case_intent` 和报告只索引进了 `check-feature`。配置了 super-linter 时 `coding-scan.sh` 跑本机已有的对应工具，不下载。
- 2026-10-24：`review.fix` 之后增加 `refresh`，把 case status 回写 `verify/plan.yaml`，并重写 `selftest.md` 和 `accept.md`。带 `writes` 的步骤若已有委派，回报必须有 `CHANGED`，写出清单之外的路径则 `record` 拒绝。Go 的 `Run.Open` 让同一 group 的步骤可以一起激活，组后面的步骤仍要等组内全部完成。
- 2026-10-24：`lite-change` 在编码之后把用例、自测、独立审查、验收索引放进同一个 `group: check`，写集分别是 `verify/plan.yaml`、`verify/selftest.md`、`review.md`、`verify/accept.md`。`next` 打出 `PARALLEL`，`record` 和 `delegate` 接受组内任一未完成步骤。人闸和写租约留在组外，审查修改和实现审核仍在这一波之后。
- 2026-10-24：五份文档收成同一体例；编码完成前必须由审查者写编码规范节；扩展配置的每个键有解释和示例。需求、设计、用例、Review、测试报告同一事实只写一处，人读和机读对同一批 id（`docs/SKILL.md`）。`lite-change` 在实现审核前增加 `review.report` 与 `review.fix`（`accept_all_findings`），不另设人闸。`review.md` 要有 `审查者: idev-reviewer` 和带数字的 `文件与行数`。§2.4 补单文件 400 行、新增文件、触及文件。规范扫描跑仓内已有的那一套（super-linter 是例子，不新装）。`references/extension-config.md` 解释 marker / extensions / workflow-defaults 的每个键并给示例；`config-doc-check.py` 对一下内核真的去读的键。

- 2026-10-23：trace 补四层可选观察，给减负和 shortcut 用，不新增门禁。技能调起写 `invoke.how` / `invoke.skills[]`；委派决定写 `decisions.kind: delegate`（`none` 表示导体自己做）；模型与一行思考写 `kind: model` 和 `calls.thinking`；组件从哪跳到哪写 `calls.from` / `calls.to`。运行路径多 `skills` / `choices` / `hops` 三行，空着是 `(none)`。`path-stats` 与周审计各加一组计数（技能入口、委派、模型、组件跳），不进 `HARD_COUNT`，也不进必须清零。旧痕迹不用回填。

- 2026-10-23：交付主路径收成四次人确认。需求把不明确的问题一轮问完（可多轮），回答不是签字，每个档位在拆解末一次写密封和拆解通过。架构先交整包方案等人 Review，有分叉才拷问，此阶段不交用例。通过后连续做用例、编码、自测，计划无信号则自动过。自测完成后停一次实现审核，然后提测，最后只确认测试结果。promote、推送、解封、回退、经验入库不动。提案 `state/proposals/20261023-fewer-signoffs.md`。

- 2026-10-22：code-review 真票全程闭环（joypaas，run 01M5F7EKCQ1EK4M5ANY5CRQF70 done：report→gate-report（chat 通道人签）→plan（5 selftest case，verify-plan 门禁 0 FAIL）→gate-plan（P1 AUTO）→fix（两轮委派+reviewer 独立复核，894/0/0/3）→run（5/5 PASS））沉淀三件，两件当轮落地、一件立稿待审：① **delegation 留痕 YAML 折叠吞换行（已修）**——`delegation.py write` 落盘 `report.raw` 经 `yaml.safe_dump` 单引号折叠把多行回报压成一行，行锚定机检（FACTS/DOC_DRIFT/SCOPE/RED_FIRST/ASSUMED/S0）全部失明并误标 agent 责任；新增 `scripts/lib/yaml_representers.py`（LiteralString + 块标量 representer），落盘改走 `yaml_representers.dump`，换行保真；端到端验收：合成多行 raw 落痕 RC=0 零 FAIL，golden 50 same、selfcheck/syntax/refs/agents-check 全绿。② **方法名锚点惯例（已落）**——I1/I3 行号在 review 与 fix 之间漂移（101→122、1893→1669），两轮委派靠「方法名+第 N 个该构造」才定位成功；`idev-coder.md` 的 CHANGED 字段、`idev-reviewer.md` 硬规则 6、`workflow-code-review.md` 的 I* 位置字段统一改为 file:方法名 锚点为主、行号辅助。③ **selector 断言对应（已落）**——I1 的 plan selector 指向配置绑定侧测试（38 例但不断言 validateMapped），真正断言在 BudgetRecognizerTest；`idev-verifier.md` plan 骨架节补「selector 必须指向含该 case assert 语句的测试类」。提案稿 `state/proposals/20261022-delegation-raw-folding.md`（status: draft）记录全过程证据链。

- 2026-10-22：存活探测不再指向全量 `healthcheck` / `agent-smoke`。这两份和四条套件一样，`block_until_ms` 大于 30000 记 `suite_block`。存活是一行不调用工具的回复。

- 2026-10-22：selfcheck、golden record、gate-channel、lease-channel 的 `block_until_ms` 大于 30000 时，`turn-budget.py` 记 `suite_block` 并失败。先说一句再把这四条套件等到结束，不再放过。`block_until_ms` 为 0 的后台启动通过。其它长命令仍只要先开口。

- 2026-10-22：回合预算的机检补上已经写进 Skill、但脚本没判的三条。先开口再连续 9 个无正文回合会失败；`block_until_ms` 大于 30000 且这一条和上一条都没有正文会失败；命令里的 `claude -p` / `agent -p` 会失败。先说一句再跑长命令仍然通过。结构问题用 `codegraph_context` 仍是做法，不进脚本。

- 2026-10-22：回合预算落地（提案 `state/proposals/20261022-agent-turn-budget.md`）。聊天里长命令先说一句再放后台，连续 8 个无正文工具回合先报现状，存活探测不再用 `claude -p` / `agent -p`。`scripts/turn-budget.py` 只数第一句正文之前的无正文回合，红夹具 9 失败、绿夹具一行 `ALIVE` 通过，`selfcheck` 跑这两份夹具。不并行多开执行者，不改迁移跳过和租约时长。

- 2026-10-21：签字改成聊天确认。人回复 `确认` / `同意` / `全签` / `LGTM` 即认可当前停问点，导体 `record PASS --by --quote` 落笔；终端 `idev gate approve` 仍可用，不再是必经。密封、架构、提测在每个档位仍各要一次确认。同日先把 P1/P2 架构关改成机检通过即过，人补了一句「架构方案还需要我签」，该条撤回。E1.2（把生命周期闸改成终端批准）否决。

- 2026-10-21：代码审查对规范显式成文。`coding.md` 文首新增**规范总则**五条（控制膨胀 / 高内聚低耦合 / 条件链先上模式 / 语法糖优先 / 复杂度有界），编码侧补「写完回扫本轮 diff」一步、Review 侧在最前补「先扫总则」一步（六步变七步，`idev-reviewer.md` 展开同步）。`coding-tables.md` §2.4 量化阈值补两行**变更级**粗筛（净增行数说得出换来什么 → T1/C3/C6；单文件变更理由 = 1 → C12/C1），与函数级五行同表同判定；§1 P5「运用」列补按栈语法糖一句（Java 多例 SPI / 经典 switch；Go 表驱动；Vue/TS 对象查表 + computed）。克制：命中一律落既有 `P#`/`C#`/`T#`，不新增报告字段与机检——`check-feature.py` / `test_review_coding.py` / golden / agent-smoke 零改动，`review.example.md` 编码规范节字段不变（仅说明行点出总则同扫）。

- 2026-10-21：`start` 不再把「没有 steps」或读坏的 `run.yaml` 当成没有进行中的 run 去覆盖。`record` / `abort` 在 `run.yaml` 写成功之后才更新 `report.md`，避免报告跑在 run 前面。`decisions.yaml` 里有一条不是 mapping 的记录时，`decide` 拒绝再追加。

- 2026-10-21：两个 `start` 不再各自写一份 run 再互相覆盖；检查和写入在同一把锁里，已有进行中的 run 就拒绝。同一个 signal 在同一次 attempt 上只接受一个 `decide`，第二次会和第一次矛盾，直接拒绝。

- 2026-10-21：`ask` / `record` 不再占着 `run.yaml` 的锁去跑 `idev`。问已经写入 SQLite、编号没落进 run 时，再次 `ask` 写回已有的 pending 编号（冲突信息里带这个编号；落盘失败则留在 `gate-<step>.id`），不开第二问，也不会把人卡在没有编号的 pending 上。已批准且内容未变时不再另开一问。

- 2026-10-21：大规模并发下两处会失真的检查。`idev` 每次打开数据文件都跑 goose.Up，即使 schema 已是当前版本也会占写锁，一群 gate/lease 查询会排在一次空迁移后面；已记录版本不低于内嵌迁移时改为只读版本号，落后的库仍会补迁移。`deliver.code_pass` 这类独立复核原来只核对 `--verified-by` 和 `--verify-evidence` 两个字符串，报告可以不存在；现在报告必须是非空文件，且 `delegations/` 里要有复核者自己的留痕用整词引用该路径，执行者的留痕不算。空文件和缺失文件分开拒绝。

- 2026-10-21：需求签收后的方案评审要交齐三份，并经 grilling。`check-feature` 在 `arch` / `code` / `test` 要求 `design.md` 六节（目标照抄基线 goal，点名每条 item 与 case_intent）、`grill.md` 的 `## arch` 轮闭合（`arch_frontier: empty`，`arch_shared_understanding: true`），以及 `verify/plan.yaml` 与 `case_intents` 按 slice / item / dimension 一一对应。`verify-plan` 也查这组对应。编码阶段补 runner，不另起用例。

- 2026-10-20：销 N1（设计 v3 的 `IDEV_ROOT` 与术语表冲突）。设计文首（版本块末）补术语注记：本文是 idevd 落地后的目标态，`IDEV_ROOT`（默认 `~/.idev`）指唯一配置根；迁移完成前以 [glossary.md](glossary.md) 的两个词为准——`IDEV_ROOT` = 内核 checkout（`~/.cursor/skills/idev`）、`IDEV_DATA` = Go CLI 数据根（默认 `~/.idev`）。设计文件 SHA-256 `7672a259…9824fea0` → `7db523d4…974fcbde`，README「Go 核心」段同步；agents-todo 验收段保留验收时点值并注明当前值；N1 行按「做完即删」移除（其完成判据即文首注记）。同笔并入当日 README / agents-todo 验收状态对齐：lease-channel 17 例与 verify 租约围栏描述、`go test -race` 注释（domain 零 IO；app 与 sqlite 同测）、停问步说明改「先 `ask`，人在自己的终端 `idev gate approve`，再 `record PASS`（不带 `--by`/`--quote`）；`IDEV_ENGINE=python` 才回到人名加确认原话」。

- 2026-10-20：修 go 引擎下 verify 租约从不生效的安全缺口。`kinds.yaml` 声明 `lease: verify` 的 kind（verify.run 等，执行者只许写票内验证产物）在 `workflow.py` 只对 `lease: write` 走租约围栏，verify 类从不取租约、record 也不校验——Go CLI 的 `--purpose verify --ticket-dir` 早已支持（ticketDir 必须搭配 --purpose verify，且自动把 `ticketDir/**` 并入 WritePaths），缺的只是 Python 驱动接线。TDD 先红后绿：`needs_write_lease` 重构为 `lease_purpose()`（write/verify/None），新增 `ticket_dir_repo_relative()`（票目录不在 git 仓内直接 Blocked）；`delegate` 的 verify 分支以 `--purpose verify --ticket-dir` 取租约（打印 `LEASE … fencing=N … paths <ticket>/**`）；`record` 对 verify 类 PASS 无租约拒绝、改动越出票目录拒绝并要求 revert；write 类两套文案与行为原样保留。lease-channel 断言 13→17（无租约拒绝 / 围栏限票目录 / 越界拒绝 / 票内释放后 RUN DONE，rival fencing 断言 2→3），红态 12 OK 5 FAIL 形态与预测一致；回归 gate-channel 14 OK 0 FAIL、golden 50 same 0 different、selfcheck PASS。

- 2026-10-20：agents-todo #7 首段（真票 joypaas 跑 code-review 配方）跑到 `report` 步 PASS，停 `gate-report` 等人签收（run `01M5A5RVBC2K2GGP1K6ETSJESM`，gate `01M5A86FX2GB614BK2TGF80DV6`）。异步委派全程留痕（delegations/report-1.yaml），五项诚实性检查全过——其中查证闭环了 review 窗口内新出现的 CONTEXT.md/ADR-0009：三重转录扫描证明是用户平行设计会话的产物而非 agent 所写，reviewer「本步未动」声明属实。审查产出 208 行 review.md：9 I* / 7 O* / 3 UNPROVEN，canon §7 命中 T3/T7/T8/T10+T11/F4，五轴齐写；正向记录（SSRF 双重校验、文案泄漏过滤、token 不入日志）与 UNPROVEN（mvn/qodana 未跑、前端 lint 未跑）都如实区分。两个环境坑记录在案：裸 prompt 会被宿主 CLI 内置技能截胡、须 `/idev` 前缀唤起；后台任务 600s 上限须设 `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`。首轮唯一 SUGGEST 是脚本问题而非 prompt 措辞问题（对 #8 是正向信号）。同日修 `coding-scan.sh` 五处管道缺陷：`set -o pipefail` 下 `find | head` 的早期退出把 SIGPIPE（exit 141）传死整脚本——package.json / pom.xml / go.mod 三处探测加 `node_modules -prune`（顺带消除 node_modules 里 package.json 的误报）、package.json 探测删掉无消费者的 `head -5`；Boot 版本回退探测原 `grep -Rqs … | head -1 | grep -q .` 因 `-q` 无输出恒为假（死代码），改为对根 pom 直接 `grep -qs`；checkstyle 探测原 `find | xargs grep -l | head -3 | grep -q .` 在 ≥2 匹配时同样 SIGPIPE→恒假，改为 `find … -exec grep -l … {} +` 落变量判空。修复后 joypaas 全程 exit=0（java=1 level=8 / vue=1（docs/prototype 真实依赖）/ go=0 / ts=0，node_modules 误报消失）、合成用例与 idev 自身均过，syntax-check / refs-check / selfcheck 回归全绿。

- 2026-10-19：补上 Claude Code 的 skill 安装缺口。契约（[agents.md](agents.md)）要求 skill 装在 `~/.claude/skills/idev`，但 `link-idev-aliases.sh` 只建了 `~/.agents` 与 `~/.joycode` 两条别名——而 Claude Code（v2.1.287 实测）只从 `~/.claude/skills` 读用户级 skill，`/idev` 在那边完全不可见。补建别名后：skill 列表 4→5、5 个 agent 全可见、debug 无 skip、`/idev status` 真实唤起并落 trace `20261019-001`。`healthcheck` 标签同步更新；README / SKILL.md / portability-checklist 的别名链补上 `~/.claude`。已知遗留：Claude Code 技能列表超预算（17 个 7832 字符 > 6000，description 被截断），但不影响本次命中——同日实测不打 `/idev`、直接说交付诉求即自动唤起（S1 冷启动、停问等人），trace `20261019-002` 落盘；若后续命中率不稳，调法在用户级 settings 的 `skillListingBudgetFraction`，本仓不动（agents-todo #5 有备注）。

- 2026-10-19：agents-todo #6（P0「签名归一化在自己栈上」）验证完成并销项。用 joypaas 真实服务器日志喂 `failure_signature.py sig`：同错（同线程 `exec-1`、不同时间戳）签名相同，时间戳剥为 `<ts>`；不同错（中文无异常类名的登录失败行 vs `UnknownHostException` 块）签名不同——验收两项均过。边界发现：线程名（`http-nio-8099-exec-N`）不在 VOLATILE 归一化表，同 bug 跨线程分裂签名，「同签名 3 次」红线在服务器日志上难触发。按该待办告诫只记录不修（归一化刻意保守，防止反向把不同 bug 合并）；服务器日志上跑 bounded-fix 时喂同一处线程的行，真需要时再议线程名剥离。

- 2026-10-13：修两处「永远红」的既有检查。`healthcheck` 与 `link-idev-aliases.sh` 都硬性要求 `~/.cursor/skills/idev` 是真目录，而本机拓扑是「git 仓是真源、那里是 symlink」——于是 healthcheck 恒定 FAIL，等于一个没法用的健康检查，新问题会被淹没。「真源」的意图是**只有一份内容**，不是「这个路径必须是真目录」，而版本化的 checkout 是更好的形态。改为接受两种形态，并把「物理根必须等于真源」从字符串比较改成物理路径比较（否则 symlink 必然被读成第二份副本）。`link-idev-aliases.sh` 内部本来就用 `pwd -P` 比对别名，只是前置检查拦住了。另：`selfcheck` 的 trace sink 锁同理已修。

- 2026-10-13：agent 层合并进内核，idev 成为一整套。新增 `agents/`（五个执行者：deliver / coder / reviewer / verifier / ops，按生命周期阶段与模块归并）与 `kind → agent` 登记表 `scripts/lib/kind_agents.py`；`workflow.py next` 原生多打一行 `DELEGATE`，`trace.py` 的 `calls[].kind` 增 `agent`。导体（`/idev` skill）独占签字权与人交互，执行者是 subagent——`is_human()` 的黑名单本就含 `agent/ai/cursor/assistant`，所以这条分工是代码级的，不是约定。新增委派留痕与五项诚实性检查（`delegation.py`）、跨票指标与复盘（`agent-metrics.py` / `agent-review.sh`，只起草不 land）、提效三板斧（`failure_signature.py` 签名归一化让 evidence.md 的三条红线判得出来、`hypothesis.py` 假设台账、coding.md §0 三项交代可机检）。自检三道：`syntax-check.sh` / `agents-check.py` / `agent-smoke.sh`（143 条）。顺手修两处内核既有问题：`selfcheck.sh` 的 trace sink 锁死路径含 `.cursor/skills/idev`，而 `kernel_root()` 用 `resolve()` 必然得到物理路径，该锁在 symlink 拓扑下永远不通过；复制进来的脚本补执行位。`cohesion.md` 加 `agents` 登记并论证它不是第二个顶层 Skill（subagent 名与 skill 名不同命名空间，入口仍只有 `idev`）。


- 2026-10-01：P6 综合缺陷修复。`aligned`/`done` 须人名 `by`；`check-feature` FAIL 打 HINT；`late-lifecycle-smoke`（test→promote→ops→拒伪造 aligned）与 `second-product-smoke` 挂入 healthcheck；audit 软信号 S1 未开 grilling；curator 14d→stale、30d→archive，evolve-review 把超龄 draft 当硬信号；agent-brief 钉死两页冷启动；三模块 SKILL 顶加「本阶段 5 步」；Linux systemd/cron 模板。真实产品票 `done` 仍须人确认（不伪造）。

- 2026-09-30：workflow 补齐三件套。编排语法的代码形态收进 `scripts/lib/workflow_spec.py`（kind 与落点、顶栏 / 参数 / 策略取值、配方与 run 校验），`workflow-check` 改用它，并开始拒绝未知字段、非法 `from` / `policy` / `risk_tier`。新增驱动器 `scripts/workflow.py`（`resolve` / `start` / `next` / `record` / `status` / `abort`）：按配方写 `run.yaml`，给出下一步与落点页，守跳步、签字原话、失败即停，不替 Agent 执行步骤。无票运行落 `product_sink.py workflow-runs`。自检锁住文档 kind 表与代码一致和驱动规则。`workflow-check` 对齐驱动器：产品配方从扩展根读；产品可有多条配方，但一个 id 或别名只许指向一条生效配方；`--run` 核对步骤与所记配方一致。配方校验时停问步骤必须声明 `with.will_write`（`[]` = 将代写: 无）或在 `label` 写 `将代写`，驱动器 `next` 打印该行。

- 2026-09-30：自检与健康检查各用一个本轮独占的临时目录，不再写死 `/tmp/idev-*`，两份并发不互相覆盖；macOS 下带后缀的 `mktemp` 模板去掉。产线在 `AGENTS.md` 或 `issue-tracker.md` 声明 `docs/specs/` 时，规格目录用复数，两份同在时并入复数那份。巡检包、测试设计、`current.md` 的执行页一律指向 `doc_home.py --key`。lite-change 烟测改在本会话 trace 目录找小改记录。配方新增可选 `doc`，`session-context --workflow` 列成 `OPEN`；UI 全量、UI 建设、启停三页执行说明移到产品仓 `.idev/pack/references/`，内核不再点名产品配方 id。

- 2026-09-30：`session-context.py` 等 5 个带 shebang 的 Python 入口补执行位，自检改为凡有 shebang 的脚本都须可执行。`evidence.md` 收尾不再写死 `docs/debt/`，未修的同类缺陷在当前票目录另开 issue。`verify/references/evolve.md` 去掉「模块实验台账」说法，与只有入口台账一致。周审计不再把内核 `state/traces/` 的导体会话记为未绑票。删掉无人调用的兼容壳 `pin-summary-check.sh`。`docs/SKILL.md` 的票目录文件改为指向各模块契约，不再只列五个。`workflow-schema.md` 不再说「不是第五模块」。

- 2026-09-30：健康检查把 lite-change 的 `WARN` 计入 `warns`。path-view 与自进化检查分开，缺进化脚本时仍检查路径视图。`coding.md` 快捷表去掉平台默认值和账本用语，与全表一致。

- 2026-09-29：票路径只认 `doc_home.py`。进入阶段跑 `session-context.py`，S8 同时列出 `s8` 和当前交付阶段；点名的产品用 `--product`。产品仓 trace 必须写 `extensions`。第一次保存放行 `.idev/task/` 与 `.idev/docs/`。缺 `evolve` 不当成试点。内核入口只列内核配方 id。

- 2026-09-29：`from: product` 与启停命令读扩展根的 `workflow-defaults.yaml`。文件或键缺失时 `s8-preflight` BLOCKED。执行模块写票路径时先跑 `doc_home.py`。

- 2026-09-30：产线文档以技能接入交付。写文档、S1 落票、S5 回填和 `docs.backfill` / `docs.changelog` 打开 `docs/SKILL.md`。目录仍认 setup-agents-docs，问句仍认 grilling。`link-companion-skills.sh` 同时挂上这两份同伴技能。

- 2026-09-29：产线文档目录认 setup-agents-docs（Matt Pocock），问句认 grilling。idev 不另定一套。已有这两套时归入 `docs/`，冲突时规范文档优先。还没有时阶段状态写 `.idev/task/`，不新建仓库根的 `docs/`。

- 2026-09-29：文件规范收成一份，写在 `conventions/docs.md`。

- 2026-09-29：`docs/spec/<feature>.md` 与 `docs/specs/<feature>.md` 同时在时，以 `docs/spec/` 为准。另一份里还没有的正文先并入，然后删除 `docs/specs/` 那份。只有旧路径时仍读旧路径。

- 2026-09-29：同一文件同时在规范目录 `docs/` 和 `.idev/` 时，规范文档优先，`.idev` 副本不覆盖它。只存在于一边的票仍留在那边。

- 2026-09-29：产线文档先认 Matt Pocock（setup-agents-docs）和 grilling。两套都在时，新文档和阶段状态按 `docs/prd`、`docs/spec`、`docs/test-case`、`docs/task` 归类。缺一套时改放到 `.idev/docs/` 与 `.idev/task/`。已有的票留在原树。解析在 `scripts/lib/doc_home.py`。

- 2026-09-29：交付仓用自己的 `marker`。共用类页写相对路径 `extension_root`。阶段页可按 `products` 过滤。`check-feature` 跑带阶段声明的产品检查。要不要票只认配方 `needs_ticket`。剥离词表改到各仓 `.idev/strip-tokens.txt`。第一次保存写下空的阶段清单、检查目录和保留 `memory.md` 的 gitignore。
- 2026-09-29：产线 `.idev` 自动整理。热集合留最新 20 条 trace、最近复盘、未消费 inbox、仍打开的提案。被自进化点名满 2 次，或满 3 代，先写入纳入版本库的 `.idev/memory.md`，再删过时原件。真实复盘结束时自动执行。产品 `.gitignore` 需保留 `!.idev/memory.md`。

- 2026-09-29：产品仓文件合同写在 `conventions/docs.md`。密封基线要有一份人读规格，`grill.md` 的字段行只能各有一行，问句必须是 `❓ **Q1** - **标题**:` 配 `➡️`。`review_questions` 保持空。

- 2026-09-29：`sealed: true` 必须有 `grill.md`。`convention` / `frontier` / `shared_understanding` 各自单独成行，正文要有 grilling 的 `❓` 与 `➡️`。散文里提到这两句不算关闭。YAML 里残留的 `status: open` 不会被关闭的 `grill.md` 盖掉。编码评审、checklist 记录、执行残留分三处，清理只删 `.idev/reviews/`。

- 2026-09-29：产线文档目录认 setup-agents-docs（`docs/spec/<feature>.md`，不再用 `docs/specs/`）。未决问题写 `docs/task/<feature>/grill.md`，问法认 grilling。有这份文件时，基线 `sealed: true` 要求 frontier 已空且人已确认共享理解。

- 2026-09-29：产线 `.idev` 的重点是执行阶段产物（trace、复盘、inbox），给定自进化参考。`docs/task/` 仍是交付票。`execution-clean.sh` 默认预览，`--apply` 才删超窗残留；不删提案、不删产线特性和交付票。

- 2026-09-29：阶段读取产线页。有 `marker: idev` 时，`stage-extensions.py` 按 `.idev/extensions.yaml` 列出该阶段要打开的文件；`check-feature` 会跑它。产品自己的检查放在 `.idev/checks/`。第一次保存中间态时写下 `marker`（`evolve: false`），已有标记不改写。启停和 UI 命令改从 `workflow-defaults.yaml` 的 `commands` 读取。自检不再要求某一产线必须有 `coding_root` 或 `ui-automation-build.yaml`。

- 2026-09-29：使用说明写入产线文档默认路径。目录认 setup-agents-docs，未决问题的问句认 grilling，两边同一 `<feature>` 路径。

- 2026-09-29：使用说明写在 `references/guide.md`（目标、架构、产线边界、一次交付与后续会话怎么接）。路由、认票、边界细则仍各认原权威页。

- 2026-09-29：`.idev/` 由 idev 在产线交付中写入。idev 识别产线侧特性，需要保存状态时持久化到该工程 `.idev/`，后续会话再读。人不用先建这个目录。

- 2026-09-29：入口对齐边界。交出口要先有 `marker: idev` 才读 `handoff.yaml`。产品会话的 inbox / 提案草稿进该工程 `.idev/`；内核 `verify/state/` 只留给没有当前产品的导体会话。

- 2026-09-29：边界拆分。产品使用 idev 时先激活内核。内核需要的中间态和产品特性都放在该工程 `.idev/`（`marker.yaml` 的 `marker: idev`）。自净化用这个标识发现 `evolve: pilot` 的仓，复盘计数进内核收据，正文留在该仓。

- 2026-09-29：产线退出内核。当前产品的类页、交出口名单在该仓 `.idev/pack/` 与 `.idev/handoff.yaml`。内核 `handoffs/registry.yaml` 的 `packs` 为空。编排器不再内置产品名。编码表去掉某一产品的类名列。

- 2026-09-29：流水线产物归当前产品。为产品构建的配方在该仓 `.idev/workflows/`，参数在 `.idev/workflow-defaults.yaml`（`from: product`）。idev 只留编排契约、kind 表、`workflow-check`，以及不绑产品布局的能力配方。

- 2026-09-29：去掉未点名产品时的 JoyPaaS 运行默认。`pack-link` / `link-outbound-skills.sh` 没有 `--pack` 且本机没有已选 pilot 时拒绝猜测；磁盘上有产品仓也不再自动选中。JoyPaaS 类页从必读的 `conventions/SKILL.md` 挪到 `packs/joypaas/conventions/`。核心 `workflow-schema` 不再登记 kafka / etcd / zk 目录。

- 2026-09-29：中间文件与内核分界。产品仓会话的 trace / 提案草稿 / 复盘 / inbox 落到该仓 `.idev/`。idev 内核只留工具本身和导体自身会话。提升进内核须人说「提升到内核」，并先过 `scripts/kernel-promote-check.sh`。交付票仍在 `docs/task/`。

- 2026-09-29：入口瘦身（提案 `state/proposals/20260929-p3-entry-slimming.md`）。认票五步与 H1–H6 只留 `invoke.md`；`agent-brief` 不再写少了「最近一条 trace」的四步。决策树只留 `SKILL.md`（补上停问点确认、clean、done 后不改 goal，以及配方命中一句）。速查与 invoke 的第二张场景表改为三行摘要。启停 / UI 生命周期的 `coding_root` 与产品目录改到 `packs/joypaas/workflow-defaults.yaml`，核心配方 `from: pack`，读不到就问人。

- 2026-09-29：可移植性解耦（提案 `state/proposals/20260929-p2-portability-decouple.md`）。去掉 `outbound_registry.py` 写路径的隐式 `joypaas` 兜底：`write_config` 默认 pack 改空、`--pack` 默认空、`_cmd_write_config` 不再兜底 joypaas。无 pilot → 落 generic（不猜产品）；存量 `pilot=joypaas` config 零影响；读路径 `detect_pack` 本就 generic-safe 未改。selfcheck/healthcheck 仍绿。

- 2026-09-29：`SKILL.md` 与 `skill-details.md` 拆分；原硬规则第 4 条中「导体评审 / 再评估禁止输出综合分数或维度打分表」一句已按用户确认删除（提案 `state/proposals/20260929-drop-noscore-compress.md`）；红绿只走 verify、不准第二套测试框架或分数门禁仍有效。
- 2026-09-29：新增 `conventions/canon.md`（T/A/F，Agent 版架构范式）。
- 2026-09-29：非门禁不停规则由 `C1–C6` 改名为 `H1–H6`，避免与 `coding-tables.md` 的代码气味 `C1–C15` 撞号；`references/0011-chat-confirm-signoff.md`（已合并的空壳）删除。
- 2026-09-29：新增 `references/agent-brief.md`、`references/glossary.md`。
