# agent 层(委派契约)

把 workflow 的每个 step 派给一个专职 agent 执行。**不是**新阶段机,**不是**第二套路由。
扩展 = 本页登记表加行 + `scripts/lib/kind_agents.py` 加行(两者不一致则 `agents-check.py` 失败)。

签字权不在这一层。`human.gate` 永远留在导体。

本页是**契约是什么**；**怎么用**见 [agents-playbook.md](agents-playbook.md)。

执行者被直接点名时同样守回合预算。正文在 [SKILL.md](../SKILL.md)「回合预算」。

## skill 与 agent:职责分离,共同合作

本层**同时**用两种机制,各做各不能互相替代的事:

| | **skill**(`/idev`,注入主会话) | **agent**(5 个,独立上下文) |
|---|---|---|
| 身份 | 导体 | 执行者 |
| 装在哪 | `~/.claude/skills/idev`、`~/.cursor/skills/idev` | `~/.claude/agents/*.md`(Cursor 兼容读同一处) |
| 认票 / 认场景 / 路由 S1–S8 | **是** | 否 |
| 读 `DELEGATE` 行、决定派给谁 | **是** | 否 |
| 组委派包 | **是** | 否(它只能收) |
| 在落点页里干活、产出工件 | 否 | **是** |
| 给证据路径 | 验收别人的 | **是**(自己的) |
| 与人交互:请签、停问、唤起 grilling | **是** | **不能** |
| 写 `sealed`/`accepted`/`aligned`/`resolved` | **是**（检查过了就写，不问确认） | **不能** |
| 落委派留痕、写 trace | **是**(每轮一条) | 否(否则一轮多条账) |
| 外层循环(`ui.clean_pass_loop`) | **是** | 否 |

### 为什么必须这样分(四条都是硬依据,不是偏好)

1. **签字权** —— 内核 `workflow_spec.is_human()` 按词表 `AGENT_WORDS` 拒绝 agent / 模型 / 角色名
   (整名与分词都匹配),存在 `people.yaml` 时还须在白名单里。**subagent 用自己的名字签字在代码层就被拒**,不是约定而是实现。
2. **与人交互** —— subagent 看不到本轮检查和未决分叉。
   `sealed`/`accepted`/`aligned` 由导体在检查通过后写入，不问确认。
3. **嵌套限制** —— Cursor 2.5 起 subagent 可以再派 subagent,但「由另一个 subagent 启动的
   subagent 不能再启动」。导体若本身是 subagent,它派出的执行者就到了嵌套末端。
4. **上下文方向相反** —— 执行要**独立**上下文(一个 step 的细节不该污染别的 step);
   路由要**完整**对话(认票、知道检查结果、知道人上一句说了什么)。同一个机制满足不了两者。

所以:**把导体做成 agent,等于把「人机共驾」降级成「无人值守」** —— 而内核 `SKILL.md`
第一句就是「**不是**无人值守自动 seal→promote」。

### 两者之间的接口(只有三样)

| 方向 | 东西 | 契约 |
|---|---|---|
| skill → agent | **委派包** | 固定 9 行,见下节。agent 看不到对话历史,这是它唯一的输入 |
| agent → skill | **回报** | `STATUS` + `EVIDENCE` 必填,另有 `CHECKS` / `SUGGEST` / `GUIDE`,见各 agent 定义 |
| 双向留痕 | **delegation record** | `brief` 与 `report` 都存**原文**,所以能照原样重放 |

接口之外没有别的通道:agent 不读导体的对话,导体不进 agent 的上下文。**这正是它可调试的
原因** —— 出问题时只有三样东西要看,而 `brief-complete` 失败指向导体、其余四项指向 agent。

### 反模式

| 不要 | 为什么 |
|---|---|
| 把导体做成 agent(`~/.claude/agents/idev.md`) | 上面四条,尤其签字权在代码层被拒 |
| 让 agent 自己 `trace.sh append` | 一轮多条账,周审计口径失效 |
| 让 agent 直接问人 | 它问不到;要停问就 `BLOCKED` 回报,由导体停 |
| 把 5 个 agent 也做成 skill | skill 注入当前上下文,5 个一起注入就没有隔离了,等于回到单体 |
| 省掉委派包里的字段"反正 agent 能猜" | 它猜不到。少一项它只能 `BLOCKED(brief)` 回来 |

## 再派一个执行者

再派一个执行者，只在它能带回**上一个在生成时拿不到的信息**。

这一层认的新信息只有四样：

| 新信息 | 落在哪 |
|---|---|
| 跑出来的结果：测试、命令、页面回执 | 当前执行者自己跑，或交给 `idev-verifier` 拿日志 |
| 独立读到的产物和尺 | `idev-reviewer` 读 diff 和扫描输出；复核者读证据文件 |
| 写集不相交的另一片工作 | `fanout.py` 打出 `FANOUT` 才派 |
| 另一个领域的约束，并带证据路径 | `GUIDE`，或一次 `CONSULT` |

能用一条命令拿到的结果，留在当前执行者。多这一跳换不回新信息的，也留在当前执行者。

**模型可以提出完成，批准只发生在检查和证据上。** `STATUS: PASS` 是提议。`delegation.py` 的机检、证据路径、`check-feature` 才是批准。

三种假象打回给原执行者，让它补证据：

| 假象 | 认法 | 打回成 |
|---|---|---|
| 做了一部分就说全部做完 | 证据只覆盖本步的一块 | 补上没覆盖的那块再报 |
| 一条路不通就说整步做不到 | 只试过一条，其余没写 | `BLOCKED`，写明未试路径 |
| 口头办成，闭环没走完 | 没有日志、回执或文件能对上尺 | 没有证据路径的 PASS 不作数 |

分片是互补的工作。另一片的结论不是证据。同一模型在同一份文件上的第二份意见也不是独立证据。写集不相交挡住的是同一文件被盖掉；跨文件把同一个不变量改矛盾，由导体在合并总账时核对。先完成的一片不取消其余。

执行者之间传任务、已确认的事实、产物路径。思考过程留在留痕里。咨询不套娃：这份委派已经是 `咨询:`，再次 `BLOCKED(domain)` 就问人。执行者不派执行者。一轮最多 8 片，其余排队。循环停在检查和证据上。

四块地方分开：

| 区域 | 是什么 | 规则 |
|---|---|---|
| 执行者私有 | 留痕里的 brief / report 原文 | 别人的原文不作证据 |
| 票目录 | 人看的工件 | 只写本步 `WRITES`；分片不改总账 |
| 产品仓 | 源码 | 只改 `include: true` 的路径 |
| 规程 | 本技能与 conventions | 执行者不改 |

知识和流程上的差别，用按需打开的页。权限和写隔离，用现在这五个执行者。拆任务留在导体；执行者收到的是已经拆好的一步。

留在书里、不进这一层：对同一段文本辩论或投票、为文风再拆执行者、无界子执行者、按赛马级联取消、每个执行者一个 worktree、跨组织的 Agent 协议、Agent 市场和社会模拟。

## 这一轮之外到达的事

原则来自 [joyaicode/ai-agent-book 第六章](https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter6.md)。只约束现有的回合、后台命令和浏览器程序。不新做事件总线。

- 常规的新消息，等到当前这条工具返回再一起看。用户说停，就不要开始下一个不可逆动作。已经做完的动作不因此撤销。
- 启动成功不是做完。`queued`、`running` 和「任务已发起」不是成功。没有结果就不编造。
- 迟到的结果对上原来的任务号或请求号。对不上就单独摆出，不并进当前结论。
- 排着的几条更新都生效，不只最后一条。
- 页面上的下一段，从现在的页面重新看起。上一张回执不能代替现在的页面。见 [browser-program.md](browser-program.md)。

留在书里：语音、机器人、虚拟身份、心跳、用另一个模型给事件分类、世界模型。

## 下一轮只接核实过的状态

原则来自 [bojieli/ai-agent-book 第十章](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter10.md)后半：循环停在独立验证，退回要带修复条件，转述会放大错误。只约束现有的重派、复核、配方和分片合并。不新做消息总线、进度文件、乐观锁或级联取消。

下一轮只接这四件：

| 件 | 现成的落点 |
|---|---|
| 原目标 | 委派包里的本步 kind 和 label |
| 已核实的证据 | `prior_failure` 里的证据路径 |
| 失败证据 | `prior_failure` 里未过的检查 |
| 剩余工作 | 这些未过的检查，加上证据没盖住的那一块 |

留痕里的 report 原文、思考过程和文件正文留在留痕里。`workflow.py` 的 `prior_failure` 只拼检查名和证据路径。

没有检查名，也没有 `file:方法名`，就不重派生成者。先让审查者或复核者补上这个条件。生成者拿到条件之后只改那几项。不同意这些条件，写 `BLOCKED(logic)`。

复核对照证据文件和尺。写手的推理不进复核包。`领域约束` 按 `delegation.py` 原样抄进下一份包。下游的 `FACTS` 指向证据文件或命令输出。上游 `GUIDE` 的句子不是来源。

同一模型的第二份意见不是独立证据。合并时各片只交回自己的那一条，并且和派发时的 intent 一致；对不上，`fanout.py merge` 拒绝。各片的 `STATUS` 拼起来不是结论。导体打开证据文件再 `record`。

顺序和并行已经写在配方里。`next` 打出的下一步就是这一跳。缺槽位走 `ASK`。片数上限在 `fanout.py`（一轮最多 8），循环上限在 `react_loop.py`（硬顶 16），无正文回合上限在 `turn-budget.py`。执行者改不了这些数，也不自己再派。同一次失败检查反复出现、又没有新证据路径，走现有的同签名三次和连续两次无变化。

这一步要撤销另一个执行者本轮已经写入的产物，写 `BLOCKED(logic)`，由人定哪一边留下。

独立密钥、步骤级价值树、多数表决留在书里。其余控制面的现有落点见下一节。

## 控制面对上现有部件

原则来自 [bojieli/ai-agent-book 第十章](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter10.md)的数据平面和控制平面。只给现有部件对上号。不新做锁、总线或终止树。

| 书里的做法 | 现有部件 |
|---|---|
| 同一文件不要被后写的盖掉 | 写租约一次一个写者。分片写集相交就 `SERIAL` |
| 跨文件把同一个不变量改矛盾 | `merge` 对照派发时的 intent。assess 给总账记了指纹，分片改了它，`merge` 拒绝 |
| 父级结束时子进程还在 | [会话收尾](../conventions/SKILL.md)只关本轮拉起的进程 |
| 进度和卡住 | `prior_failure`、`LOOP` / `COUNT`、同签名三次、连续两次无变化 |
| 执行者之间的消息 | 委派包、回报、`GUIDE` 原样抄。必读是这一步自己的落点页 |
| 并发到顶 | 默认一轮 4 片，最多 8。多出来的是 `QUEUED`，不打断正在跑的片 |
| 没核实的结果不进权威状态 | 分片文件在 `merge` 之前不是总账 |

没有新的执行结果时，同一上下文里再看一遍，会把已经对的改错。生成者只改点名的失败项。现有检查判不了的，补证据或补这条检查。

审查者的 `CHANGED` 只许 `review.md` 和 `review/shards/`。写了别的路径，`gate-held` 失败。规划留在主会话。执行者都是 `inherit`，不按难度再分模型档。

## 这一层是什么 / 不是什么

| 是 | 不是 |
|---|---|
| 每个 step 多一行「这步谁去做」 | 新的状态机(run 状态机一个字节没改) |
| 专职 prompt + 按职责收紧的工具集 | 无界 fan-out。人闸和写租约一次一步；同一 `group` 且 `writes` 不相交的 verify 步骤同时开。自测、用例设计、用例执行、根因在 `fanout.py` 打出 `FANOUT` 时，同一条消息派多个分片 |
| 独立上下文,互不污染 | 新的签字权(人签字的规则完全不变) |
| 强化「只开一个执行模块」 | 新的验收权威或分数门禁 |

`find_run()` 仍拒绝第二份活跃 run。人闸和 `lease: write` 一次只开一步。配方里同一个 `group`、并且 `writes` 两两不相交的 verify 步骤，从第一个未完成成员到组尾同时开放：`next` 打出 `PARALLEL`，`record` 和 `delegate` 接受组内任一未完成步骤。这是先订死写集再并行，对应 `conventions/canon.md` 对「先订接口再并行」的要求。`references/hitl-risk-tiers.md` 说的不内置并行 PR 阶段机仍然成立：组不是一条并行的合并流水线。

自测、用例设计、用例执行、根因，以及写集还没钉死成一份 `review.md` 的审查，可以在**同一步**里按需拆开。导体先跑 `scripts/fanout.py assess`。少于两片、写集相交、或同一个 Maven 模块没有 `runner.parallel: true`，输出 `SERIAL`，仍然只派一个 agent。用例起草在 `arch.yaml` 里还没有两条 `case_intent` 时，改看 `review.md` 里已签收的 `I*`：签收项就是分片，不必等这一步自己把 intent 写出来。审查按改动的顶层模块分片深读；`coding-scan.sh` 是 `PREP`，导体先跑完。输出 `FANOUT` 时，同一条消息把每个 `SHARD` 派出去（Cursor 用 Task，Claude Code 用 Agent 工具），并且对每一片执行 `workflow.py delegate <step> --shard <id>`。那张验证租约只覆盖该片的 `WRITES`，不覆盖整棵票目录。不要对一个 `FANOUT` 步骤再打一张整票租约。每个委派包多三行：`分片`、`只写`、`范围`。分片只写 `WRITES` 里的路径。`verify/plan.yaml`、`arch.yaml`、`review.md` 和 `hypotheses.yaml` 只由导体的 `fanout.py merge` 改。assess 打出 `MERGE` 且没有 `SHARD` 时，草稿已经齐了，跑 merge，不要再派一个执行者去写这些总账。合并之后这一步只 `record` 一次。每一片的留痕用 `shard:`，文件落在 `delegations/<run_id>/<step>-<shard>-<attempt>.yaml`。另一片的结论不是证据。分片是互补工作，先完成的一片不取消其余。默认一轮 4 片，最多 8 片，其余是 `QUEUED`，合并后再 assess。这仍然是一份 run。`review.fix` 不拆。再派的条件见「再派一个执行者」。

`conventions/evidence.md:4` 已经为此留了口子:「复杂问题可并行多个 Agent,但不能用『另一个 Agent 猜过了』代替证据。」—— 所以每个 agent 的回报都必须带证据路径,**agent 说过不算证据**。

## 登记表(kind → 委派给)

按内核自己的**生命周期阶段与模块**归并,一个 agent 端到端拥有一个阶段,而不是按动作切碎:

<!-- agents-table:begin -->
| agent | 对应阶段 / 模块 | 角色 | 承接 kind |
|---|---|---|---|
| `idev-deliver` | deliver 阶段机 + 产线文档 | 需求 / 架构 / 文档 | `deliver.advance` · `docs.backfill` · `docs.changelog` |
| `idev-coder` | `code` 阶段 + 构建提交 | 开发 | `deliver.code_pass` · `review.fix` · `ui.playbook_sync` · `frontend.lint_fix` · `java.build` · `git.replace_check` · `git.sensitive_shield` · `git.sensitive_restore` · `git.commit_push` |
| `idev-reviewer` | 评审 | 审查(**独立于开发**) | `review.report` |
| `idev-verifier` | verify 模块 + 用例所需环境 | 测试 | `verify.plan` · `verify.run` · `localdev.start` · `localdev.stop` · `localdev.approval_off` · `ui.lifecycle_run` · `ui.surface_scan` · `ui.coverage_lock` |
| `idev-ops` | ops 模块 + S4 论证 | 排障 / 诊断 | `route.s4` · `ops.classify` · `ui.fix_deposit` |
| **导体** | — | 持签字权 | `preflight.inputs` · `human.gate` · `shell.confirmed` · `tool.step` · `ui.clean_pass_loop` · `ui.product_batch` |

30 个 kind:24 个委派,6 个导体保留。每个 kind 的**落点页**见 `registry/kinds.yaml` 的 `page`,本页不复制那一列。

这张表由 `scripts/gen-kinds.py` 从 `registry/kinds.yaml` 生成。加一个 kind 只改那一个文件。
<!-- agents-table:end -->

## 角色能力

五个执行者都站在同一条端到端交付链上。每个角色做三件事：沿链读得懂、本领域按资深标准处理、能指导别的角色。落笔仍按上表的 kind。导体不成为第六个领域专家。产线子 agent 不在这张表里。

**全栈。** 能读上游的尺和下游的后果：基线、方案、实现、红绿、排障结论。改文件和跑本阶段命令只落在自己的 kind 上。这是能力，不另加每步通读门禁。碰到上游尺或下游后果时，读到证据再判断。

**本领域资深。** 处理本领域任务时，以 [experts.md](../deliver/references/experts.md) 该阶段的拒过清单为下限。清单没写到的判断带证据路径。稳定标准写进该角色定义和专家清单的对应行，人确认后才改。一张票里长出的经验进 lessons 候选，确认并复现之后才升成权威。

| 领域 | 执行者 |
|---|---|
| 需求 / 架构 / 文档 | `idev-deliver` |
| 实现 / 构建 / 提交 | `idev-coder` |
| 审查 | `idev-reviewer` |
| 红绿 / 用例所需环境 | `idev-verifier` |
| 论证 / 排障 | `idev-ops` |

**指导别的角色。** 只写本领域约束和证据路径，不写对方的工件，不改密封基线。角色之间不直接对话。`SUGGEST` 仍只说本定义哪一步含糊。

1. **顺手约束。** 做本步时发现别的角色必须遵守的本领域约束，写回报 `GUIDE:`。没有写 `无`。非空时 `delegation.py write` 打出 `HANDOFF`，导体把原文抄进下一角色委派包的 `领域约束:` 行。
2. **卡住再咨询。** 本步做不下去，是因为问题落在另一个执行者的领域：`STATUS: BLOCKED(domain)`，`DOMAIN:` 写上表五个名字之一，不写自己。这不是 `SIGNAL`，不问人。`delegation.py write` 打出 `CONSULT <执行者>`。导体另派该领域角色一次。委派包加 `咨询: <原 step>`，并附上对方回报原文。被咨询的角色只回 `GUIDE` 和 `EVIDENCE`，不写原步骤的工件。咨询回来后，导体把 `GUIDE` 抄进原角色的重派委派包。没有 `BLOCKED(domain)` 时不另开咨询。咨询这一轮若也做不下去，回报 `BLOCKED(logic)`；若仍写 `BLOCKED(domain)`，`write` 打出 `CONSULT none` 并带信号 `consult does not nest`，导体问人，不再套娃。`DOMAIN` 缺了、写了自己、或不是上表五个名字，`write` 打出 `REBRIEF`，导体不猜，按 `BLOCKED(brief)` 打回。

**为什么这样分而不是更细:** 一个阶段里的动作天然同进同退 —— 写完代码就要构建和提交,
跑用例就要先起环境,论证和排障都走 `evidence.md` 的同一套闭环。切得更碎只会让导体
多组几次委派包,而每组一次就多一次 `brief-complete` 出错的机会。

**`review.report` 为什么单列:** `coding.md` §0 明文规定这一步**只记账、不改代码**,
而 `idev-coder` 的硬规则是命中必须当轮改掉。同一个 agent 不能既是实现者又是审查者 ——
这是制度性的分离,不是粒度选择。

## 导体保留的步骤(为什么不委派)

| kind | 原因 |
|---|---|
| `human.gate` | **制度性,不是选择。** `workflow_spec.is_human()` 按词表拒绝 agent / 模型 / 角色名 —— subagent 用自己的名字签字在代码层就被拒。签字权不可下放。 |
| `preflight.inputs` | 纯可读性探针,导体自跑一条命令即可,委派反而多一跳 |
| `shell.confirmed` | 就一条人已确认的命令,组委派包比直接跑更贵 |
| `tool.step` | 已登记工具的一步。`next` 只打出命令，不执行，也不另起运行时 |
| `ui.clean_pass_loop` | 外层整轮循环控制(`policy.max_clean_attempts`),跨多个 step,不属于单步执行 |
| `ui.product_batch` | 历史 kind,新配方不用 |

## 导体回路(委派步两到三条命令)

1. `python3 scripts/workflow.py next --feature <f>` 看 `NEXT` / `OPEN` / `DELEGATE`。`DELEGATE none` 导体自己做;`human.gate` 照旧 `record --by --quote`。
2. `workflow.py step <step> --feature <f>`:交给 agent,要写代码的领写租约,打印机器填好的委派包(`BRIEF` 到 `END BRIEF`),记下开始时间。原样发给 agent。有 `FANOUT` 时仍按分片 `delegate <step> --shard <id>`,不走 `step`。
3. agent 回来,回报原文交给 `workflow.py land <step> --feature <f> --report -`(走 stdin)。它写委派留痕,机检与下面第 5 条相同,然后:
   - kind 要独立复核(`next` 打 `VERIFY`)且回报 PASS:领复核租约,打印复核包(`复核对象` 是写手这次的留痕)。发给复核者,它的回报再 `land` 一次,这次带 `--verified-by` / `--verify-evidence` 记下本步。
   - 不复核的 kind:按回报的 STATUS 直接 record。
   - `SEND BACK`:归 agent 的检查没过,或复核没过。再跑 `step <step>` 拿带 `prior_failure` 的重派包。确认检查器误判、这次仍该过,才在写手那次 `land` 加 `--accept-with-findings "<为什么仍然过>"`,理由带到最后的 record。
   - `STOP`:回报 BLOCKED,或有信号等人答。照 `HANDOFF` / `CONSULT` / `REBRIEF` / `SIGNAL` 做,人答了 `decide`,再把同一份回报 `land` 一次(不会重复写留痕)。

带复核的一步三条命令(`step`、`land`、`land`),其余委派步两条。复核租约要在写手回报被接受之后、复核者开工之前领,租约 30 分钟,所以不能提前到 `step`。规则和 BLOCKED 文案都在下面这些底层命令里,`step` / `land` 只是按顺序调它们;出了问题可以逐条手跑定位。

### 底层命令

1. `python3 scripts/workflow.py next --feature <f>` → 读 `NEXT` / `OPEN` / `DELEGATE` 三行
2. `DELEGATE none` → 导体自己做这一步;`DELEGATE <agent>` → 组委派包(见下)
3. **记下 `started_at`**,然后委派:Claude Code 用 Agent 工具,Cursor 用 `/<agent-name>`。
   没有 `FANOUT` 时一步只派一个 agent。`fanout.py assess` 打出 `FANOUT` 时,同一条消息派这一波的每个分片,不要等前一个回来再派下一个。`PREP` 由导体先跑完,再派分片。
4. 收回报，**记下 `finished_at`**。打开 `EVIDENCE` 指向的文件，再核对 `STATUS`。没有证据路径的 PASS 不作数。
   做了一部分就说全部做完、只试了一条路就说做不到、口头办成但没有对上尺的产物，都打回给原执行者补证据。
   没有检查名或 `file:方法名` 的退回，先补修复条件，不重派生成者。认法在「再派一个执行者」和「下一轮只接核实过的状态」。
5. **落委派留痕**(可调试的前提,见 [agents-evolve.md](agents-evolve.md)):
   ```bash
   python3 scripts/delegation.py write --feature <f>    # brief + report 原文走 stdin
   ```
   它会算五项诚实性检查并写回,`duration_s` 由两个时间戳算出。
   `no-signoff-write` 或 `metrics-shape` 失败 → 退出码 2,**停下来**,不要 record。
   `delegation.py write` 打出的 `HANDOFF` / `CONSULT` / `REBRIEF` 照着做：`HANDOFF` 把 `GUIDE` 原样抄进下一委派包的 `领域约束:`；`CONSULT <agent>` 另派该执行者咨询一次，不问人，不套娃；`REBRIEF` 按 `BLOCKED(brief)` 打回。咨询收回的 `GUIDE` 抄进原角色的重派委派包。
   打印 `SIGNAL …`(回报是 `BLOCKED(logic)`、有 `[承重]` 假设,或 `ARTIFACT: UNKNOWN`)→ **停下来问人**:
   一个问题、选项、你的推荐;人答了用 `workflow.py decide <step> --signal "<原样>"
   --question … --answer … --quote "<人的原话>"` 记进 `decisions.yaml`。
   `继续` / `ok` 不是答案,再问一次。没有信号就不停
6. `workflow.py record <step> <STATUS> --evidence <路径>`。`human.gate` 另须
   `--by <人名> --quote "<确认原话>"`;
   `KIND_VERIFIER` 里的 kind(`next` 打印 `VERIFY …`)PASS 前先派那个 agent 复核。
   Go 引擎下先 `workflow.py delegate <step> --verify` 给它领复核租约。
   它的留痕和写手同一个 `step`、同一个 `kind`,加 `role: verifier`,同样走
   `delegation.py write`:落成 `<step>-<attempt>.verify.yaml`,挂在写手那次 attempt 上,
   **不占新的 attempt**,同一次 attempt 只收一份。不要另起 `fix-verify` 之类的步骤名。
   报告里用整词写上证据路径;再 `record PASS --verified-by <它> --verify-evidence <那条路径>`。
   执行者自己的留痕不算。报告不存在、是空文件、或没有它的留痕引用这条路径,都会 BLOCKED。
   写手最新一份留痕的机检里有归 agent 的 FAIL(`brief-complete` 归导体,不算)时,
   `record PASS` 默认拒绝并列出是哪几项:打回重做(`delegation.py check --feature <f> --step <step>` 看原因);
   确认检查器误判、这次仍该过,才写 `--accept-with-findings "<为什么仍然过>"`,
   这几项和理由写进该步的 `accepted_findings` 与审计。没有 FAIL 时带这个参数会被拒。

两个时间戳是**可选**的 —— 可观测性不该挡住一次正常委派。但缺了就没有耗时视图,
「哪个 agent 慢、哪一步是瓶颈」就答不出来,所以默认记上。

一次 run 的全景(谁做了什么、多久、结果、证据)一条命令看完:

```bash
python3 scripts/delegation.py timeline --feature <f>
```

重派时先取回上次的委派包,别凭记忆重组:

```bash
python3 scripts/delegation.py replay --feature <f> --step <step>
```

它打印可直接重发的委派包(含 `prior_failure`),**但不自动重派** —— 派不派仍是你的决定。

每轮末导体统一写一条 trace(`scripts/trace.sh append`),这一轮派了谁、几次由它从留痕生成(见下)。**各 agent 自己不写 trace**,否则一轮多条账。

## 委派包(固定格式)

subagent **看不到对话历史** —— 委派消息是它唯一的输入。少一项它就得 `BLOCKED` 回来,等于白跑一趟。照抄这个格式:

```
票目录: <python3 $IDEV/scripts/lib/doc_home.py --repo <仓根> --feature <f> --key task 的输出>
仓根: <绝对路径>
feature / stage / risk_tier: <来自 deliver.yaml>
本步: <step.id>  kind=<kind>  label=<label>  with=<with>
attempt: <第几次;>1 时必须附 prior_failure>
必读: <该 kind 的落点页绝对路径>
IDEV_ROOT: <idev 根,默认 ~/.cursor/skills/idev>
artifact: <线上跑的那份产物路径;kind=ops.classify 必填>
禁止: 写 sealed/accepted/aligned/resolved/reopen_baseline/semantic_gate.*;改密封基线正文
回报: 按你定义里的回报格式,STATUS + EVIDENCE 必填
领域约束: <上一角色 GUIDE 的原文；没有就不要这一行>
咨询: <原 step 卡在本领域时才写，并附上对方回报原文；没有就不要这一行>
分片: <fanout 的 SHARD id；没有分片就不要这一行>
只写: <WRITES 里的路径>
范围: <SCOPE 原文>
```

`workflow.py step` 打出的委派包在 `END BRIEF` 前有一行 `PROGRESS closed=<已收口>/<总步数> open=<步骤 id>`。原样带上。已收口含跳过、未证明和失败后已改道，不是通过。

`IDEV_ROOT` 对 `idev-coder` / `idev-verifier` / `idev-ops` 是**必填**:这三个要跑提效脚本
(`scripts/failure_signature.py`、`scripts/hypothesis.py`),定义里以 `$IDEV` 引用它。
不给就等于让它们去空路径执行 —— `delegation.py` 的 `brief-complete` 对这三个强制检查这一项。

合并进 idev 之前这里还有一个独立的 `AGENT_ROOT`(agent 层单独一个仓)。合并后两者是同一个
路径,要求填两遍只是给导体多一次填错的机会,所以只保留 `IDEV_ROOT`。

`kind=ops.classify` 必须带 `artifact`:`idev-ops` 要用 `artifact-match.py` 核对产物与源码
是否同源(回报的 `ARTIFACT:` 行)。**没告诉它产物是哪一份,它只能 `BLOCKED` 回来** ——
`brief-complete` 在这里失败指向导体,省掉一次白跑。

`attempt > 1` 时 `prior_failure` 必填,且别凭记忆重组委派包:用
`delegation.py replay --feature <f> --step <step>` 把上次那份原样取回来。

`git.commit_push` 的委派包还必须写明「`human.gate` 已过」,否则 `idev-coder` 会按它的硬规则 12 拒跑 —— 那是它唯一不可逆的动作。

需要 `product` 的配方:委派包必须点明**恰好一个**产品名,不点名就不委派(内核规则,不是本层新加的)。

## 双边字段对照

一份定义同时服务 Claude Code 和 Cursor,靠的是两边都**静默忽略**不认识的 frontmatter 字段:

| 字段 | Claude Code | Cursor | 本层怎么写 |
|---|---|---|---|
| `name` | 认(必填) | 认 | 必写,须等于文件名 |
| `description` | 认(必填) | 认 | 必写。缺了 Claude Code **静默跳过整个文件** |
| `model` | 认 | 认 | `inherit` |
| `tools` | 认(逗号分隔) | 忽略 | 按职责收紧 |
| `readonly` | 忽略 | 认 | 一律 `false`,原因见下 |
| `is_background` | 忽略 | 认 | `false`(串行委派,要等回报) |

**为什么没有一个 agent 用 `readonly: true`:** Cursor 的 `readonly` 禁止全部写入与改变状态的 shell 命令。而 `review.report` 要写 `review.md`、`verify.plan` 要写 `plan.yaml`、`ops.classify` 要写 `ops.yaml`、`idev-coder` 要跑 `git commit`、`idev-verifier` 要启停本地服务 —— 没有一个步骤是纯读的。误设 `true` 会让这些步骤在 Cursor 下直接跑不通。`agents-check.py` 按 `kind_agents.READONLY_BREAKS` 逐个硬检查。

工具收紧改为落在 Claude Code 的 `tools` 上,并在每个 agent 的硬规则里重述:

| agent | 收紧 |
|---|---|
| `idev-reviewer` | **无 `Edit`** —— 写 `review.md` 用 `Write`,不改已有代码 |
| `idev-ops` | **无 `Edit`** —— 写假设台账、报告、lessons,不改代码 |
| 其余三个 | 全套(要改代码、写票 YAML,或跑改变状态的命令) |

**归并的代价要说清:** `idev-coder` 现在同时拥有 `code` 阶段和 `git.commit_push`,
所以它必须有 `Write`/`Edit`,**无法再像原先那个独立的命令执行者那样收紧到"只跑命令
不改文件"**。那条边界现在只剩 prompt 级约束(硬规则 12–15)加导体验收回报。
换来的是少两次委派、少两次组委派包出错的机会 —— 这是有意的权衡,不是疏漏。

Cursor 侧这些收紧不生效(它忽略 `tools`,subagent 继承父级全部工具),所以**每个 agent 的硬规则里都重述了一遍**边界。这是 prompt 级约束,不是工具级 —— 实际把关仍在导体验收回报那一步。

## trace

派了谁、哪一步、第几次、是不是复核,`trace.py append` 从委派留痕生成 `delegations` 段,条数就是留痕份数,导体不用手记(字段见 [trace.md](trace.md))。想在跳转里看到这一跳,可以另记 `calls[].kind: agent`(已在 `scripts/trace.py` 的 `CALL_KINDS` 里),`target` 写 agent 名,`from: conductor`,`to: agent:<name>`。
知道模型就写 `model`(通常 `inherit`),这一跳的思考压成一行 `thinking`,有计时再写 `duration_s`。
同时在 `decisions` 记一条 `kind: delegate`(`chose: none` 表示导体自己做)。模型这一跳另记 `calls[].kind: model`,不要伪装成 script。
这些字段都可选:缺了不挡委派,有了才能看出谁调了谁、想了什么。字段表在 [trace.md](trace.md)。
**不要记成 `module`** —— 否则一轮里多次委派会被周审计的 `multi-exec-calls` 当成「calls 跨多执行模块」硬报警。
记成 `tool` 不会报警,但分不出「这一轮委派了谁」。

## 自检

```bash
python3 scripts/agents-check.py        # 定义 + 登记表 + 与内核 KINDS 同步
python3 scripts/lib/kind_agents.py --check
python3 scripts/lib/kind_agents.py --kind review.report   # 单看一行
```

`agents-check.py` 校验六项:AGENTS 与 `agents/*.md` 双向齐全 · `name` 等于文件名 · `description` 非空 · 没有 `readonly: true` 却要写文件 · `KIND_AGENTS` 恰好覆盖内核 `KINDS` · 每行的 agent 名已登记。

内核加了新 kind 而这里没加行 → FAIL。这是有意的:和 `selfcheck.sh` 锁住散文 kind 表与 `KINDS` 相等是同一种机械门禁。
