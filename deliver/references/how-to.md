# 端到端交付（评审密封 → 提测）

先 **需求评审（拷问至无异议）** 密封原始需求，再拆解 → 架构 → 编码/自测 → 提测 → 投产后排障。  
后面任何反馈都**不能推翻**已密封基线；验收尺就是这份基线。红绿走 verify 模块。排障走 ops 模块。

> 模块：`~/.cursor/skills/idev/deliver/SKILL.md`（入口 `idev`）  
> 契约：[deliver-schema.md](deliver-schema.md) · [experts.md](experts.md) · [gates.md](gates.md)  
> 决策：[0008](0008-deliver-conductor.md) · [0009](0009-deliver-baseline-seal.md)

本机实验。新产品脚手架走当前产品 `.idev/handoff.yaml` 里的可选 Skill。

## 何时用

| 场景 | 做法 |
|------|------|
| 从诉求做到提测 | 本模块，从 **`req-review`** 起 |
| 只要跑已有变更的红绿 | 入口路由到 verify 模块 |
| 边界不清 / 要不要做某条 | 评审阶段拷问，密封前解决 |
| 后面发现「需求不好」 | `baseline-conflict`：基线内改实现，或人 `reopen_baseline` 再评审 |
| 投产后现象 / 巡检 | 入口路由到 ops 模块：先分类，再 debug 或 handoff |

## 阶段与产物

| 阶段 | 产物 | 人签字 |
|------|------|--------|
| `req-review` | `baseline.yaml` + 人读规格（`doc_home.py --key spec`，只复述） | `sealed: true` |
| `req` | `req.yaml`（挂 `baseline_item_id`） | `accepted` |
| `arch` | `design.md` + `arch.yaml` | `accepted` |
| `code` | 代码 + verify selftest；§1/§2/§3 + §3.8 增强扫描（coding-scan/五轴/栈指南）；`check-feature code` | 自测门 |
| `test` | verify `mode=test` | 提测门 + `aligned` |
| `done` | 基线仍密封 | 人写 `aligned` 或提测停问点确认用语 |
| `ops` | `ops.yaml` + verify debug/patrol | `resolved` / origin |

指针：`<票目录>/deliver.yaml`（含 `risk_tier`）。

## 密封之后

| 能 | 不能 |
|----|------|
| 切片译法、方案、代码、用例 runner | 改 baseline 的 goal / items / boundaries |
| 回退 `req` / `arch` / `code` | 用提测 FAIL 倒逼改原始需求 |
| 人 reopen 后 `revision+1`、旧 id 作废 | Agent 自行 unseal 或复用旧 item id |
