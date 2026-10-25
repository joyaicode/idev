# 请人签字前必须打印的检查（校对后）

先跑 `bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> <stage>`，再贴本表。  
脚本或本表有一条 `FAIL` 不准 `sealed` / `accepted` / `aligned` / `resolved`，也不准记 `AUTO`。哪些点签、哪些点 `AUTO`：[chat-confirm-signoff.md](../../references/chat-confirm-signoff.md)。  
脚本锁：`slice.must` 原文、`semantic_gate` 已记录、`plan.goal` 复制基线、test 维表全覆盖。票面 YAML 用 PyYAML 读，**结构绿 ≠ 口号可证伪**；口号 / non_goal 是否盖住顺手做大，仍须人看 [semantic-gate.md](semantic-gate.md)。`check-feature` 不做法伪判断。`by:` 必须是人名。无确认用语 Agent 不填；有确认用语按 [chat-confirm-signoff.md](../../references/chat-confirm-signoff.md) 代写当前停问点（含 `semantic_gate`）。  
`req` 及之后须有非空 `deliver-eval.md`。`test` 档 `plan.mode` 必须是 `test`。

## 真源

- 尺：`<票目录>/baseline.yaml`（`sealed: true`）。同时要有一份人读规格和 `grill.md`（问句行见 [docs/SKILL.md](../../docs/SKILL.md)）。规格路径只认 `doc_home.py --key spec`；`spec/` 与 `specs/` 同时在时，以它输出的那份为准并清掉另一份（仓声明 `docs/specs/` 时是复数）。
- 人读规格只许复述基线。冲突 → 改规格，不改基线（除非人 reopen）。
- verify `plan.yaml` 的 `goal` / `non_goal` 必须与基线原文一致（复制，不准另写）。

## 语义门（每人签前）

- [ ] 已打印 [semantic-gate.md](semantic-gate.md) 对应阶段，由人逐项判（Agent 不得自己判勾；人回确认用语后才代写 `semantic_gate`）
- [ ] `req` 及之后：`check-feature` 已过 slice.must 原文锁 + 上一阶段 `semantic_gate`

## req-review

- [ ] 有 `goal`、`non_goal`、至少一条可证伪 `items[]`
- [ ] `goal` 有可量化 SMART 指标；验收无主观词、可红绿切换（[req-quality.md](req-quality.md) §1/§3）
- [ ] `review_questions` 与 `objections` 都是空列表；未决问句在 `grill.md`
- [ ] 与 CONTEXT / 点名的 ADR 冲突已写成问题
- [ ] `sealed` 仍是 false（等人写 YAML 或回复确认用语）

## req

- [ ] `baseline_revision` == 密封本 revision
- [ ] 每个 item 至少一条 slice；每条 slice 恰好一个 `baseline_item_id`
- [ ] 每条 slice.must 与对应 item 原文一致（脚本）；没有基线里不存在的义务
- [ ] 每条 slice 过 INVEST；故事 > 8 点已拆（[req-quality.md](req-quality.md) §2/§4）
- [ ] 每个档位：基线未密封时 `check-feature req` 照查基线就绪与 frontier 已空，本阶段末一次签 `sealed` + `req.accepted`。`shared_understanding` 随这次确认写入

## arch

- [ ] 每条 item、每个 include 的影响面有 `case_intents`
- [ ] 意图都有 `baseline_item_id`
- [ ] `approach` 未改写 goal / non_goal
- [ ] `semantic_gate.req-review` 与 `semantic_gate.req` 已记录
- [ ] 方案整包已交出。有 `## arch` 轮时 `arch_frontier` 已空；没有未决问题就不要造一轮
- [ ] `## 前置` 写了影响范围内的既有问题、需求行数、既有问题行数。有既有问题时人已选，`scope_debt.decision` 不是 `pending`。一条都没有时 `decision` 为 `mark`
- [ ] `fix-first` 时子需求已 `done`，父票已按修完的代码重算影响面
- [ ] 本阶段不要求 `verify/plan.yaml`

## 调用 verify

- [ ] `plan.goal` / `non_goal` 复制自基线
- [ ] 每条 case 有 `slice_id` + `baseline_item_id`，且与 `req.yaml` 那条 slice 的 item 一致
- [ ] 没有 `PASS` 而 `evidence` 仍是 `not run`
- [ ] 未 `git add` / 未入库 `generatedverify/`

## code

- [ ] 只改 `arch.yaml` 里 `include: true` 的路径
- [ ] 已写 `review.md`（少做 / 多做 / UNRELATED）
- [ ] 已过 [coding.md](../../conventions/coding.md) 文首底线；已按 §0 + [coding-tables.md](../../conventions/coding-tables.md) §1 匹配（或确认零命中）并运用；§2 气味已扫且命中已改
- [ ] [coding-tables.md](../../conventions/coding-tables.md) §2.4 量化阈值已扫；超线已改或 `review.md` 写清理由并落 `C#`
- [ ] 若有结构调整：§3 R1–R6 满足；`review.md` 写了护栏 / R 条件
- [ ] `review.md`「编码规范」用本页 `P#`/`C#`/`R#`（禁止另起表号）；场景命中 / 气味命中 / 纠正非占位符
- [ ] `check-feature.sh <feature> code` PASS（含编码规范弱门禁）
- [ ] 本轮废弃无用的代码 / 导入 / 方法 / 字段已删；注释与文档已对齐代码
- [ ] 已按 [coding-tables.md](../../conventions/coding-tables.md) §3.8 增强扫描：`coding-scan.sh` + 五轴 + 栈指南；`review.md` 写了五轴 / 栈指南 / 增强扫描
- [ ] `review.md` 的 `审查者` 是 `idev-reviewer`，`文件与行数` 有数字
- [ ] 已跑该仓已有的规范扫描（有 super-linter 就跑那一套；否则 Java：`problems-scan.sh`；Python / Go / Shell / JS / Vue：`lang-scan.sh`；前端：`lint-fix`；仓内若有 Checkstyle/PMD/SpotBugs 一并绿）。插件不在是 `UNPROVEN`，不是扫干净。不为这层新装 IntelliJ、JDK、ruff、golangci-lint、shellcheck、eslint 或 Node
- [ ] 自测有跑证且独立审查已写入之后才请实现审核。确认写入 `semantic_gate.code` 并把 stage 改为 `test`
- [ ] `by:` 不是 agent / AI（对话确认后代写时须是人名）

## test

- [ ] 每条基线 item 至少一条 `mode=test` case
- [ ] UNPROVEN 写清缺基线或 non_goal，不写成达标
- [ ] 已按 [unproven-gate.md](../../verify/references/unproven-gate.md) 覆盖维表六族（case 或显式 UNPROVEN；correctness 不得免测）
- [ ] `semantic_gate` 已记到 `code`（实现审核）；人已确认接受残留 UNPROVEN 风险

## ops

细则在 `../ops/references/gates.md`。最少：

- [ ] 现场四件齐；`kind` 已定
- [ ] `feature` 已复现；`onboard`/`runtime` 已 handoff
- [ ] 未确认 origin 不准回退

## reopen

- [ ] 人已写 `reopen_baseline: true`
- [ ] `baseline.revision + 1`；旧 item id **不**拿去装新含义
- [ ] 下游 `req` / `arch` / verify plan 的 accepted 作废
