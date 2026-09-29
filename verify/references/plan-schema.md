# plan.yaml 契约（schema_version 1）

扩展加登记表的行。修正不兼容的语义时 **+1 `schema_version`**，并写 ADR；旧文件按「未知字段忽略、未知 mode/dimension 当 `UNPROVEN`」读，禁止改写已落盘的 `cases[].evidence`。

权威示例：[plan.example.yaml](plan.example.yaml)。

## 顶栏

| 字段 | 约束 |
|------|------|
| `schema_version` | 整数，当前 `1` |
| `feature` | kebab-case，与 `<票目录>/` 同名 |
| `mode` | 见模式表 |
| `accepted` | 人改为 `true`，或本轮确认用语全签后，才许 `run` 已勾选用例。见 [chat-confirm-signoff.md](../../references/chat-confirm-signoff.md) |
| `goal` / `non_goal` | 无密封基线则人写。有 `baseline.yaml` `sealed` 则**复制基线原文**，缺则拒写 |
| `entry` | `kind`: `diff` \| `phenomenon` \| `patrol-pack` |
| `impact_candidates` | Skill 提名；人 `include: true/false` |
| `cases` | 可执行项；`mode=test` 时维表六族须有 case 或 `unproven_surfaces` / `unproven.md` |
| `unproven_surfaces` | 可选；无 case 的维必须在此或 `<票目录>/unproven.md` 列出 |
| `human_signoff` | 不可执行项 |
| `revisions` | 追加，不覆盖。每次 plan/run/promote 一条 |

`entry` 按 mode：`logic`/`selftest` → `diff`；`debug` → `phenomenon`；`test` → 前两者之一；`patrol` → `patrol-pack`（无包拒跑）。

## 模式（加行，不新开 Skill）

| mode | 入口 | 机器必覆盖的维度（缺 = 该维 `UNPROVEN`） |
|------|------|------------------------------------------|
| `logic` | diff | `correctness` + 人勾选的 `compat` |
| `selftest` | diff | `correctness` + `compat`（必须有 case） |
| `debug` | phenomenon | `repro` + `root-cause-toggle` |
| `test` | diff 或 phenomenon | 维度表全列 |
| `patrol` | patrol-pack | 包内原样重放，不提名新影响面 |

新 mode：补一行 + 入口 + 维度子集。不要复制 SKILL.md。

## 维度（加行）

| id | 无对照物时 |
|----|------------|
| `correctness` | 必须有可执行 case，否则 `UNPROVEN` |
| `compat` | 未确认的影响面不跑，标 `UNPROVEN` |
| `boundary` / `exception` | 无 case → `UNPROVEN` |
| `concurrency` / `performance` | 无场景包或基线 → `UNPROVEN`，禁止写达标 |
| `ui-prototype` | 无原型对照 → `UNPROVEN` |
| `convention` | 无线程安全/性能/语言特性的可执行断言 → 只进 `human_signoff` |
| `repro` / `root-cause-toggle` | 仅 `debug` |

## 运行器（加行；日后 CLI 只认这些 kind）

| kind | v1 怎么跑 |
|------|-----------|
| `maven-surefire` | `mvn test -pl <module> -am -Pex -Dtest=<selector>` |
| `maven-failsafe` | `mvn verify -pl <module> -am -Pex -Dit.test=<selector> -DfailIfNoTests=false` |
| `shell` | 人确认过的一条命令（curl / 对比文件） |
| `frontend-http` | 先走当前产品 `.idev/handoff.yaml` 里的取 Cookie Skill，取该 `env`（local\|test\|prod）的会话 Cookie，再 curl/fetch。无会话则停，不准编 token。UI 对照仍要 `baseline_ref`，否则 `UNPROVEN` |

新 kind（浏览器、压测）必须带 `baseline_ref`，否则该 case 只能 `UNPROVEN`。`frontend-http` 的 `runner.env` 必填。

## `cases[]`

| 字段 | 约束 |
|------|------|
| `id` | 稳定 slug，修正时不要复用旧 id 装新断言 |
| `slice_id` | 端到端交付时必填，对齐 `req.yaml` 的 slices；无 `deliver.yaml` 可空 |
| `baseline_item_id` | 有密封 `baseline.yaml` 时必填；验收尺是基线 item，不是后来发挥的句子 |
| `dimension` | 维度表 |
| `runner` | `{ kind, module?, selector?, command? }` |
| `accepted` | 人改 YAML 或确认用语全签。`false` 则 `run` 跳过并 `UNPROVEN` |
| `status` | 只许 `PASS` \| `FAIL` \| `UNPROVEN` |
| `evidence` | 日志相对路径（`target/verify/...`）或未跑原因 |

AI 不得把未执行写成 `PASS`。生成测试的 `selector` 落在 `generatedverify` 包。

## `human_signoff[]`

| 字段 | 约束 |
|------|------|
| `id` | `req` / `design` / `arch` / 扩展 slug |
| `status` | 只许 `PENDING` \| `ACCEPTED` \| `REJECTED` |
| `by` | 人名；无确认用语不得填 `ACCEPTED` |

不可执行的「架构达标 / 规约度」只能待在这里。

## 修正与兼容

1. 猜想错了：追加 `revisions[]` + 新 `cases[]`，旧 case 留着当失败证据。
2. 登记表加行：旧 plan 不认识的 id → `UNPROVEN`，不要拒读。
3. 删行或改语义：`schema_version + 1` + ADR；提供只读迁移说明，不批量改写历史 report。
4. 抽 CLI：只实现本文件的读写与 runner 表，不另起一套状态机。

## 试运行评估与进化（加行，不新开 Skill）

台账 `~/.cursor/skills/idev/state/ledger.yaml`：`phase` 只许 `trial` \| `ga`。当前默认 `trial`。台账只有入口这一份，模块目录下不设台账。

反馈标签与提案流程见 [evolve.md](evolve.md)。加 tag / 加诚实性检查 = 改 evolve 登记表。  
`feedback.yaml` / `proposals/` 不是 `plan.yaml` 的字段；未知文件类型不要发明，先加登记。

`report.md` 的 `conductor-eval` 只计件数，不是分数，不进 `cases[].status`。
