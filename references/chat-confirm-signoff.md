# 停问与签字（唯一权威页）

什么时候停下来问人、问完怎么记，只在本页。其它页只留一行指针；与本页冲突以本页为准。

交付阶段不设确认。检查过了、没有未决分叉，就写下这一关，并在同一轮接着做。不要人说确认、通过或继续，也不要人再输口令、短码或关键字。

停下来只有一类：

- **B 类决策**：机器在书面判据下定不了。只在出现**信号**时停，记人的回答。

解封、回退、promote、生产写、`git push`、经验入库仍要点名那件事。这些不是交付确认。机检全过、没有信号，就往下走。

## 编制：先认人岗，再决定怎么问

当前工程里谁担任哪个岗位，先认出来，再决定这一轮问谁、问多少。岗位是产品、设计、架构、开发、测试、交付、排障。认法只在 `scripts/staffing.py`（`session-context` 打出一行 `STAFFING`）。

| 读到的 | 模式 | 这一轮怎么问 |
|--------|------|----------------|
| `.idev/staffing.yaml` 里全部岗位落在同一个人 | `solo` | 七个视角一次列全，问这一个人 |
| 岗位落在两个以上的人 | `collaborative` | 只问 `hold` 里当前这个人的岗位。`wait` 里别人的岗位列成「待」，不向当前这个人问，也不为此再开一轮 |
| 产品 `.idev/people.yaml` 只有一个人，没有岗位文件 | `solo` | 这个人兼任七岗。不问「你是哪个角色」 |
| 产品名单有两个人以上，还没有岗位文件 | `unassigned` | 只问一次岗位表（同一人兼任就各岗填同一人）。写完 `staffing.py write` 之前不签字，不再拆开问 |
| 产品没有名单 | 回落内核 `config/people.yaml` | 内核只有一个人时视为兼任。内核也没有人、git 用户名是人，则视为这一个人 |

产品名单不并入内核名单。内核名单只在产品还没写名单时，表示当前操作的人。

判据已经能唯一得出结论的，直接做并留痕，不开讨论。事实能从代码和工件里查到的，不设成题。需求、架构、实现、提测在检查通过后直接落笔，不问人。解封、回退、promote、生产写、push、经验入库仍要点名。B 类只在信号出现、并且书面判据给不出唯一结论时，并进上面这一轮。

一次讨论把当前这个人能答的未决问题按他持有的视角列全，放在同一条消息里。他持有的视角没有未决就写「无未决」。挂在本题选项上的后续写成「若第 n 题选 a，则…」，放在同一轮。没有未决就不问。只有回答打开了这轮没有写到的新分叉，才再开一轮。交付阶段不在这轮之外再要一句确认。

`record PASS` 在编制是 `collaborative` 时拒绝不在该闸岗位上的人。`solo` 不另加这层。岗位还没写明时，任何人的签字都先被拒绝，直到岗位文件落地。

## 档位 ↔ 停问点

`risk_tier` 写在 `<票目录>/deliver.yaml`（人定，缺省 P1）。

交付主路径不为确认停。问答不是落笔条件。

| 点 | 所有档位 |
|----|----------|
| 需求通过 → `baseline.sealed` + `req.accepted` | 检查通过且 frontier 空，同时写密封和拆解。不问确认 |
| 架构通过 → `arch.accepted` | 检查通过且没有未决分叉，写架构通过并进入 `code`。不问确认 |
| 实现审核 → `semantic_gate.code` | 用例、编码、自测做完且检查通过，写这一关并进入提测。不问确认 |
| 提测结果 → `deliver.aligned` | 提测检查通过，写 `aligned` 并 `done`。不问确认 |
| verify plan → `plan.accepted` | 无 `SIGNAL` → `AUTO`（含 P0）。有 `SIGNAL` 留到实现审核一起答，不提前停 |
| ops 分类 | B，所有档位：`kind` 拿不准时执行者回 `BLOCKED(logic)` |
| 环境 / 产物 | B，所有档位：`ARTIFACT: UNKNOWN` |
| ops `resolved` | 账本收敛（有证成根因、无 open）就写。没收敛是 B，答完再写 |
| origin 回退 / 解封基线 | 所有档位，回复里要点名那件事 |
| `promote` / 生产写 / `git push` | 所有档位，人要点名 |
| lessons 候选 → 权威 | 所有档位，人要点名 |

先起草、自测、写报告。检查过了才写这些字段。promote、生产写仍等人点名。
不可逆动作在任何档位都不降级。降档的依据是周审计里「`AUTO` / `[非承重]` 后被推翻」的次数，不是感觉。

## B 类：信号

| 信号 | 从哪来 |
|------|--------|
| `BLOCKED(logic)` | 任一执行者回报 |
| `ASSUMED: [承重] …` | 回报；每条假设以 `[承重]` / `[非承重]` 开头，或整行写「无」（`assumption-tagged` 机检） |
| `ARTIFACT: UNKNOWN` | idev-ops 回报 |
| grill `frontier` 非空、`objections` 非空、baseline-conflict | `grill.md`、`baseline.yaml` |
| 方案分叉未决 | `arch.yaml` |
| 影响范围内的既有问题 | 判据在 `deliver/SKILL.md`。两条都能用证据判定时直接写 `scope_debt.decision`（`mark` 或 `fix-first`），不问。行数 `UNPROVEN`、分不开定不了、或重大缺陷定不了时才 `pending`，并进当前这个人的决策包。选项只有先修、本次不修。一条都没有时 `mark` |
| 残留 `UNPROVEN` 需人接受风险 | verify `report.md`；plan 阶段 `check-feature verify-plan` 打印 `SIGNAL` |
| plan 有不从基线 1:1 派生的用例 | `check-feature verify-plan` 打印 `SIGNAL` |
| 有界修复红线命中 | `hypothesis.py check` |
| `check-feature` / `stage-gate` 修一次后仍 FAIL | 脚本退出码 |

前三行由 `delegation.py write` 算出，写进委派留痕的 `signals` 并打印 `SIGNAL …`。该步有未答信号时 `workflow.py record <step> PASS` 拒收。

用例计划上的 `SIGNAL` 不单独停。留到实现审核，和这次审核一起答。架构通过之后、自测完成之前，不为计划再请一次签。

人答了就记：

```bash
workflow.py decide <step> --feature <f> --signal "<SIGNAL 原样>" \
  --question "<一句话问题>" --options "1 … / 2 …" --recommend "1" \
  --answer "<结论>" --quote "<人的原话>"
```

只追加到 `<票目录>/decisions.yaml`。有效回答是选项号或针对问题的自由文本；`继续` / `ok` / `好` 不选任何东西，拒收，再问一次。留痕里没有的信号拒收。`decide` 本身不写签字字段。同一句如果也是当前这一步的对齐，导体接着 `record`，不再向人要第二句。

## 决策包（每次停问唯一格式）

```
【需要你决定】<停问点>  risk_tier=<P0|P1|P2>
编制: <STAFFING 行>
触发: <A 类闸名 | B 类信号 + 出处路径>
方案: <这一步的图，短>
问题:                          # 没有未决就整段不写，不编题
  1. <一句话问题>  选项: a) … b) …  AI 建议: a，因为 …
  若第 1 题选 b，则这幅图不成立，改方案，不落笔。
证据: check-feature=<…>  stage-gate=<…>  PASS/FAIL/UNPROVEN=<n/n/n>  未决 grill=<id|无>
```

- 一条消息只含当前这个人能答的未决。没有未决，就只摆方案和证据。
- 人选了不推翻的那一档，或只说 `按建议` / `听你的` / 选项号，这句就是对齐，直接落笔。人选了包里写明会让这幅图不成立的那一档，就改方案，不落笔。
- `待` 里的事项不向当前这个人问。
- 没有 A 类闸、也没有信号、编制也不缺岗位，就不停。

## 交付阶段：检查过了就写

这一关的检查过了，并且没有未决的 B 类分叉，就写下这一关，接着做下一阶段。不问确认，不等「通过」。`继续`、`ok`、`好`、`看着差不多` 都不是停顿。

原话不解析。疑问、否定、犹豫、空句子、`继续`、`确认不了` 都一样，记下这一步。否决用 `record FAIL` 或 `idev gate reject`，不靠句子分类。检查没过就只写没过的那一条。基线已经 `sealed: true` 时，直接写架构通过。解封和回退不需要关键字。

### `by`

1. 本特征 `<票目录>/` 里已有、且能过 `workflow_spec.is_human()` 的 `by`，并且在 `collaborative` 下还持有这一闸的岗位
2. 否则编制里的当前人（`solo` 就是那一个人；`collaborative` 就是 `STAFFING` 的 `chat`，且持有这一闸）
3. 否则 `git config user.name`（同样须过 `is_human()`，并且对得上编制）
4. 都没有 → 问一次名字，并进当次消息，**不签**。不为此再开一轮

`is_human()` 按词表拒绝 agent / 模型 / 角色名；存在 `config/people.yaml` 时名字还必须在白名单里。S8 的 `human.gate` 要求白名单必须存在。禁止把 `by` 写成 agent / AI。

### 怎么落笔

```bash
workflow.py record <gate> PASS
```

`by` 按上一节取，可以不传。不需要 `--quote`。这一步已经开了门时，同一次记录把那张门记成已批准。不要终端，不要短码，不要确认。

deliver 各阶段的字段（上表）在检查通过后写入 YAML。一次只写当前这一关。

agent 不得跑 `idev token init`，不得读取或改写 `~/.idev/secrets/`。`驳回` 仍是拒绝。

### 只写当前这一关（不跨阶段）

| 停在 | 代写 | 签完立刻 |
|------|------|----------|
| 需求通过（每个档位） | `baseline.sealed=true` + `req.accepted=true` + `by` + `semantic_gate.req-review` + `semantic_gate.req`；`grill.md` 的 `shared_understanding: true` | 进入 `arch`。不另请一次「共享理解」 |
| 架构通过 | `arch.accepted=true` + `by` + `semantic_gate.arch`（不改已拟 `include`） | 进入 `code`，接着做用例、编码、自测，中间不再请签 |
| 实现审核 | `semantic_gate.code` + `by`；`deliver.stage=test`。若 plan 有 `SIGNAL` 且尚未 `AUTO`，同一次写 `plan.accepted=true` 与 `cases[].accepted=true` | 进入提测。不另问「要不要提测」 |
| 提测结果 | `deliver.aligned=true` + `by` | `done`（人没提提升 / 巡检包 / promote 则不问 promote） |
| ops `resolved`（P0，或 P1/P2 账本未收敛） | `resolved=true` + `by` | 关单 |

一次落笔不把后面的关一并写掉。需求在 `req` 末写，不在 `req-review` 末再停一次：`check-feature req` 在基线未密封时照样查基线就绪、frontier 已空、人读规格在，并打印 `baseline seals with req at <档位>`。`shared_understanding` 由这次落笔写入。`arch` 及之后仍要求 `sealed: true`。架构不要求事先写过 `## arch` 问句。

### 回退和解封要点名那件事

| 动作 | 回复里点名 |
|------|------------|
| 回退 | `回退到需求` / `回退到架构` / `回退到实现`，或 `问题在需求` / `问题在架构` / `问题在编码`。`origin=req` / `origin=arch` / `origin=code` 仍认 |
| 解封基线 | `打开基线` / `解除密封` / `重新打开基线` / `解封` / `reopen` |

没点名，就不是这一步的对齐，不写 `reopen_baseline` / `defect_origin`。密封门上说出密封本身（`密封` / `进行密封` / `确认密封`）也算对齐；`解除密封` 是解封，不算。点了名但带否定、转折或犹豫（`不要解除密封`、`密封，但是范围要改`、`等等再打开基线`），照样拒收。点了回退或解封，也不能拿去通过当前的需求、架构、实现或提测，也不能拿去通过密封门。

### 落笔清单不念给人

`workflow.py next` 打出的 `将代写:` 是导体自己的落笔清单。对人只摆方案和证据。不把字段名、门短码念给人。

1. 检查通过之后，只写上表这一行的字段（外加同表规定的立刻下一步）。
2. 清单和上表「代写」列不一致 → 先改清单再写，不准边猜边写。

### 证明上下文（硬）

请人看这一步时，用短列表给出**本停问点相关证明**（有则写，无则写「无/未跑」）：

| 停问点 | 至少要有 |
|--------|----------|
| 需求通过 / 架构通过 | `check-feature <stage>` 结果；未决问句 id（没有就写无） |
| 实现审核 | `check-feature code`；selftest 的 PASS/FAIL/UNPROVEN；并进来的 plan `SIGNAL`（没有就写无） |
| 提测结果 / aligned | `check-feature test`；PASS/FAIL/UNPROVEN 计数；人是否接受残留 UNPROVEN；仍 `PENDING` 的 `human_signoff` |
| promote（人已提及时） | plan.mode；accepted；PASS 数；目标 `doc_home.py --key patrol` |

禁止：检查没过就写这一关。对人只在有未决分叉时开口。

## AUTO：机检代替人

只在上表写了 `AUTO` 的格子，且没有信号时：

| 点 | 写法 | 谁查 |
|----|------|------|
| S8 `human.gate` | 配方 `with.auto_tiers` 含本票档位，且只给 plan 闸（`accepted_plan`）；`workflow.py record <gate> AUTO`，不带 `--by` / `--quote`。它自己跑 `check-feature verify-plan`，输出写进 `verify/plan-check.log`，退出码和 sha256 记进该步 `auto:`；`--evidence` 可省，写了只能是这个文件 | `workflow.py`：它跑出的输出要有 `0 FAIL` 行、没有 `SIGNAL` 行，且 `verify.plan` 步留痕里的信号都已 `decide`。事先存好的文件不算数，会被覆盖 |
| `plan.yaml` | `accepted: true` + `auto: <检查输出>`，`cases[].accepted: true`；`human_signoff` 保持 `PENDING`，实现审核时给人看。有 `SIGNAL` 不记 `AUTO`，并进实现审核 | `check-feature test`：文件存在、没有人名 `by`。每个档位都可以 |
| `ops.yaml` | `resolved: true` + `auto: <路径>`，不写 `by` | `check-feature ops`：档位在 P1/P2、`hypothesis.py check` 绿、无 `open`、至少一条 `proven` |

`semantic_gate.*` 在检查通过后写入，不另设确认。

## 诚实性

检查没过，或还有未决分叉，却把 `sealed` / `accepted` / `aligned` / `resolved` / `human_signoff` / `semantic_gate.*.passed` 写成 true / `ACCEPTED` → 伪造。`by` 写成 agent / AI → 伪造。`AUTO` 格子以外写 `auto:` 也是伪造。
检查过了就写，这是本规则，不是伪造。

## 不准

- agent 运行 `idev token init`，或读取、改写 `~/.idev/secrets/`
- 检查已经通过，仍请人确认、通过，或再输入短码
- 请人看这一步时不贴证明上下文（门禁/跑证/UNPROVEN）
- 把字段名或 `将代写` 清单念给人
- 没有未决却编一道题
- 用落笔改 baseline `goal` / `items` / `non_goal`
- 把 `继续` 当成对一道未决题的回答
- `check-feature` FAIL 仍写这一关
- 有 `SIGNAL` 仍记 `AUTO`
- 已 accepted 的 plan 再 `run` 时重跑 `verify-plan`
- 无未决分叉还请人「确认」
- 判据已经唯一时仍把既有问题拿来问人
- 按岗位或按视角拆成多轮问同一个人
- 向当前这个人问 `STAFFING` 里 `wait` 的题
- 岗位还没写明时分几次问人岗关系
- 编制已经认出唯一的人，仍问名字或问他担任哪个角色
- 检查过了，字段仍是 false、门仍 pending
- 叫人输入门短码、验证码、口令或 `origin=` 关键字
- 基线已经 `sealed: true`，还要再等一句密封才写架构通过
- 人没提提升 / 巡检包 / promote 仍问 `promote.sh`
- 自测还没跑完就请人做实现审核
- 实现审核通过后另问「要不要提测」
- 用例计划单独请签（无 `SIGNAL` 记 `AUTO`，有则并进实现审核）
