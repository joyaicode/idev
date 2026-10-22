# 提案：回合预算，先说话再堵住

- status: landed
- at: "2026-10-22T12:40:00+08:00"
- scope: 导体与执行者在聊天回合里的可见进度、长命令、存活探测、检索止损
- 确认：by wangwei794，quote「确认」，2026-10-22。认的是本提案四刀与「不改什么」。
- 落地：by wangwei794，quote「确认」，2026-10-22。`conductor_revision` 2 → 3。
- 续落：2026-10-22，人说「修复并落地所有提升项」。机检补上连续无正文、未先开口的长命令、`claude -p` / `agent -p`。`conductor_revision` 3 → 4。
- 续落：2026-10-22，人说「继续」。四条全量套件 `block_until_ms` 大于 30000 记 `suite_block`。`conductor_revision` 4 → 5。结构检索仍是做法，不进脚本。
- 续落：2026-10-22，人又说「继续」。`healthcheck.sh` 与 `agent-smoke.sh` 同样记 `suite_block`。存活改为一行回复。`conductor_revision` 5 → 6。
- 依据：`state/traces/20261022-001.yaml`

## 定案

1. 发出 `block_until_ms` 大于 30000 的命令之前，先写一句用户可见的话：命令、预算、在等什么。
2. 连续 8 个只有工具、没有正文的助手回合之后，必须先写一句现状再继续。一条消息里的多个只读工具算一个回合。
3. 聊天回合里不用 `claude -p` 或 `agent -p` 做存活探测。调起检查走 `scripts/healthcheck.sh` 或 `scripts/agent-smoke.sh`，或一次不调用工具的一行回复。
4. 结构问题先一次 `codegraph_context`。查不到就停并写明查不到，不再退回几十轮 `Grep` / `Read`。
5. 全量 `scripts/selfcheck.sh`、`test/golden/record.sh`、`test/gate-channel.sh`、`test/lease-channel.sh` 不占住当前回复：先写第 1 条那一句，再放后台，结束再报结果。

## 证据

计数来自本仓两次内核会话转录，方法是按 `<user_query>` 分段，数「第一条带正文的助手消息之前，有多少条助手消息带工具且没有正文」。转录没有每条命令的墙钟。

| 事实 | 数 |
|---|---|
| [架构审查与工程化](885410f1-cd55-46c6-87b4-2724a893f692) 助手消息 / 其中只有工具 | 298 / 263 |
| 同上，连续无正文最长，以及超过 5 个回合的段数 | 36；18 |
| 13:05「继续优化 idev 达到大规模工程化生产可用级」重开后，首句前的无正文回合 | 35，且全是 `Grep` / `Read` |
| 14:21「继续优化」到 14:34 平台插入 `Briefly inform the user` | 13 分钟；该问 72 次工具，38 条助手消息里 4 条有正文 |
| 「确认各 agent 都能正常调起」的 shell 次数 | 39，含多批 `claude -p --agent idev-*`，`block_until_ms` 120000 |
| 收尾 `agent -p` 的 `block_until_ms` | 180000 |
| 自检类命令的 `block_until_ms` | 120000 或 180000 |
| 存活子会话正文 | 一行 `ALIVE idev-coder`，`turn_ended: success` |
| [签字流程收简](6fe663dc-1fe2-4573-8752-a0751dc919c2) 20:08–20:25 | 119 次工具，连续无正文最长 24 |
| `store.go` 在 schema 版本已不低于内嵌迁移时跳过 `goose.Up`；`busy_timeout` | 5 秒。对不上 35 个无正文回合 |
| `leasesvc` 默认租约 | 30 分钟。这两份转录的命令里没有 acquire 卡住 |

## 要改什么

正文只写一处，其它页留指针。

| 落点 | 写什么 |
|---|---|
| `SKILL.md` | 新增短节「回合预算」，写入上面五条定案。不把「是否把多次只读并进一条消息」写成通过/失败条件 |
| `references/agents.md` | 一行指针：执行者直接被点名时同样守回合预算，正文在 `SKILL.md` |
| `references/agents-playbook.md` | 「不要这样用」加一行：聊天里用 `claude -p` / `agent -p` 做存活探测，以及无正文连续超过 8 个回合 |
| `references/agent-accuracy.md` | 在「批量只读探测」下加一句：批量仍不是门禁；机检数的是首句前的无正文回合 |
| `scripts/turn-budget.py` | 读一份 jsonl。按 `<user_query>` 分段。任一段的首句前无正文工具回合大于 `--max`（默认 8）则退出码 1，并打印段摘要与计数。等于 8 通过 |
| `test/fixtures/turn-budget/` | 红夹具：9 个无正文工具回合后才有正文。绿夹具：一条 `ALIVE`、零工具 |
| `scripts/agent-smoke.sh` 或 `scripts/selfcheck.sh` | 只跑上述夹具的红绿。不读 `~/.cursor/projects/` 下的真实转录 |
| `references/changelog.md` | 落地时记一条 |

`schema_version` 不升。`state/ledger.yaml` 的 `phase` 不改。落地时 `conductor_revision + 1`，本文件 `status` 改为 `landed`。

## 不改什么

- 不并行多开执行者。`conventions/canon.md` 仍把「多开几个 Agent 就快了」列为反模式，串行委派保持。
- 不改 `internal/adapters/store/sqlite/store.go` 的迁移跳过，也不改 `busy_timeout`。
- 不改租约 TTL。出现 acquire 后不释放，再另开提案。
- 不把批量只读做成门禁（`references/agent-accuracy.md` 已写明原因）。
- 不把历史转录路径写进自检必跑项。自检只跑仓内红绿夹具。

## 验收

- `turn-budget.py` 对红夹具退出码 1，输出里有 9。
- 对绿夹具退出码 0。
- 落地后的下一次内核改动：第一句用户可见正文出现在第 8 个工具回合之内；跑自检之前先有一句命令、预算、在等什么。
