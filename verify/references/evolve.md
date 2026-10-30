# 试运行评估与进化（拷问后才落地）

导体当前 **`phase: trial`**。试运行必须收反馈；改进只能先写成提案，**拷问对齐后再改 Skill / schema / 文档**。  
禁止：Skill 根据一次聊天自行改自己、用分数当门禁、用 LLM 自评代替人确认。

## 自进化闭环（Hermes 对齐）

在线：执行 → nudge（有信号）→ 提案草稿 → grill → 人确认 → land。  
脚本与映射：[references/self-evolution.md](../../references/self-evolution.md)。  
S8：`self-evolve-review`（别名：自进化 / 进化复盘）。  
`bash ~/.cursor/skills/idev/scripts/evolve-review.sh` 只写草稿；`evolve-curator.sh` 归档超龄提案（默认不 `--apply`）。  
**仍禁止**未确认改 Skill、分数门禁、LLM 自评盖章。  
学习信号、落点，以及写出更新的一方不改验证，见 [self-evolution.md](../../references/self-evolution.md)「学习信号写到哪里」。


入口台账：`~/.cursor/skills/idev/state/ledger.yaml`（`phase` / `conductor_revision` / `acceptance: chat-confirm`）。台账只有这一份，模块目录下不设台账。

## 评估（可数，不是打分）

每次 `run` 在 `report.md` 写 `## conductor-eval`，只计件数：

| 计数 | 从哪来 |
|------|--------|
| `cases_pass` / `cases_fail` / `cases_unproven` | `cases[].status` |
| `unproven_reasons` | `evidence` 分类：`not-accepted` / `no-baseline` / `no-runner` / `unknown-id` |
| `impact_nominated` / `impact_included` | `impact_candidates` |
| `signoff_pending` | `human_signoff` 仍 `PENDING` |
| `feedback_status` | 同目录 `feedback.yaml`：`pending` \| `received` \| `none` |

另做**可机检的诚实性**（任一失败写进 report，不得粉饰）：

| 检查 | 失败条件 |
|------|----------|
| `no-pass-without-evidence` | `PASS` 却没有日志路径 |
| `signoff-not-forged` | 无本轮确认用语却把 `human_signoff` 写成 `ACCEPTED`（有确认用语且 `by` 是人名则通过） |
| `one-hop-only` | 候选 `hop` > 1 |
| `trial-asked-feedback` | 单独点名 verify 且 `phase=trial` 且 run 结束没有 `feedback.yaml`。由 deliver / ops 调用时只写 `conductor-eval`，本条不适用 |

结构好不好由人在拷问里评，不当机器门禁。  
路由对不对看该次会话的 traces：产品仓是 `<repo>/.idev/traces/`，导体自身会话才是 `idev/state/traces/`。  
再评估 / 提案写发现 + 证据 + 是否落地。

## 反馈标签（人填，试运行必问）

`<票目录>/verify/feedback.yaml`，标签只许下表（加标签 = 改本登记表，不新开文件类型）：

| tag | 含义 |
|-----|------|
| `missed-impact` | 影响面漏了后来出事的路径 |
| `false-green` | case 绿了但用户现象仍在 |
| `false-unproven` | 其实能跑，被标成 UNPROVEN |
| `wrong-mode` | mode 用错 |
| `too-heavy` | plan 膨胀、无关 case 太多 |
| `skill-unclear` | Skill 步骤含糊导致 Agent 做错 |
| `schema-gap` | 契约缺字段 / 缺 runner |
| `ok` | 这次没有导体问题 |

`status: pending` 直到人写 `tags` 或明确 `none`。Agent 可代写人口述，但 `by` 必须是人。  
试运行每次 run 后 **停问**：哪些 tag、一句话证据。收到后复制一份到当前会话的 inbox（产品工程 `.idev/inbox/<feature>-<n>.yaml`；没有当前产品才是内核 `verify/state/inbox/`）。

## 提案 → 拷问 → 落地

1. **propose**（人要进化，或 inbox 里同类 tag ≥ 2）：产品会话写该工程 `.idev/proposals/<NN>-<slug>.md`。只有改内核自己、且没有当前产品时，才写  
   `~/.cursor/skills/idev/verify/state/proposals/<NN>-<slug>.md`  
   只许改：登记表加行、Skill 硬规则/步骤澄清、文档指针。  
   必须写：要改什么 / 不改什么 / 依据哪些 feedback id / 是否升 `schema_version`。
2. **grill**：只拷问该提案的分叉（读 `~/.cursor/skills/grilling/SKILL.md`）。未到「确认」不得改 Skill。
3. **land**：人说确认后，只改真源 `~/.cursor/skills/idev/verify/`（检查脚本受影响时改 `idev/scripts`）。不要写回产品仓，不要 PR keep-current。不兼容则在本机 references 加 ADR 副本 + `schema_version + 1`。入口台账 `~/.cursor/skills/idev/state/ledger.yaml` 的 `conductor_revision + 1`，提案标 `landed`。导体验收是 **chat-confirm**，不要为导体自身改动建产品仓 `docs/task` 票。
4. **ga**：只有人再次拷问确认，才把入口台账 `phase` 从 `trial` 改成 `ga`。`ga` 后反馈改为按需，不再每次 run 强停；inbox 规则仍在。

AI 不得把提案标 `landed`，不得在拷问未确认时改 SKILL.md。
