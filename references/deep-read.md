# 审计解读与深读（速查长段）

每轮先看 [operator-cheatsheet.md](operator-cheatsheet.md)。本页只在审计报警或 opened 跨模块时打开。

## 审计怎么跑

默认看**滚动最近 50 条**，不回填历史债。

```bash
bash ~/.cursor/skills/idev/scripts/audit-traces.sh 50
bash ~/.cursor/skills/idev/scripts/install-weekly-audit.sh
# S8：weekly-trace-audit
```

| 报警 | 含义 | 通常处理 |
|------|------|----------|
| 缺 scenario | 没记 S1–S8 | 补路由习惯 |
| **同轮多模块执行 calls** | calls 跨 deliver/verify/ops | 收敛到单模块；拆两轮 |
| 仅 opened 多模块（深读） | 单执行 + 邻接只读 | **允许**（见下） |
| calls 弱/空 | 无可核验调用 | 补真实 calls |
| 疑似写入签收但无 signoff | 写了 sealed/accepted/aligned 却无确认块 | 补 `signoff` 或改掉伪造写入 |
| **阶段页未写入 opened** | trace 有 `extensions`，其中路径不在 `opened` | 把 `OPEN` 行抄进 `opened` 后再请签 |
| **有标记的产品 trace 缺 extensions** | 产品仓 `.idev/traces/` 的 trace 没有 `extensions` 字段 | 补 `extensions: []` 或本轮 `OPEN` 路径 |
| 仅否定/描述签收词 | 「不写 aligned / 他票仍 sealed」 | **不算违规** |

本轮若写入签收字段，trace 必须带：

```yaml
signoff:
  status: recorded
  marks: [accepted]
  by: "<人名>"
  evidence: "<确认原话或 YAML 路径>"
```

## 多模块 opened：允许深读 vs 应收敛

先看 **route.module** 与 **calls**，不要只看 opened。

**口诀：** 一个 `route.module` + `calls` 只服务该模块（外加只读边界）→ 允许。

| 允许深读 | 条件 |
|----------|------|
| S4 对照阅读 | `route.module=conventions`；calls 不做阶段推进 |
| 边界只读 | 执行 calls 只落在当前模块；不写邻接工件 |
| 改 idev / 新配方提案 | 本轮不落仓内票；不并行执行 verify/ops |
| 入口短页 | 打开 `idev/SKILL.md` + 当前模块 |

| 应收敛 | 为什么 |
|--------|--------|
| 同轮 calls 同时 deliver 执行与 verify 执行（非 handoff） | 违反每轮一个执行模块 |
| 为以防万一打开 deliver+verify+ops 全文 | 易误触签字/推阶段 |
| S2 推 deliver 时又改 verify plan / 跑 promote | 场景混用；拆两轮 |
| opened 很多却说不清为什么 | 补 why，或删无关 opened |

落地：opened 可以多，**calls 必须单执行模块**（handoff 除外，须在 decisions 写明）。每多开一个邻接 `*/SKILL.md`，decisions 写一句为什么只读。周审计只把「calls 跨多执行模块」当报警。

样本（2026-09-18）：049 / 032 / 022 均为允许深读（calls 单模块）。

路径一眼看清：`bash ~/.cursor/skills/idev/scripts/path-view.sh` / `path-view.sh stats`（无分数）。
