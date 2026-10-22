# 停问与签字（唯一权威页）

什么时候停下来问人、问完怎么记，只在本页。其它页只留一行指针；与本页冲突以本页为准。

停问只有两类：

- **A 类签字**：不可逆、或改变后面所有工作的尺。位置固定，每次都停，人签名。
- **B 类决策**：AI 拿不准、或卡住了。只在出现**信号**时停，记人的回答，不是签字。

两类都不是的点不停：机检全过就往下走，需要留痕的记 `AUTO`。

## 档位 ↔ 停问点

`risk_tier` 写在 `<票目录>/deliver.yaml`（人定，缺省 P1）。

| 停问点 | P0 | P1 / P2 |
|--------|----|---------|
| 评审 → `baseline.sealed` | A，req-review 末单签 | A，**与拆解同签**：req 末一次写 `sealed` + `req.accepted` |
| 拆解 → `req.accepted` | A，req 末单签 | 并入上一行 |
| `arch.accepted` | A | A |
| verify plan → `plan.accepted` | A | 无 `SIGNAL` → `AUTO`；有 → 停问，人确认后签 |
| 提测 → `deliver.aligned` | A | A |
| ops 分类 | B：`kind` 拿不准时执行者回 `BLOCKED(logic)` | 同左 |
| 环境 / 产物 | B：`ARTIFACT: UNKNOWN` | 同左 |
| ops `resolved` | A | 账本收敛（有证成根因、无 open）→ `AUTO`；否则停问，人确认后签 |
| origin 回退 / 解封基线 | A，带关键字 | A，带关键字 |
| `promote` / 生产写 / `git push` | A | A |
| lessons 候选 → 权威 | A | A |

闸门放在副作用之前：先起草、自测、写报告，人签后才写签字字段、跑 `promote.sh`、写生产。
不可逆动作在任何档位都不降级。降档的依据是周审计里「`AUTO` / `[非承重]` 后被推翻」的次数，不是感觉。

## B 类：信号

| 信号 | 从哪来 |
|------|--------|
| `BLOCKED(logic)` | 任一执行者回报 |
| `ASSUMED: [承重] …` | 回报；每条假设以 `[承重]` / `[非承重]` 开头，或整行写「无」（`assumption-tagged` 机检） |
| `ARTIFACT: UNKNOWN` | idev-ops 回报 |
| grill `frontier` 非空、`objections` 非空、baseline-conflict | `grill.md`、`baseline.yaml` |
| 方案分叉未决 | `arch.yaml` |
| 残留 `UNPROVEN` 需人接受风险 | verify `report.md`；plan 阶段 `check-feature verify-plan` 打印 `SIGNAL` |
| plan 有不从基线 1:1 派生的用例 | `check-feature verify-plan` 打印 `SIGNAL` |
| 有界修复红线命中 | `hypothesis.py check` |
| `check-feature` / `stage-gate` 修一次后仍 FAIL | 脚本退出码 |

前三行由 `delegation.py write` 算出，写进委派留痕的 `signals` 并打印 `SIGNAL …`。该步有未答信号时 `workflow.py record <step> PASS` 拒收。

人答了就记：

```bash
workflow.py decide <step> --feature <f> --signal "<SIGNAL 原样>" \
  --question "<一句话问题>" --options "1 … / 2 …" --recommend "1" \
  --answer "<结论>" --quote "<人的原话>"
```

只追加到 `<票目录>/decisions.yaml`。有效回答是选项号或针对问题的自由文本；`继续` / `ok` / `好` 不选任何东西，拒收，再问一次。留痕里没有的信号拒收。决策不授权写任何签字字段。

## 决策包（每次停问唯一格式）

```
【需要你决定】<停问点>  risk_tier=<P0|P1|P2>
触发: <A 类闸名 | B 类信号 + 出处路径>
问题:
  1. <一句话问题>  选项: a) … b) …  AI 建议: a，因为 …
证据: check-feature=<…>  stage-gate=<…>  PASS/FAIL/UNPROVEN=<n/n/n>  未决 grill=<id|无>
将代写: <字段列表>（仅 A 类）
```

- 一次停问合并当时所有 B 类信号。A 类闸与 B 类问题同时出现，先答 B 类，再签 A 类。
- 没有 A 类闸、也没有信号，就不停，不说「请确认」。

## A 类：签字

### 确认用语

大小写不敏感，可带句号 / 感叹号：`确认` / `全签` / `同意` / `LGTM`。整句只能是确认（`parse_confirm` 文法）：`同意吗`、`确认不了` 不算。
`继续` / `continue` / `ok` / `好` / 只提修改都不算。

### `by`

1. 本特征 `<票目录>/` 里已有、且能过 `workflow_spec.is_human()` 的 `by`
2. 否则 `git config user.name`（同样须过 `is_human()`）
3. 都没有 → 问一句名字，**不签**

`is_human()` 按词表拒绝 agent / 模型 / 角色名；存在 `config/people.yaml` 时名字还必须在白名单里。S8 的 `human.gate` 要求白名单必须存在。禁止把 `by` 写成 agent / AI。

### 签字怎么落笔：聊天里回确认

人在对话里回确认用语，就是认可当前停问点。导体把这一句原话记下来，不要求人另开终端。

```bash
workflow.py record <gate> PASS --by <人名> --quote "<人的原话>"
```

`by` 按上一节取。`quote` 必须是本轮原话，整句过确认文法。`继续` / `ok` / `好` 拒收。导体不得编造原话。

deliver 各阶段的字段（上表）同样只在这句确认之后代写进 YAML。一次确认只写当前停问点。

`workflow.py ask` 加 `idev gate approve` 仍可走，用来留下终端签名。它不是必经步骤。人已经回了确认用语，就直接 `record --by --quote`，不要再请人去终端。agent 不得自己跑 `idev gate approve` / `idev gate reject` / `idev token init`。

### 只签当前停问点（不跨阶段）

| 停在 | 代写 | 签完立刻 |
|------|------|----------|
| req-review（P0） | `baseline.sealed=true` + `by` + `semantic_gate.req-review` | 进入 `req` |
| req（P0） | `req.accepted=true` + `by` + `semantic_gate.req` | 进入 `arch` |
| req（P1 / P2） | `baseline.sealed=true` + `req.accepted=true` + `by` + `semantic_gate.req-review` + `semantic_gate.req` | 进入 `arch` |
| arch | `arch.accepted=true` + `by` + `semantic_gate.arch`（不改已拟 `include`） | 进入 `code` |
| verify plan（P0，或 P1/P2 有 `SIGNAL`） | `plan.accepted=true`；全部 `cases[].accepted=true`；`human_signoff` → `ACCEPTED` + `by` | `run`（无 runner 的维仍 `UNPROVEN`） |
| test 提测 | `deliver.aligned=true` + `by` | `done`（人没提提升 / 巡检包 / promote 则不问 promote） |
| ops `resolved`（P0，或 P1/P2 账本未收敛） | `resolved=true` + `by` | 关单 |

一次确认不把后面的 `aligned` / `done` 一并签掉。P1/P2 在 req-review 末不停：`check-feature req` 在基线未密封时照样查基线就绪、grill 已闭合、人读规格在，并打印 `baseline seals with req at P1`。`arch` 及之后仍要求 `sealed: true`。

### 破坏性必须带关键字

| 动作 | 确认句须含 |
|------|------------|
| 回退 | `origin=req` / `origin=arch` / `origin=code`（如 `确认 origin=code`） |
| 解封基线 | `解除密封` 或 `reopen` |

无关键字当普通确认，不写 `reopen_baseline` / `defect_origin`。

### 停问回显（硬）

请人确认前，消息里**必须有且仅针对当前停问点**的一行：

`将代写: <字段列表>`

示例：`将代写: arch.accepted、arch.human_signoff、deliver.semantic_gate.arch、deliver.stage=code`。

1. 人回确认用语后，只写这一行列出的字段（外加同表规定的立刻下一步）。
2. 禁止笼统说「请确认」却不写将代写列表。
3. 列表与上表「代写」列不一致 → 先改列表再请签，不准边猜边写。

### 证明上下文（硬，防橡皮图章）

请签消息在 `将代写:` 之外，还必须用短列表给出**本停问点相关证明**（有则写，无则写「无/未跑」）：

| 停问点 | 至少要有 |
|--------|----------|
| req-review / req / arch | `check-feature <stage>` 结果；未决拷问 id |
| verify plan | case 数；correctness 是否可执行；`SIGNAL` 行 |
| test 提测 / aligned | `check-feature test`；PASS/FAIL/UNPROVEN 计数；人是否接受残留 UNPROVEN；仍 `PENDING` 的 `human_signoff` |
| promote（人已提及时） | plan.mode；accepted；PASS 数；目标 `doc_home.py --key patrol` |

禁止：只贴 Agent 摘要、不贴门禁/跑证就请人「确认」。

## AUTO：机检代替人

只在上表写了 `AUTO` 的格子，且没有信号时：

| 点 | 写法 | 谁查 |
|----|------|------|
| S8 `human.gate` | 配方 `with.auto_tiers` 含本票档位；把检查输出存成文件，`workflow.py record <gate> AUTO --evidence <文件>`，不带 `--by` / `--quote` | `workflow.py`：文件要有 `0 FAIL` 行，不能有 `SIGNAL` 行 |
| `plan.yaml` | `accepted: true` + `auto: <检查输出>`，`cases[].accepted: true`；`human_signoff` 保持 `PENDING`，提测时给人看 | `check-feature test`：档位在 P1/P2、文件存在、没有人名 `by` |
| `ops.yaml` | `resolved: true` + `auto: <路径>`，不写 `by` | `check-feature ops`：档位在 P1/P2、`hypothesis.py check` 绿、无 `open`、至少一条 `proven` |

`semantic_gate.*` 没有 `AUTO` 写法：它记的 req-review / req / arch 在每个档位都是 A 类。

## 诚实性

无本轮确认用语却把 `sealed` / `accepted` / `aligned` / `resolved` / `human_signoff` / `semantic_gate.*.passed` 写成 true / `ACCEPTED` → 伪造。`AUTO` 格子以外写 `auto:` 也是伪造。
有确认用语且 `by` 是人名 → 合法代写。trace 记 `kind: call` / `chose: chat-confirm-signoff`。

## 不准

- agent 运行 `idev gate approve` / `idev gate reject` / `idev token init`，包括借 `script` 等手段伪造终端，或读取、改写 `~/.idev/secrets/`
- 人已经回了确认用语，仍请人去终端再签一次
- 编造确认原话再写入 `--quote`
- 请签时不贴证明上下文（门禁/跑证/UNPROVEN）
- 请签时不写 `将代写: …` 一行
- 用确认改 baseline `goal` / `items` / `non_goal`
- 把 `继续` 当签字或当决策
- `check-feature` FAIL 仍代签
- 有 `SIGNAL` 仍记 `AUTO`
- 已 accepted 的 plan 再 `run` 时重跑 `verify-plan` 或再请人签一次
- 无当前停问点还请人「确认」
- 人没提提升 / 巡检包 / promote 仍问 `promote.sh`
- 自测门过后人没说「提测」仍问是否进入 `mode=test`
