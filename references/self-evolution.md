# idev 自进化（Hermes 对齐，人确认才落地）

对照 [Nous Research Hermes Agent](https://github.com/NousResearch/hermes-agent) 的**在线闭环**与 hermes-agent-self-evolution 的**离线轨迹进化**，把可复用模式落到 idev，**不照搬** DSPy/GEPA 栈，也**不**用 LLM 打分当门禁。

权威契约仍是 [verify/references/evolve.md](../verify/references/evolve.md)：propose → grill → land → ga。本页补的是**何时自动起草稿、如何复盘、如何归档**，不是绕过拷问。

## Hermes → idev 映射

| Hermes 模式 | idev 落地 | 禁止 |
|-------------|-----------|------|
| Skills from experience | 产品仓会话的草稿写 `<repo>/.idev/proposals/`。人说「提升到内核」且 `kernel-promote-check.sh` 通过后，才进内核 `state/proposals/` | 直接改 SKILL.md；把产品草稿原样抄进内核 |
| Patch skills in use | 提案里写「要改什么 / 不改什么」；land 后改真源 | Agent 静默 patch 真源 |
| Curated memory + nudge | `state/reviews/` + inbox + 本页 nudge 规则 | 把一次聊天脾气写成规则 |
| Background review cadence | S8 `self-evolve-review` / `scripts/evolve-review.sh` | 无人确认就 land |
| Curator archive unused | `scripts/evolve-curator.sh` 标 `archived`（可 `--apply`） | 静默硬删提案 |
| Human approval on skill write | grilling + 确认用语 | 分数门禁 / LLM 自评盖章 |
| Offline trace→skill (GEPA) | `evolve-review.sh` 只产出**提案草稿** + 证据链 | 自动写生产 / 自动 commit Skill |

## 自净化发现试点

产线用 idev 做交付之后，idev 会在该工程 `.idev/marker.yaml` 写下 `marker: idev`。自净化扫描到 `evolve: pilot` 的仓，把它们纳入自进化。发现脚本：`scripts/lib/product_marker.py --from-install`。扫描范围是 `IDEV_DISCOVER_ROOTS`，以及本机安装记录里 `product_root` 的相邻目录。这不把安装记录当成当前会话的产品。

`evolve-review.sh` 对每个试点只记 HARD 计数。该仓的 trace、提案、复盘仍在它自己的 `.idev/`。内核收据不抄试点正文。

## 在线闭环（每轮可走）

```
执行(S1–S8) → 写 trace / 收 feedback
     ↓
nudge（有信号才提醒，不刷屏）
     ↓
propose 草稿（脚本或人手）→ grill → 人确认 → land 真源
     ↓
curator：过期未落地提案 → archived（不硬删）
```

ReAct 关节用尽（`react-exhausted`）或工具失败（`react-tool-fail`）各写一条 inbox，note 带 step、工具名和观察摘要。热标签规则与上面相同：同类非 ok ≥ 2 才问要不要写提案。不改权重，不改配方。

### Nudge（硬）

在以下**任一**成立时，Agent **一句话**问要不要写成提案（不自动写 Skill）：

1. 本轮修了导体缺口 / 假绿 / 步骤含糊，且尚未有对应提案  
2. inbox 里同一非 `ok` tag ≥ 2  
3. `audit-traces` 本窗 HARD_COUNT > 0，或 healthcheck/selfcheck 新 WARN/FAIL 指向 Skill 文案  
4. 人说「进化 / 自进化 / 沉淀 / 把这次写进 skill」

**不算 nudge：** 纯 banter、单次 `ok` feedback、已 landed 的重复话题。

Nudge 话术示例：「这次踩到 X，要不要我按 evolve 写一条提案草稿？」人说要才写。

### 背景复盘（S8）

原话含「自进化 / 进化复盘 / evolve review / hermes 复盘」→ S8 `workflows/self-evolve-review.yaml`。  
产品 UI 剧本（inventory / wave / 覆盖锁）的建设与进化走产品仓 `.idev/workflows/` 里的 S8 配方，不要和导体进化混用。

脚本：`bash ~/.cursor/skills/idev/scripts/evolve-review.sh`  
只读 traces / inbox / reviews / 未落地提案 → 写出一份 **draft** 提案（或「无信号」收据）。**绝不**改 SKILL / schema / ledger.phase。

**信号（硬）：** 仅 `HARD_COUNT>0` 或 inbox hot tag（同类非 ok ≥2，且未 `consumed`）。reviews 里的缺口关键词只作软提示（默认最近 7 天，`--review-days`），**单独不抬 signal**。

### Curator

`bash ~/.cursor/skills/idev/scripts/evolve-curator.sh`  
默认只打印建议；`--apply` 才改状态（不硬删）。

| 年龄 | 动作 |
|------|------|
| ≥ `--stale-days`（默认 14） | `status: stale`（仍打开，催 grill） |
| ≥ `--days`（默认 30） | `status: archived` |

`evolve-review.sh` 把 **stale / 超龄 draft** 计入硬信号（与 HARD / inbox hot 并列），避免提案永久草稿。

### 清理执行产物

`bash ~/.cursor/skills/idev/scripts/execution-clean.sh`  
默认只打印将删除的文件。`--apply` 才删除。对象只是当前产线 `.idev/` 里的执行残留（没有当前产品时才是内核 `state/`）。删除前把一行摘要写入 `.idev/memory.md`。

时间窗（不带 `--compact`）：

- `traces/`：最新 50 条一律保留；更老且超过 30 天的删
- `reviews/`：文件名含 `latest` 或 `status.env` 的保留；其余超过 30 天的删
- `inbox/`：只删 `status: consumed` 或 `archived`、且超过 30 天的

整理（`--compact`，真实 `evolve-review` 结束时自动 `--apply --bump`）：

- 热集合：最新 20 条 trace、带 `latest` 或 `status.env` 的复盘、未消费 inbox、仍打开的提案
- 热集合以外的文件，被其它复盘或提案以 `traces/<file>` 这种路径点名满 **2** 次，就折进摘要并删除
- 距上次整理满 **3** 代（每次真实复盘 `--bump` 一代），把热集合以外的残留和已关闭提案折进摘要并删除
- 摘要在 `.idev/memory.md`，纳入版本库。产品 `.gitignore` 使用 `.idev/*` 时要保留 `!.idev/memory.md`

不碰 `docs/task/`、`.idev/task/`、`.idev/docs/`，不碰仍打开的提案，不碰 `marker.yaml`、`pack/`、`workflows/`、`handoff.yaml`、`extensions.yaml`、`checks/`、`strip-tokens.txt`、`memory.md`。`--days`、`--keep`、`--hot`、`--cites`、`--generations` 可改窗口。Curator 仍然只把超龄提案标成 `archived`，不直接删文件；已关闭提案等整理代次到了再摘要后删除。

## 离线进化（v1 范围）

v1 **不做** GEPA/DSPy 自动改写。离线 = 定期跑 `evolve-review.sh`，把轨迹与反馈压成提案，仍走 grill + 确认。

定时安装（Mac LaunchAgent，周六 10:15，紧接周审计 10:00）：

```bash
bash ~/.cursor/skills/idev/scripts/install-weekly-evolve.sh
```

产物：`state/reviews/evolve-review-latest.md` + `evolve-review-status.env`（`signal=`）。有硬信号才写 draft 提案；**不**自动 land Skill。对话提醒靠 Bot 例行任务读 status（无信号则保持安静）。

若未来加模型辅助改写：只能改提案正文，且必须过 selfcheck/healthcheck；**禁止**把模型分数写进台账或当 land 条件。

## 提案路径（钉死）

| 范围 | 目录 |
|------|------|
| 某个产品上的进化草稿 | 该工程 `.idev/proposals/`（须已有 `marker: idev`） |
| 导体改内核自己、且没有当前产品 | `~/.cursor/skills/idev/state/proposals/` |
| 仅 verify 导体契约 | `~/.cursor/skills/idev/verify/state/proposals/` |

`evolve-review.sh` 跟当前会话走：产品仓写该工程 `.idev/proposals/` 与 `.idev/reviews/`；没有当前产品时才写内核 `state/proposals/`。verify 导体契约仍按 evolve.md，且只在改内核自己时进 `verify/state/proposals/`。

## 与周审计的关系

| 能力 | 脚本 / 配方 | 产物 |
|------|-------------|------|
| 纪律抽检 | `audit-traces.sh` / `weekly-trace-audit` | HARD 计数 + 样本 |
| 自进化复盘 | `evolve-review.sh` / `self-evolve-review` | 提案草稿或无信号收据 |
| 提案治理 | `evolve-curator.sh` | archived 标记 |

周审计发现 HARD 后，下一刀应是 evolve-review（或人手提案），不是直接改 Skill。

## 验收

- selfcheck / healthcheck 仍绿  
- 无自动 land  
- 人可用「确认」走 grill 后 land；未确认则 Skill 字节不变  
