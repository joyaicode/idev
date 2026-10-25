# 代码审查（执行说明）

配方：`workflows/code-review.yaml`。场景 **S8**。

## 触发

`代码审查` / `规范审查` / `审查当前仓` / `code-review`。档 **P1**。

当前工作区 = 被审查仓。不在 idev 里开交付阶段机。  
「综合评审 skill / 导体 / idev」走 **S4**，不要用本配方。

## 参数

| 名 | 必填 | 说明 |
|----|------|------|
| `feature` | 否 | 默认 `code-review`。工件落在 `doc_home.py --repo <被审查仓> --feature <feature> --key task` 给出的目录。配方 `needs_ticket: false`，不要求 `deliver.yaml` |

## 步骤顺序（硬）

```
review.report → human.gate → verify.plan → human.gate → review.fix → verify.run
```

无正式发现 `I*`（空报告，或只有 `O*` / UNPROVEN）：`report` 之后其余步 **SKIPPED**，`run.status=done`。无停问点不请签。

任一步 FAIL → 停。禁止 `auto.seal` / `auto.accepted` / `skip.signoff`。

## 范围

整仓机械扫描。种类：Java / Vue / JS（有 TS 再加）+ `yml` / `yaml` / `xml`。

排除：`target` / `node_modules` / `dist` / `.git` / `generatedverify`。不做 Markdown、不做 `.mustache`。

深度：先 `coding-scan.sh` 认语言并打开对应规约；机械扫描全仓；**只深读命中文件**。未打开的文件在报告写 **UNPROVEN**，不准写成已审。

报告步**只读**：可跑 `coding-scan.sh`（只跑随 idev 带上的插件，不安装工具链）；**不准**执行 `commands.lint_fix`（会改文件）。没有这个键就问人。`problems` 或 `lang` 退出码 2 是 `UNPROVEN`，不要写成已扫干净。

再次跑：覆盖 `review.md`，`workflow/run.yaml` 开新一轮；旧 evidence 只留 git 历史。

## 1. `review.report`

1. 跑 `bash ~/.cursor/skills/idev/scripts/coding-scan.sh <repo根>`。输出里 `java hygiene` 的每一条 **blocking** `file:line`，以及同一次扫描末尾 `problems` 和 `lang` 插件的每一条 `file:line`，先写成 `I*`（分片则写进该模块的 `### FINDING`，位置含 `file:line`），再写总则、五轴、内聚。`note` 不打回。`problems` 或 `lang` 退出码不是 0，或输出 `UNPROVEN`，这一步不算扫完。这两层不安装 IntelliJ、JDK、ruff、golangci-lint、shellcheck、eslint 或 Node。漏记 blocking 时 `delegation.py` 的 `java-hygiene` 打回这份报告。范围是相对 merge-base 的 diff 加工作区，不是整仓存量；整仓另跑 `java_hygiene.py --all`。`next` 若打出 `FANOUT_ASSESS report`，先跑那条 assess。`FANOUT` 时导体先跑扫描（`PREP`），再按模块各派一个审查者，每片只写 `review/shards/<模块>.md`，用 `### FINDING` / `### UNPROVEN`，不写 `review.md`、不编 `I*`。每片 `workflow.py delegate report --shard <id>`。全部回来后 `fanout.py merge`，再把这一步 `record` 一次。改动的源码模块少于两个时仍是一个审查者。写集已经钉成一份 `review.md` 的步骤不走这条分片。
2. 跑 `python3 ~/.cursor/skills/idev/scripts/session-context.py --repo <repo根> --feature <feature> --scenario S8 --stage code`。点了产品名就加 `--product`。打开每一行 `OPEN`，并把路径写入 trace 的 `extensions`（没有页就写 `extensions: []`）与 `opened`。没有 `OPEN` 就不打开产线 pack。
3. 打开 [coding.md](../conventions/coding.md) §0 与文首**底线**、**规范总则**、[coding-tables.md](../conventions/coding-tables.md) §1/§2/§3 与 §2.4（含变更级粗筛）；按栈打开 `java.md` 与 `code-review-skill` 指南。底线先判：把问题做复杂、关键路径没有异常处理或降级、无依据或绕路、平铺直叙、只有 get/set 的哑对象、说不出换来什么的文件和行，写成 `I*`，落既有 `T#`/`C#`/`F#`。
4. 写票目录里的 `review.md`（`doc_home.py --key task`）：
   - **正式发现 `I1`…**：`P#` / `C#` / `R#`，或 `landing` / `identity` / `config` 已有条文。每条：位置（**file:方法名 锚点为主，行号只作辅助**——review 与 fix 之间同一文件可能被平行改动，行号会漂移）、根据、修复建议。进默认修复清单。
   - **意见 `O1`…**：五轴对不上编号的观感。入库，**不进**默认清单。
   - **UNPROVEN**：未打开的范围内文件（可按目录汇总，不必列每一个）。
5. 不另起 `F#`。本步不改业务代码。命中标「待签收」（C14 例外，见 coding.md）。

写 `workflow/run.yaml` + `report.md`。本步结束若无 `I*` → 其余步 SKIPPED，结束。

## 2. `human.gate`（签收清单）

默认修全部 `I*`。人可划掉若干 `I*`；未划掉的才修。  
要修意见须显式写「纳入 O*」。无确认用语不前进。

## 3. `verify.plan`（`mode=selftest`）

只为已签收项起草 `doc_home.py --key plan` 给出的 `plan.yaml`。`FANOUT_ASSESS plan` 在还没有两条 `case_intent` 时按已签收的 `I*` 分片：每片只写 `verify/shards/plan-<I*>.yaml` 和 `verify/checks/<I*>/`，`delegate plan --shard <I*>`。导体 `merge` 后才有一份 `plan.yaml` 和 `arch.yaml` 的 include。少于两条已签收项时仍是一个验证者。  
无 `deliver.yaml`：`goal` / `non_goal` 人写或从已签收 `I*` 复述；case 不挂 `slice_id` / `baseline_item_id`。  
起草或改了 `cases[]` 后跑 `check-feature.sh <feature> verify-plan`。没有 `baseline.yaml`、且当前 `workflow/run.yaml` 指向的配方 `needs_ticket: false` 时，这道门禁不要求 `sealed`，`stage-gate --stage test` 也不要求 case 挂 `baseline_item_id`。已有 `baseline.yaml` 时仍要求密封。FAIL 不准请签。

## 4. `human.gate`（accepted plan）

已 accepted 且本轮未改用例 → 跳过（H4）。

## 5. `review.fix`

只改已签收 `I*`（及显式纳入的 `O*`）点名的文件。此步恢复 C14：这些项当轮改掉，只记账不算过。  
交付主路径（`lite-change`）的 `review.fix` 带 `accept_all_findings: true`，在实现审核前改全部 `I*`，不另设签收闸。本配方没有这个字段。  
可跑 `lint-fix` / 扫描。更新 `review.md` 纠正栏。

## 6. `verify.run`

只跑 `accepted == true` 的 cases。回写 status + evidence。写 `verify/report.md`。

## 不做

- 不建 `deliver.yaml` / 不走 req-review 阶段机
- 不把意见默认当成必须改
- 不假装整仓逐文件已读
- 不自动 `promote`、不改其它票的密封基线
