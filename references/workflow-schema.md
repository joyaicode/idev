# workflow 契约（schema_version 1）

快捷指令工作流：把已有 deliver / verify / conventions / ops / docs 能力编成命名配方。  
**不是**新模块，**不是**第二套阶段机。扩展 = 本文件登记表加行。

权威示例：`workflows/dev-selftest.yaml`。run 实例示例见文末。

## 顶栏（配方 `workflows/<id>.yaml`）

| 字段 | 约束 |
|------|------|
| `schema_version` | 整数，当前 `1` |
| `id` | kebab-case，与文件名一致 |
| `needs_ticket` | 缺省要票。只有显式 `needs_ticket: false` 才跳过 `deliver.yaml`。内核不再按配方 id 开白名单 |
| `aliases` | 字符串列表；用户原话**子串**命中 id 或任一别名 → S8。多条命中取**最长**别名。`params.product` 为 required 时：原话必须点明恰好一个产品名，否则不启动、不猜默认产品。不要再写三产品 / 依次UI 这类不点名的别名 |
| `summary` | 一句说明何时用 |
| `doc` | 可选。执行说明页，相对放 `workflows/` 的那一层（产品仓即 `.idev/`，如 `pack/references/<页>.md`）。`session-context.py --workflow <id>` 把它列成 `OPEN`；写了但文件不在 → `workflow-check` 与 `session-context` 失败 |
| `risk_tier` | `P0` \| `P1` \| `P2`；缺省跟票或 `P1` |
| `params` | 变量声明：`name` + `required` + `from`（`user` \| `deliver.yaml` \| `default` \| `product`）。`from: default` 用 `default` 给值。`from: product` 不在配方里写路径：执行时只读扩展根 `.idev/workflow-defaults.yaml` 的键，键名取 `product_key`（点号分层），缺省同 `name`（没有 `extension_root` 时就是本仓）。没有该文件或没有该键 → 预检 BLOCKED，不猜。`product_key` 只配 `from: product` |
| `steps` | 有序步骤 |
| `policy.on_fail` | `stop`（默认）\| `ask` |
| `policy.on_gate` | `stop`（检查没过才停；不解析原话） |
| `policy.on_case_fail` | `stop_fix_continue`：停在首红 → 分析修复 → `ui.fix_deposit` → 从失败点续跑同轮 |
| `policy.require_clean_pass` | `true` 时：同轮曾有 FAIL 则不算交付；必须再开一轮 **从头** lifecycle，直到一轮零 FAIL |
| `policy.max_clean_attempts` | 外层整轮上限，默认 `5`；超限 `blocked` 等人 |
| `roles` / `rules` | 可选，只作说明，不参与校验与驱动 |

顶栏、参数、步骤、`policy` 出现本页没有的字段 → `workflow-check` 失败。


## 步骤 `steps[]`

| 字段 | 约束 |
|------|------|
| `id` | 稳定 slug；修正时不要复用旧 id 装新含义 |
| `kind` | 见 kind 表 |
| `with` | 可选参数（如 `mode: selftest`）。`shell.confirmed` 的 `with.command` 写已确认的那条命令；写 `status` 时读扩展根 `commands.status` |
| `label` | 给人看的短名 |
| `group` | 可选。同一 slug 的连续步骤同时开放。人闸和写租约不能进组。组内每步都要有 `writes` |
| `writes` | 可选，只和 `group` 一起用。票内相对路径，组内两两不相交。`next` 打出 `WRITES`；这一步只写这些文件 |
| `slots` | 可选 slug 列表。配方写了 `params` 时，每个名字必须是其中一个。`next` 发现 `run.params` 里缺了或是空白，先打 `ASK slot a,b`，不打 `DELEGATE` / `COMMAND` / `TOOL`。用 `workflow.py param k=v` 写回当前开放步骤，再看 `next` |
| `branch` | 可选。`pass` / `fail` 指向后面的步骤 id。带 `group` 的步骤不能写，落点若在组里必须是该组第一步。`record` 按刚记下的状态跳过去，中间未完成的步骤记 `SKIPPED`。落点已经记完则拒绝。`FAIL` 同时写 `branch_to`，这一步不再把 run 停成 `blocked` |
| `react` | 可选。这一步是动态关节。没有它，配方行为与以前相同。`human.gate` 和带 `group` 的步骤不能写。`use` / `tool_group` 上不能写，要改成员就用 `adjust` |

组里多于一步未完成时，`next` 先打 `PARALLEL <group>`，再按配方顺序列出每个未完成成员。`record` 和 `delegate` 接受其中任一步。组后面的步骤要等组内全部记完。这一步已经有委派时，回报要有 `CHANGED`；列出 `writes` 之外的路径，`record` 拒绝。没改文件写 `CHANGED: 无`。波次打开时给票目录留一份哈希。之后票里多出来的、且不在这一波任一 `writes` 里的文件，`record` 也拒绝。`workflow.py delegate --open` 一次委派当前波里每一个 agent 步骤。

`react` 把自由循环收成这一步声明的工具候选集。`next` 打出 `REACT candidates=… max_hops=… on_exhaust=… on_fail=…`，并打出可直接照抄的 `REACT_OPEN`、`REACT_ACT`、`REACT_OBSERVE`、`REACT_FINISH`、`REACT_SHOW`。这些行只打印，不执行工具。

| 字段 | 约束 |
|------|------|
| `candidates` | 非空 slug 列表，不可重复。每一个都必须是 `references/tools.yaml` 里的 `id`。新工具先登记 `id` / `summary` / `limit` / `command`，再写进步骤 |
| `max_hops` | 可选整数，1 到 16，缺省 8。用尽走 `on_exhaust`，不再记一跳 |
| `on_exhaust` | `human`（缺省）或 `stop`。只在跳数用尽时走 |
| `on_fail` | `human`（缺省）、`stop` 或 `skip`。只在工具观察失败时走。`skip` 记下这一跳、循环保持 `open`、打出 `SKIP`、退出码 0，不写 inbox，也不自动再试 |

一条配方可以编排别的配方和已登记工具。步骤恰好写 `kind`、`tool`、`tool_group`、`use` 里的一个。`tool` 是 `references/tools.yaml` 里的工具 id，展开后 kind 为 `tool.step`，`next` 打出 `TOOL <command>`，再打 `LIMIT`（这条做不到什么）。有 `inputs` / `outputs` 时再打 `IN` / `OUT`。`TOOL` 行等于登记的 `command`，不改写、不追加参数，也不执行。`inputs` 里缺的名字和 `slots` 一样先 `ASK`。`tool_group` 按组里的顺序展开成多步。`use` 是另一条配方的 id：先查本目录，再查内核 `workflows/`，产品同 id 覆盖内核。展开后的步骤 id 是 `<本步 id>--<被引用步骤 id>`，多层引用就继续加前缀。

`use` 和 `tool_group` 可以带 `adjust`：`skip` 去掉成员，`replace` 只改成员的 `label` / `with` / `react`，`extend` 追加步骤（本身也可以是 `tool`、`tool_group` 或 `use`）。不写 `order` 时，追加接在剩下的成员后面。写了 `order` 就必须把剩下的成员和追加的步骤各列一次。引用自己、或 A 引用 B 再引用 A，都拒绝。嵌套超过 8 层拒绝。既有配方不写这些字段时，展开结果与原来的步骤相同。

循环文件在 `state/react/<feature>--<step>.yaml`（产线是 `.idev/react/`）。`next` 的 `REACT_LOG` 是这个文件的路径；本轮 trace 的顶层 `react:` 抄它，`trace.py append` 把还没出现的跳抄进 `calls`（`kind: tool`，`args` 是登记的命令）。`react_loop.py show --feature <f>` 列出这个 feature 的循环。先打 `COUNT hops=<已用>/<上限>`，再逐跳打出 `HOP`、`WHY`、`RESULT`、`TOOL`、`LIMIT`。已用次数是记录里的跳数。这是回放记录，不重跑命令。脚本只校验和记跳，不调用模型，不改配方。用尽写 inbox 标签 `react-exhausted`。工具失败在 `on_fail` 不是 `skip` 时写 `react-tool-fail`，note 带 step、工具名和观察摘要。同类标签未消费地出现至少两次时，`evolve-review` 把它算作热标签并起草提案，提案里的「要改什么」仍待人填。出口码 3 的 stdout 以 `EXIT human` 或 `EXIT stop` 开头；码 2 是拒绝，文件不变。`start` 把配方文件的 sha256 前 16 位写入 run 的 `recipe_digest`。`next` 打 `DIGEST match`、`DIGEST drift` 或 `DIGEST missing`。drift 只说明文件已变，不改 run 里已经展开的步骤。有票且这一步声明了 `react` 时，`next` 再打 `LOOP absent`，或 `LOOP <status> hops=<已用>/<上限>`。已用和上限从循环文件数出。这行不挡步骤。步骤比对仍按展开后的 id 和 kind。

`verify.plan`、`verify.run`，以及写集不是单独一份 `review.md` 的 `review.report`，`next` 多打一行 `FANOUT_ASSESS`。这是提醒先跑 `scripts/fanout.py assess`，不是新步骤。`SERIAL` 时这一步仍只派一个 agent。`FANOUT` 时同一条消息派每个分片，并对每片 `delegate <step> --shard <id>`；那张验证租约只覆盖该片路径。分片只写 assess 给出的路径。assess 打出 `MERGE` 且没有 `SHARD` 时草稿已经齐了，只跑 `fanout.py merge`，不要再派执行者。合并之后这一步只 `record` 一次。根因用 `--activity rootcause`，不从 `route.s4` 自动打出来。写集已经是 `review.md` 的审查步骤不打这一行。

## kind 登记表（加行，不新开 Skill）

<!-- kinds:begin -->
| kind | 落到 | 说明 |
|------|------|------|
| `preflight.inputs` | — | S8 前置可读性探针：缺票/缺路径/缺巡检包 → BLOCKED 并列缺项；不改代码 |
| `human.gate` | — | 检查通过就 `record PASS`，不另要确认；`label` 或 `with.will_write` 必须能还原一行 `将代写: …` + 证明上下文（见 chat-confirm） |
| `shell.confirmed` | — | 仅跑人已在配方或本轮确认的一条命令 |
| `tool.step` | — | 已登记工具的一步。next 打出 TOOL 命令，不执行 |
| `ui.clean_pass_loop` | — | 外层：本轮若曾有 FAIL，必须从 lifecycle_run **重头**再跑，直到一次全绿；受 `policy.max_clean_attempts` 限制 |
| `ui.product_batch` | — | 历史 kind（旧 run 仍可校验）；新配方不要用 |
| `route.s4` | conventions | 分析论证 / evidence；改代码再开该类页 |
| `deliver.advance` | deliver | 当前 stage 内推进允许动作；不跳阶段、不跳签字 |
| `deliver.code_pass` | deliver `code` | 编码纪律：§0 匹配 + review.md + 扫描 |
| `docs.backfill` | docs/SKILL.md | 契约 / 经验回填（S5）。打开该技能，再按 setup-agents-docs 归类 |
| `docs.changelog` | docs/SKILL.md | 变更说明 / 任务小结。打开该技能后写入解析出的票目录 |
| `review.report` | conventions/coding | 认语言 + 出审查报告；**不改代码**；命中标待签收（C14 例外） |
| `review.fix` | conventions/coding | 交付主路径 with.accept_all_findings 时改全部 I*；code-review 仍只改已签收 I* 与显式纳入的 O*。此步恢复当轮必改 |
| `verify.plan` | verify | 起草/调整 plan；请人 accepted（已 accepted 且未改用例 → 跳过，H4） |
| `verify.run` | verify | 跑已 accepted 且勾选的 cases |
| `ops.classify` | ops | 现象分类 |
| `localdev.start` | — | 执行扩展根 `.idev/workflow-defaults.yaml` 的 `commands.start`。`{target}` 换服务名，缺省 `all`。工作目录用 `coding_root` 与 `products.<product>.dir`。没有这些键 → 预检 BLOCKED，不猜命令 |
| `localdev.stop` | — | 执行扩展根 `commands.stop`。没有该键 → 预检 BLOCKED。目录与 start 相同 |
| `localdev.approval_off` | — | 执行扩展根 `commands.approval_off`。没有该键 → 预检 BLOCKED。不要改产线路由或配置里的审批开关 |
| `ui.lifecycle_run` | verify / shell | 全量生命周期 UI：执行扩展根 `commands.lifecycle`（或 plan 勾选的全量 suite）；没有该键 → 预检 BLOCKED。首红即停 |
| `ui.surface_scan` | shell | 扫描 frontend views + locale → `e2e/inventory.json`（`ui-surface-scan.py`） |
| `ui.coverage_lock` | shell | `required` token 必须出现在 e2e 且挂 wave（`ui-coverage-check.py`） |
| `ui.playbook_sync` | conventions/coding | 按 inventory 建设或进化 wave / helper；写只打本轮资源 |
| `ui.fix_deposit` | conventions/docs + evidence | 根因分析 → 修复 → 沉淀 lessons；回填 inventory.wave 后再锁 |
| `frontend.lint_fix` | conventions/coding | 执行扩展根 `commands.lint_fix`。没有该键 → 预检 BLOCKED。残留 lint = FAIL |
| `java.build` | — | 有 `pom.xml` 则 `mvn … package`；`with.skip_tests: true`（默认）用 `-DskipTests`；`false` 跑单测 |
| `git.replace_check` | — | 扫描仓内 `go.mod`：未注释的本地 `replace => ./|../|/Users|绝对路径` → FAIL（须注释掉再提交） |
| `git.sensitive_shield` | — | 提交前屏蔽敏感配置（备份 → 占位符写入工作区）；清单见 workflow-repo-commit |
| `git.sensitive_restore` | — | 提交推送后从备份还原本地敏感配置 |
| `git.commit_push` | — | 整仓 `git add -A` → commit → push 当前分支；须已过 human.gate |

禁止 kind：`auto.seal` / `auto.accepted` / `skip.signoff` / `multi.module.load`。
<!-- kinds:end -->

## run 实例（仓内）

路径：有票时是 `doc_home.py --key task` 解析出的 `<票目录>/workflow/run.yaml`。`needs_ticket: false` 且没给 `--feature` 时，落 `product_sink.py workflow-runs`（产品仓 `.idev/workflow-runs/<id>-<时间>.yaml`；没有当前产品才是内核 `state/workflow-runs/`）。

| 字段 | 约束 |
|------|------|
| `schema_version` | `1` |
| `workflow_id` | 配方 id |
| `recipe` | 起跑时解析到的配方路径 |
| `recipe_digest` | 起跑时配方文件 sha256 的前 16 位。`next` 用来对照，不作为门禁 |
| `feature` | kebab-case；无票为 `-` |
| `status` | `pending` \| `running` \| `blocked` \| `done` \| `aborted` |
| `params` | 绑定后的参数 |
| `policy` | 起跑时抄下的配方 `policy` |
| `steps[]` | 起跑时展开后的 `id` / `kind` / `label` / `with` / `group` / `writes` / `react` / `tool` / `slots` / `branch`。没有 `status` 就是还没跑；跑过是 `PASS` \| `FAIL` \| `UNPROVEN` \| `SKIPPED` \| `BLOCKED` \| `AUTO`，另有 `at`，`evidence` / `note` 可选。`human.gate` 为 `PASS` 时必须有 `signoff: {by, quote, at}`，`by` 若写了必须是人名，`quote` 可空；疑问、否定、犹豫拒收。为 `AUTO` 时只有 `evidence`（它跑出的检查输出路径）和 `auto: {stage, log, exit, sha256}`，没有 `signoff`。独立复核过的步骤另有 `verification: {by, evidence, at}` |
| `revisions[]` | 只追加；改已记录的步骤时写 `step` 与 `旧 -> 新: 原因` |
| `feedback` | `status`：`pending` \| `filed`；试运行 tag 拷到 verify inbox |

报告：同目录 `report.md`（无票运行是同名 `.md`），每次记录后重写。

## 编排工具

| 工具 | 管什么 |
|------|--------|
| `scripts/lib/workflow_spec.py` | 本页语法的代码形态：kind 与落点、顶栏 / 参数 / 策略 / 状态取值、配方与 run 的校验。本页 kind 表与它不一致时自检失败 |
| `scripts/workflow-check.sh` | 校验内核与当前产品全部配方（产品配方读扩展根 `.idev/workflows/`，与 `workflow.py` 同源）、入口发现词。一个 id 或别名只能指向一条生效配方（产品同 id 覆盖内核不算冲突）。`workflow-check.py --run <run.yaml>` 校验实例，记了 `recipe` 时步骤须与该配方一致 |
| `scripts/s8-preflight.sh` | 起跑前探票、配方、巡检包、`workflow-defaults.yaml` 与阶段页 |
| `scripts/workflow.py` | 按配方驱动一次 run，只管 `run.yaml`，不替 Agent 执行步骤 |

`workflow.py` 用法（在产品仓内执行，或加 `--repo`）：

```bash
W=~/.cursor/skills/idev/scripts/workflow.py
$W resolve <id>                                  # 产品扩展根优先，其次内核
$W start <id> --feature <f> [--param k=v]        # 校验配方、绑参数、写 run.yaml，打印第一步
$W next --feature <f>                            # NEXT 步骤、OPEN 落点页、COMMAND 取值键；有摘要时先打 DIGEST；末尾打 PROGRESS closed=<已收口>/<总步数> open=<步骤 id>
$W param k=v --feature <f>                       # 把缺的槽位写回当前开放步骤，再打 next
$W record <step> PASS|FAIL|UNPROVEN|SKIPPED|BLOCKED --feature <f> [--evidence <路径>] [--note <原因>]
$W step <step> --feature <f>                     # 委派步的入口：交给 agent（含写租约），打印机器填好的委派包
$W land <step> --feature <f> --report -          # 收 agent 回报：写留痕；要复核就领复核租约、打印复核包，否则 record
$W delegate <step> --feature <f>                 # 委派前标记执行者；写代码的步骤同时领写租约
$W ask <gate-step> --feature <f>                 # 可选；终端 idev gate approve 不是必经
$W record <gate-step> PASS --feature <f>   # 检查过了就记录，不另要确认
$W record <gate-step> AUTO --feature <f>        # 仅当档位在 with.auto_tiers 里；自己跑该闸的检查
$W record <step> PASS --feature <f> --evidence <路径> --verified-by <复核 agent> --verify-evidence <复核报告>
$W delegate <step> --verify --feature <f>        # 写手回来后给复核者领复核租约（Go 引擎）
$W record <step> PASS --feature <f> --evidence <路径> --accept-with-findings "<为什么仍然过>"   # 留痕机检有 FAIL 时
$W decide <step> --feature <f> --signal "<信号原样>" --question <问题> --answer <结论> --quote "<人的原话>" [--options …] [--recommend …]
$W status --feature <f>
$W abort --note <原因> --feature <f>
```

它守的规则：缺必填参数或 `from: product` 的键 → BLOCKED，不猜；有票配方无 `deliver.yaml` → BLOCKED；同一张票已有进行中的 run 不另起；只能记当前步骤，想跳过就把当前步骤记 `SKIPPED`；改已记录的步骤必须写 `--note` 并进 `revisions[]`；`FAIL` / `BLOCKED` 让 run 停在 `blocked`，修好后重记同一步；`human.gate` 的 `PASS` 直接记录，不解析原话。`ask` 和 `record` 不在写 `run.yaml` 的锁里调用 `idev`。问已经在库里、编号却没写进 run 时，再次 `ask` 把那个 pending 编号写回去，不开第二问；编号已在且仍 pending 时拒绝再开。已经批准且内容没变时直接去 `record`，不再另开一问。`start` 在同一把锁里判断并写入：已有 `running` / `blocked` 的 run 就拒绝（没有 `steps` 也算进行中），读不出来或不是 mapping 的 `run.yaml` 不覆盖，两个 start 不会各写一份再互相覆盖。`report.md` 在 `run.yaml` 写成功之后才更新。同一 attempt 的同一个 signal 只接受一次 `decide`。没有 `--by` / `--quote` 时，`record` 才读回终端批准：状态非 approved、内容在批准后改过、签名验不过都会 BLOCKED。`--quote` 是 `继续` / `ok` 不算确认。gate 的类型取 `with.gate_type`（`accepted_req|accepted_arch|accepted_plan|aligned|resolved|step_confirm`），没写时 `will_write` 提到 `plan.yaml` 的算 `accepted_plan`，其余算 `step_confirm`；摘要覆盖 `with.subject` 列出的票内文件（`accepted_plan` 默认取 `verify/plan.yaml`），没有文件时覆盖问题本身。registry 里 `lease: write` 的 kind（Go 引擎下）要先 `delegate`：它把 run 的步骤状态投影进 `~/.idev` 的 SQLite，按 `arch.yaml` 里 `include: true` 的路径领写租约，同一张票（按票目录绝对路径区分，两个 checkout 的同名票互不相干）同时只有一个写者，fencing 只升不降；持有期间 token 记在 `run.yaml` 的 `steps[].lease`，释放后只留编号、fencing、路径和 `released_at`。没有租约记 `PASS` → BLOCKED；执行者回报的 `CHANGED` 有租约外的路径 → BLOCKED；`record` 收口和 `abort` 都会释放租约，没释放的到期自动回收（默认 2 小时）。`SKIPPED` 要 `--evidence` 指向先前的签字，或指向表明本闸无可签内容的文件（如没有 `I*` 的 `review.md`）。`AUTO` 只给声明了 `with.auto_tiers` 且票的 `risk_tier` 在其中的 `human.gate`，不得带 `--by` / `--quote`。它在锁外自己跑该闸的检查（`accepted_plan` 闸跑 `check-feature verify-plan`），输出写进票的 `verify/plan-check.log`；退出码非 0、没有 `0 FAIL` 行、有 `SIGNAL` 行，或 `verify.plan` 步最新留痕里的信号还没 `decide`，都 BLOCKED。事先存好的文件不读，会被覆盖；`--evidence` 可省，写了必须就是这个文件。`KIND_VERIFIER` 登记了复核者的 kind，`PASS` 须 `--verified-by` 正是那个 agent，且 `--verify-evidence` 指向一份已经写好的非空报告；票的 `delegations/` 里还要有该 agent 自己的留痕，正文用整词引用这条路径。执行者自己的留痕不算。两条都是该 agent 名下的文件，机器核对的是「报告在、留痕对得上」，不是另一台进程的签名。复核者的留痕与写手同 `step`、同 `kind`，带 `role: verifier`，`delegation.py write` 把它落成 `<step>-<attempt>.verify.yaml`，挂在写手那次 attempt 上、不占新号，同一次 attempt 只收一份；Go 引擎下它另记一条 `verification.recorded` 审计，写手与复核者是同一 agent 时拒收。有代理执行者的步骤（`DELEGATE` 不是 `none`），写手最新一份留痕的机检里有归 agent 的 FAIL（`brief-complete` 归导体，不计）时，`PASS` → BLOCKED 并列出各项；`--accept-with-findings "<理由>"` 放行，各项与理由写进该步的 `accepted_findings`，Go 引擎下另记 `delegation.accepted` 审计；没有 FAIL 却带这个参数、或对非 `PASS` 带它，都 BLOCKED。该步最新委派留痕里有信号（`BLOCKED(logic)`、`[承重]` 假设、`ARTIFACT: UNKNOWN`）而 `decisions.yaml` 没有对应答复时，`PASS` → BLOCKED；`decide` 只接受留痕里真有的信号，`--quote` 是 `继续` / `ok` 这类不选任何东西的词时拒收。决策不是签字：它记人对一个问题的回答，不授权写签字字段。Go 写 `run.yaml` 时比对写前写后，记录变了的每一步各记一条审计：首次落定或改了状态记 `step.recorded`，状态不变而证据、签字、复核或时间变了记 `step.amended`，`SKIPPED` 记 `step.skipped`，状态被清掉记 `step.retried`；detail 带结论、原状态、证据、执行者、租约编号、委派编号、复核者、签字人和这次 `run.yaml` 的 sha256。首次写入记 `run.started`，转 `done` / `aborted` 记 `run.completed` / `run.aborted`；只领租约或只改 feedback 的写入不记步骤事件。`idev audit export --run <run_id>` 按序列出。`step` 与 `land` 只把上面这些命令按顺序串起来，各条的规则与 BLOCKED 文案不变：`step` 走 `delegate`，委派包从 run、票和 registry 取（`票目录`、`仓根`、`stage`、`risk_tier`、`必读` 是该 kind 的落点页、`IDEV_ROOT`、`with`、`只写`、上一角色的 `GUIDE`；重派时带上次的 `prior_failure`），存进 `<run 目录>/briefs/<run_id>--<step>.yaml` 并记下开始时间；`land` 用它和回报原文拼出留痕交给 `delegation.py write`。写手回报有归 agent 的 FAIL 打 `SEND BACK`、不复核也不 record；回报 `BLOCKED` 或有没答的信号打 `STOP`；写手 PASS 且 kind 在 `KIND_VERIFIER` 里，走 `delegate --verify` 并打印复核包（`复核对象` 是写手这次的留痕），复核者的回报再 `land` 一次才 record。复核租约跟在被接受的写手回报之后、复核者开工之前领，所以不提前到 `step`。同一份回报重复 `land` 不另写留痕；用过的委派包换了新回报 → BLOCKED，先 `step` 拿重派包。退出码：0 正常，1 用法或配方非法、或 `land` 打回（`SEND BACK` / `STOP`），2 BLOCKED。

## 覆盖

流水线产物属于当前产品，写在 `<repo>/.idev/workflows/<id>.yaml`。一个产品可以有多条配方，一条对应一个场景（如 UI 全量、起停服务、多角色协作），各用自己的 id 与别名。idev 的 `workflows/` 只放编排能力（任何产品都能用的配方，以及导体自己的配方）。同 id 时用产品仓那份。构建出来的流水线不要写回 idev。

## 反馈

试运行（台账 `phase: trial`）结束或 `blocked` 停问时：可写 feedback，落点与 `product_sink.py inbox` 相同（产品工程 `.idev/inbox/`，没有当前产品才是内核 `verify/state/inbox/`，文件名前缀 `wf-`）。不加分数门禁。

## 修正与兼容

1. 编排错了：追加 `revisions[]`，改 `steps` 状态或跳过；旧 evidence 保留。
2. 登记表加 kind：旧配方不认识的 kind → 执行拒跑并 `BLOCKED`，不要默契跳过。
3. 删 kind 或改语义：`schema_version + 1` + 提案；不批量改写历史 run。

## UI 生命周期与知识沉淀

扩展根的 `marker.yaml`、`extensions.yaml`、`workflow-defaults.yaml` 每个键的解释和示例只在 [extension-config.md](extension-config.md)。会话仓写了 `extension_root` 时读那一仓，不要再放一份。没有文件或没有配方要的键，`s8-preflight` BLOCKED。

`ui.fix_deposit` 落盘（禁止 `.scratch/`）：

1. 教训写 `<票目录>/lessons/<YYYYMMDD>-<case-slug>.md`：现象、根因证据、修复、防再发。`<票目录>` 只认 `doc_home.py --key task`
2. 索引追加：`<票目录>/lessons/README.md`
3. 回填 `e2e/inventory.json` 的 `wave` / `required`，再跑 `ui.coverage_lock`
4. 可复用且已剔除产品专有逻辑 → idev 核心（evidence / coding / docs）。仍绑协议 / 仓 / 服务码 → 该产品 pack 或产品仓，不要进核心。

用到 `ui.*` / `localdev.*` 的配方属于产线，执行说明由该配方的 `doc` 指向产品仓 `.idev/pack/`，不放进内核。

整仓提交推送见 [workflow-repo-commit.md](workflow-repo-commit.md)（`repo-commit-push`）。

整仓代码审查见 [workflow-code-review.md](workflow-code-review.md)（`code-review`）。

## 签字不可跳过（生命周期修复）

1. 配方步骤若对应 deliver/ops 停问点，**必须**保留签字类 step（`kind` 含 signoff / 人签 / chat-confirm）；禁止用 `auto.seal`、`auto.accepted`、`skip.signoff` 或删步绕过。
2. S8 只加速允许动作，不改变密封基线尺；跳过签字 = 配方非法，导体拒跑。
3. `deliver.advance` 仍「不跳阶段、不跳签字」。


## human.gate 字段（硬）

| 字段 | 要求 |
|------|------|
| `label` | 须含或能生成 `将代写: <字段>` |
| `with.will_write` | 可选；字符串数组，优先用于拼 `将代写`。`[]` 表示 `将代写: 无`（只停问、不写字段） |
| `with.proof` | 可选；短证明上下文（门禁结果 / PASS 计数） |
| `with.auto_tiers` | 可选；`risk_tier` 取值的非空子集，只能写在有机检的闸上（目前只有 `accepted_plan`），写在别的闸上配方非法。票在这些档位时，`record AUTO` 自己跑的检查全过且无信号即可记 `AUTO`，不停问。不写 = 每档都要人签 |

`with.will_write` 与 `label` 里的 `将代写` 至少有一个，都没有 → `workflow-check` 失败；`will_write` 不是字符串列表或含空串也失败。`workflow.py next` 在停问步骤直接打印由它拼出的 `将代写:` 行。

检查没过不得把本步标 PASS。不另要确认用语。

产线配方的别名只写在该仓 `.idev/workflows/<id>.yaml`。内核 kind 表不登记某一条产线的配方名。产品配方顶栏若有 `roles` / `rules`，只是说明，`workflow-check` 不校验。它校验 `needs_ticket` / `aliases` / `risk_tier` / `params` / `policy` / `steps` 与 `human.gate` 的 `将代写`。
