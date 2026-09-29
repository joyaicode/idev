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
| `policy.on_gate` | `stop`（须确认用语） |
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

## kind 登记表（加行，不新开 Skill）

| kind | 落到 | 说明 |
|------|------|------|
| `preflight.inputs` | — | S8 前置可读性探针：缺票/缺路径/缺巡检包 → BLOCKED 并列缺项；不改代码 |
| `route.s4` | conventions | 分析论证 / evidence；改代码再开该类页 |
| `deliver.advance` | deliver | 当前 stage 内推进允许动作；不跳阶段、不跳签字 |
| `deliver.code_pass` | deliver `code` | 编码纪律：§0 匹配 + review.md + 扫描 |
| `review.report` | conventions/coding | 认语言 + 出审查报告；**不改代码**；命中标待签收（C14 例外） |
| `review.fix` | conventions/coding | 只改已签收 `I*`（及显式纳入的 `O*`）；此步恢复当轮必改 |
| `verify.plan` | verify | 起草/调整 plan；请人 accepted（已 accepted 且未改用例 → 跳过，H4） |
| `verify.run` | verify | 跑已 accepted 且勾选的 cases |
| `docs.backfill` | docs/SKILL.md | 契约 / 经验回填（S5）。打开该技能，再按 setup-agents-docs 归类 |
| `docs.changelog` | docs/SKILL.md | 变更说明 / 任务小结。打开该技能后写入解析出的票目录 |
| `ops.classify` | ops | 现象分类 |
| `human.gate` | — | 显式停问；无确认用语不前进；`label` 或 `with.will_write` 必须能还原一行 `将代写: …` + 证明上下文（见 chat-confirm） |
| `shell.confirmed` | — | 仅跑人已在配方或本轮确认的一条命令 |
| `localdev.start` | — | 执行扩展根 `.idev/workflow-defaults.yaml` 的 `commands.start`。`{target}` 换服务名，缺省 `all`。工作目录用 `coding_root` 与 `products.<product>.dir`。没有这些键 → 预检 BLOCKED，不猜命令 |
| `localdev.approval_off` | — | 执行扩展根 `commands.approval_off`。没有该键 → 预检 BLOCKED。不要改产线路由或配置里的审批开关 |
| `localdev.stop` | — | 执行扩展根 `commands.stop`。没有该键 → 预检 BLOCKED。目录与 start 相同 |
| `ui.lifecycle_run` | verify / shell | 全量生命周期 UI：执行扩展根 `commands.lifecycle`（或 plan 勾选的全量 suite）；没有该键 → 预检 BLOCKED。首红即停 |
| `ui.surface_scan` | shell | 扫描 frontend views + locale → `e2e/inventory.json`（`ui-surface-scan.py`） |
| `ui.playbook_sync` | conventions/coding | 按 inventory 建设或进化 wave / helper；写只打本轮资源 |
| `ui.coverage_lock` | shell | `required` token 必须出现在 e2e 且挂 wave（`ui-coverage-check.py`） |
| `ui.fix_deposit` | conventions/docs + evidence | 根因分析 → 修复 → 沉淀 lessons；回填 inventory.wave 后再锁 |
| `ui.clean_pass_loop` | — | 外层：本轮若曾有 FAIL，必须从 lifecycle_run **重头**再跑，直到一次全绿；受 `policy.max_clean_attempts` 限制 |
| `ui.product_batch` | — | 历史 kind（旧 run 仍可校验）；新配方不要用 |
| `git.replace_check` | — | 扫描仓内 `go.mod`：未注释的本地 `replace => ./|../|/Users|绝对路径` → FAIL（须注释掉再提交） |
| `frontend.lint_fix` | conventions/coding | 执行扩展根 `commands.lint_fix`。没有该键 → 预检 BLOCKED。残留 lint = FAIL |
| `java.build` | — | 有 `pom.xml` 则 `mvn … package`；`with.skip_tests: true`（默认）用 `-DskipTests`；`false` 跑单测 |
| `git.sensitive_shield` | — | 提交前屏蔽敏感配置（备份 → 占位符写入工作区）；清单见 workflow-repo-commit |
| `git.sensitive_restore` | — | 提交推送后从备份还原本地敏感配置 |
| `git.commit_push` | — | 整仓 `git add -A` → commit → push 当前分支；须已过 human.gate |

禁止 kind：`auto.seal` / `auto.accepted` / `skip.signoff` / `multi.module.load`。

## run 实例（仓内）

路径：有票时是 `doc_home.py --key task` 解析出的 `<票目录>/workflow/run.yaml`。`needs_ticket: false` 且没给 `--feature` 时，落 `product_sink.py workflow-runs`（产品仓 `.idev/workflow-runs/<id>-<时间>.yaml`；没有当前产品才是内核 `state/workflow-runs/`）。

| 字段 | 约束 |
|------|------|
| `schema_version` | `1` |
| `workflow_id` | 配方 id |
| `recipe` | 起跑时解析到的配方路径 |
| `feature` | kebab-case；无票为 `-` |
| `status` | `pending` \| `running` \| `blocked` \| `done` \| `aborted` |
| `params` | 绑定后的参数 |
| `policy` | 起跑时抄下的配方 `policy` |
| `steps[]` | 抄自配方的 `id` / `kind` / `label` / `with`。没有 `status` 就是还没跑；跑过是 `PASS` \| `FAIL` \| `UNPROVEN` \| `SKIPPED` \| `BLOCKED`，另有 `at`，`evidence` / `note` 可选。`human.gate` 为 `PASS` 时必须有 `signoff: {by, quote, at}`，`by` 是人名，`quote` 以确认用语开头 |
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
$W next --feature <f>                            # NEXT 步骤、OPEN 落点页、COMMAND 取值键
$W record <step> PASS|FAIL|UNPROVEN|SKIPPED|BLOCKED --feature <f> [--evidence <路径>] [--note <原因>]
$W record <gate-step> PASS --feature <f> --by <人名> --quote "<人的确认原话>"
$W status --feature <f>
$W abort --note <原因> --feature <f>
```

它守的规则：缺必填参数或 `from: product` 的键 → BLOCKED，不猜；有票配方无 `deliver.yaml` → BLOCKED；同一张票已有进行中的 run 不另起；只能记当前步骤，想跳过就把当前步骤记 `SKIPPED`；改已记录的步骤必须写 `--note` 并进 `revisions[]`；`FAIL` / `BLOCKED` 让 run 停在 `blocked`，修好后重记同一步；`human.gate` 的 `PASS` 要人名与确认原话（`继续` / `ok` 不算），`SKIPPED` 要 `--evidence` 指向先前的签字。退出码：0 正常，1 用法或配方非法，2 BLOCKED。

## 覆盖

流水线产物属于当前产品，写在 `<repo>/.idev/workflows/<id>.yaml`。一个产品可以有多条配方，一条对应一个场景（如 UI 全量、起停服务、多角色协作），各用自己的 id 与别名。idev 的 `workflows/` 只放编排能力（任何产品都能用的配方，以及导体自己的配方）。同 id 时用产品仓那份。构建出来的流水线不要写回 idev。

## 反馈

试运行（台账 `phase: trial`）结束或 `blocked` 停问时：可写 feedback，落点与 `product_sink.py inbox` 相同（产品工程 `.idev/inbox/`，没有当前产品才是内核 `verify/state/inbox/`，文件名前缀 `wf-`）。不加分数门禁。

## 修正与兼容

1. 编排错了：追加 `revisions[]`，改 `steps` 状态或跳过；旧 evidence 保留。
2. 登记表加 kind：旧配方不认识的 kind → 执行拒跑并 `BLOCKED`，不要默契跳过。
3. 删 kind 或改语义：`schema_version + 1` + 提案；不批量改写历史 run。

## UI 生命周期与知识沉淀

产品目录、前端路径、启停和关审批的命令都在扩展根 `.idev/workflow-defaults.yaml` 的 `commands` 与 `products`（会话仓写了相对路径 `extension_root` 时读那一仓，不要在会话仓再放一份）。没有该文件或没有该键，`s8-preflight` BLOCKED。

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

无确认用语不得把本步标 PASS。

产线配方的别名只写在该仓 `.idev/workflows/<id>.yaml`。内核 kind 表不登记某一条产线的配方名。产品配方顶栏若有 `roles` / `rules`，只是说明，`workflow-check` 不校验。它校验 `needs_ticket` / `aliases` / `risk_tier` / `params` / `policy` / `steps` 与 `human.gate` 的 `将代写`。
