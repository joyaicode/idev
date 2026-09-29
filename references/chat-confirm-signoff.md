# 对话确认 → 当前停问点全签

人授权通道可以是改 YAML，也可以是**本轮确认用语**。两种等价。  
`继续` / `continue` / `ok` / `好` / 只提修改 **不算**确认。

## 确认用语

大小写不敏感，可带句号/感叹号：`确认` / `全签` / `同意` / `LGTM`。

## `by`

1. 本特征 `<票目录>/` 里已有非空、且不是 `agent|ai|cursor|assistant` 的 `by`
2. 否则 `git config user.name`
3. 都没有 → 问一句名字，**不签**

禁止把 `by` 写成 agent / AI。

## 只签当前停问点（不跨阶段）

| 停在 | 代写 | 签完立刻 |
|------|------|----------|
| req-review | `baseline.sealed=true` + `by` + `deliver.semantic_gate.req-review` | 进入 `req` |
| req | `req.accepted=true` + `by` + `semantic_gate.req` | 进入 `arch` |
| arch | `arch.accepted=true` + `by` + `semantic_gate.arch`（不改已拟 `include`） | 进入 `code` |
| verify plan（起草或调整 `cases[]` 时） | `plan.accepted=true`；全部 `cases[].accepted=true`；`human_signoff` → `ACCEPTED` + `by` | `run`（无 runner 的维仍 `UNPROVEN`） |
| test 提测 | `deliver.aligned=true` + `by` | `done`（人没提提升 / 巡检包 / promote 则不问 promote） |
| ops `resolved` | 仅当停问就是 resolved | 关单 |

一次确认不把后面的 `aligned` / `done` 一并签掉。

## 破坏性必须带关键字

| 动作 | 确认句须含 |
|------|------------|
| 回退 | `origin=req` / `origin=arch` / `origin=code`（如 `确认 origin=code`） |
| 解封基线 | `解除密封` 或 `reopen` |

无关键字当普通确认，不写 `reopen_baseline` / `defect_origin`。


## 停问回显（硬）

请人确认前，消息里**必须有且仅针对当前停问点**的一行：

`将代写: <字段列表>`

示例：`将代写: arch.accepted、arch.human_signoff、deliver.semantic_gate.arch、deliver.stage=code`。

规则：
1. 人回确认用语后，只写这一行列出的字段（外加同表规定的立刻下一步）。
2. 禁止笼统说「请确认」却不写将代写列表。
3. 列表与上表「代写」列不一致 → 先改列表再请签，不准边猜边写。


## 证明上下文（硬，防橡皮图章）

请签消息在 `将代写:` 之外，还必须用短列表给出**本停问点相关证明**（有则写，无则写「无/未跑」）：

| 停问点 | 至少要有 |
|--------|----------|
| req-review / req / arch | `check-feature <stage>` 结果；未决拷问 id |
| verify plan | case 数；correctness 是否有 runner；UNPROVEN 维 |
| test 提测 / aligned | `check-feature test`；PASS/FAIL/UNPROVEN 计数；人是否接受残留 UNPROVEN |
| promote（人已提及时） | plan.mode；accepted；PASS 数；目标 `doc_home.py --key patrol` |

禁止：只贴 Agent 摘要、不贴门禁/跑证就请人「确认」。

## 诚实性

无本轮确认用语却把 `sealed` / `accepted` / `aligned` / `resolved` / `human_signoff` / `semantic_gate.*.passed` 写成 true / `ACCEPTED` → 伪造。  
有确认用语且 `by` 是人名 → 合法代写。trace 记 `kind: call` / `chose: chat-confirm-signoff`。

## 不准

- 请签时不贴证明上下文（门禁/跑证/UNPROVEN）
- 请签时不写 `将代写: …` 一行
- 用确认改 baseline `goal` / `items` / `non_goal`
- 把 `继续` 当签字
- `check-feature` FAIL 仍代签
- 已 accepted 的 plan 再 `run` 时重跑 `verify-plan` 或再请人签一次
- 无当前停问点还请人「确认」
- 人没提提升 / 巡检包 / promote 仍问 `promote.sh`
- 自测门过后人没说「提测」仍问是否进入 `mode=test`
