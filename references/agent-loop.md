---
audience: AI models and agents that load idev
authority: normative（双层回路的观测词汇表以本页为准；停车理由的枚举只认本表）
---

# agent 双层回路与统一停靠表

外层是导体回路，内层是 step 级循环。两层都不是新造的：外层是
[agents.md](agents.md)「导体回路」的既有命令链，内层是四个既有脚本的循环。本页把它们**收拢成一套观测词汇**，让「为什么停」在四种循环里说同一种话。

**本页不是第二状态机。** run 状态机的 step 状态
（`pending → ready → delegated → returned → verifying → terminal`）是唯一真源；
本页描述的 loop 是「谁在什么上限内反复做一件事」，是观测词汇表，不是状态。
一次停靠不改任何 run.yaml 字段，`DOCK` 行不进决策、不进签字、不进机检。

## 双层图

```
外层（导体回路，agents.md「导体回路」三命令）:
  next → (assess) → step/委派包 → agent → land → 机检 → record → trace → next
                ↘  human.gate → 人签/ AUTO → record ↙
                    遇到停靠 → 本表 → 谁接手 → 回到 next

内层（step 级循环，四个既有落点）:
  react     声明式 ReAct 工具循环   react_loop.py（配方步骤写 react 才存在）
  drive     导体自动推进            drive_run.py（CAP=8，遇 DELEGATE/PARALLEL/ASK/DECISION/失败即停）
  fanout    分片判定                fanout.py（SERIAL/FANOUT/MERGE/QUEUED）
  clean_pass 整轮重试               policy.require_clean_pass + max_clean_attempts（默认 5）
```

## 统一停靠表（STOP_REASON 只认本表）

| STOP_REASON | 触发条件 | 现有脚本信号 | 归属 loop | 停后谁接手 |
|---|---|---|---|---|
| `DELEGATE` | 下一步 kind 委派 | `DELEGATE idev-` 行 / fanout `SERIAL` | drive / fanout | 导体派执行者 |
| `PARALLEL-WAVE` | 组内并行波 | `PARALLEL <group>` 行 / fanout `FANOUT` | drive / fanout | 导体逐片派 |
| `ASK-SLOT` | 缺槽位 | `ASK slot` 行 | drive | 人补参数 |
| `DECISION` | 决策闸停问 | `DECISION` 行 | drive | 人答 `decide` |
| `SIGNAL` | 未答信号 | `SIGNAL …` / `land` 的 `STOP <step> has signals` | 外层 land | 人（drive=auto 按 RECOMMEND 代决；硬停点仍问人） |
| `HUMAN-GATE` | 人闸无 AUTO 判据 | `GATE at …` 无 `record AUTO` | drive | 人签字 |
| `FINAL-REVIEW` | solo_e2e 全链收口（stage=done 且 aligned） | session-context 的 `FINAL_REVIEW` 行 | 外层（run 之外） | 人终审：整体审或点名阶段深审 |
| `CMD-FAIL` | 导体命令失败 | `drive-*.log` 退出码≠0 / `record` 非零 | drive | 导体修环境 |
| `CAP-REACHED` | 上限已到 | `BLOCKED drive stopped after 8…` / fanout `QUEUED` 溢出 | 全部 | 人 |
| `LOOP-EXHAUSTED` | react 跳数用尽 | `EXIT human\|stop` + inbox `react-exhausted` | react | 按 `on_exhaust` |
| `TOOL-FAIL` | react 观察失败 | `EXIT` + inbox `react-tool-fail` | react | 按 `on_fail` |
| `MERGE-DUE` | 分片全回 | `MERGE … do not delegate` | fanout | 导体跑 `fanout.py merge` |
| `BLOCKED-REPORT` | 执行者 BLOCKED/检查未过 | `land` 的 `STOP` / `SEND BACK` | 外层 land | 按 HANDOFF / CONSULT / REBRIEF / 打回重派 |
| `AUTO` | 机检闸过（不停） | `record AUTO` | drive | 继续下一轮（列在表里是为了与 HUMAN-GATE 可辨） |

legacy kind（`ui.clean_pass_loop` / `ui.product_batch`）留行：老 run 仍在解析，新配方不用（`registry/kinds.yaml` why_kept）。

**`DOCK` 行的形态**（四种循环同一种语法）：

```
DOCK reason=<STOP_REASON> loop=<drive|fanout|react|land> <一行事实>
```

只拼既有输出能支撑的事实，同一条路径每次停都打同一个 reason。打在
**输出末尾**（drive 与 land 走 stderr），不插中间——消费方解析既有行的顺序不变。`DOCK` 行不进 trace 的必写字段：`recorded`/`delegations` 留真源，trace 有 `notes` 可选带一行。

## 循环上限总表（一处收拢，散页改指针）

| 上限 | 值 | 落点脚本 |
|---|---|---|
| 一轮分片 | 默认 4，最多 8，溢出 `QUEUED` | `fanout.py` |
| react 跳数 | 默认 8，硬顶 16 | `react_loop.py` |
| drive 导体步 | 8 | `drive_run.py` `CAP = 8` |
| 无正文助手回合 | 超过 8 判 FAIL（rounds ≥6 才查） | `turn-budget.py` / SKILL.md「回合预算」 |
| 同签名失败 | 3 次；连续 2 次无有效变化 | `failure_signature.py` 红线 |
| clean_pass 整轮重跑 | 默认 5（`policy.max_clean_attempts`） | `workflow.py` `CLEAN attempt=n/cap` 行 |

`CLEAN attempt=<n>/<cap>` 由 `workflow.py next` 从 run 的 `revisions[]`（`FAIL -> ` 前缀）与站立 FAIL 步骤派生；派不出来打 `CLEAN attempt=untracked`，不猜数。

## 探针规约（一行 HEALTH）

探针不合并：`s8-preflight`（票/配方/巡检包缺项）、`req-ground --probe`（给 codegraph 命令清单）、`runsc_probe`（隔离跑根因 snippet）各答一个不同的问句，合并是偶然复杂度（T1）。规约对三者一致：

| 约束 | 值 | 出处 |
|---|---|---|
| 输出 | 状态行 + 退出码（0 ok / 2 BLOCKED），不是长文 | 三个探针现有形态 |
| 体量 | 工具结果中位 386 字符是达标基线 | 20261102-turn-cost-reduction 实测 |
| 时延 | 超过 2 秒须 `block_until_ms` 先行一句话 | 只量不判：量出分布前不定红线（对齐 `cold-start-size.py --agents` 先例） |
| 收尾 | `s8-preflight` 末尾打 `HEALTH ok=<n> fail=<m>` 一行事实计数 | 不是分；covenant「PASS 只说明没撞已知硬错」照旧 |

## 常驻头与压缩（原则一行版）

- 委派包常驻头就是已有的三行：`本步:` / `PROGRESS closed=/open=` / `prior_failure`。**排序稳定在前、易变在后**（对齐前缀缓存的分层原则）。goal 密封在 baseline.yaml 按需读——可从磁盘重放的，不进上下文。
- 磁盘可重放层（`workflow/resume.yaml`、`workflow/reads.yaml`、`.idev/timeline/`）**只进指针不进正文**；HANDOFF 后新会话先读 `resume.yaml` 按 `open:` 行接着跑。
- 压缩是结构化拼装不是摘要：零 LLM 生成文本（agent-brief.md「留在书里」维持）。

## 反模式

| 不要 | 为什么 |
|---|---|
| 把本页读成第二套路由或新阶段机 | 路由唯一权威是 `SKILL.md` 决策树；本页只命名「停」 |
| 给 DOCK/CLEAN 行加执行力 | 观测行不进机检不进签字；加了就是新门禁，走提案先 |
| 为 stop reason 新增状态字段进 run.yaml | run 状态机字节不改；停靠是 step 迁移之间的观测 |
| 把导体做成 agent 来「闭环」 | P3 #15；签字权与停靠权都要留在导体 |
| 合并三个探针脚本 | 三问句三探针，合并丢可读性换偶然复杂度 |
