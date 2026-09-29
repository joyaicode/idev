# 功能：证据导体（自测 / 排障 / 验收 / 巡检）

开发验证、排障复现、自测、测试验收、日常巡检共用一条循环：人确认范围 → 跑可执行用例 → `PASS`/`FAIL`/`UNPROVEN` → 需求/设计/架构由人签字。  
v1 没有独立 CLI；Agent 走 Skill，脚本只做 `promote` / `clean`。

> 模块：`~/.cursor/skills/idev/verify/SKILL.md`（入口 `idev`）  
> 契约 / 怎么扩展：[plan-schema.md](plan-schema.md)  
> 试运行评估 / 进化：[evolve.md](evolve.md)  
> 决策：[0006](0006-verify-conductor.md) · [0007](0007-verify-conductor-evolve.md)  
> 排障硬规则：[conventions/evidence.md](../../conventions/evidence.md)

本机实验。正式用例仍进 `*Test` / `*IT`。交付走 deliver 模块。投产后排障走 ops 模块（本模块提供 `debug` / `patrol`）。

## 何时用

| 场景 | mode | 入口 |
|------|------|------|
| 对着 diff 看刚改的逻辑 | `logic` | diff + 目标/非目标 |
| 自测正确性 + 影响面兼容 | `selftest` | 同上 |
| 查问题、复现猜想、钉根因 | `debug` | 现象 + 哪套环境/产物 + 可观察物 |
| 测试阶段按维度验收 | `test` | 上两者之一；全维度，缺基线只能 `UNPROVEN` |
| 抽查回归 | `patrol` | 已登记巡检包（`doc_home.py --key patrol`），无包拒跑 |

不要整仓漫游当入口。不要让 AI 盖「全面通过」。  
前端请求要登录态：先走当前产品 `.idev/handoff.yaml` 里的取 Cookie Skill，再跑 `frontend-http`。

## 四步

1. 给人 `feature` slug。有密封基线则 goal/non_goal 复制基线；否则人写。
2. Agent 写 `<票目录>/verify/plan.yaml`，`accepted: false`。起草或调整 `cases[]` 后、请人勾选前跑 `check-feature.sh <feature> verify-plan`。人勾选用例和影响面并改 `accepted: true`，或回复确认用语全签（[chat-confirm-signoff.md](../../references/chat-confirm-signoff.md)）。
3. Agent `run`：只认 `plan.accepted`；只跑勾选的 runner。**不跑 `verify-plan`，不请签。** 日志在模块 `target/verify/`；同目录出 `report.md`。
4. 人要巡检包或留下生成测试：`bash ~/.cursor/skills/idev/verify/scripts/promote.sh <feature>`。清一次性测试：`clean.sh`。
5. **入口直接落到本模块且 trial：** run 后填导体 `feedback.yaml`。**由 deliver / ops 调用时**不为进化再停。改本模块只动 `~/.cursor/skills/idev/verify/`。

生成测试只许待在 `src/test/java/**/generatedverify/`。禁止 `git add` 该目录。

## 报告里能写什么

| 可以 | 不可以 |
|------|--------|
| 某 case `PASS`/`FAIL` 并挂日志路径 | 「架构达标」「性能达标」而无对应绿 case |
| 某维因无基线 / 未确认而 `UNPROVEN` | 分数、全面验收通过 |
| `human_signoff` 仍 `PENDING`，等人改 YAML 或确认 | 无确认用语却写成 `ACCEPTED` |

## 扩展与修正

- **加 mode / 维度 / 运行器**：只改 [plan-schema.md](plan-schema.md) 登记表。
- **改已锁语义**：ADR + `schema_version + 1`。旧 plan 未知 id 当 `UNPROVEN`，不改写历史 `evidence`。
- **以后抽 CLI**：只实现 schema 的读写和 runner 表；不要第二套状态机。
- **浏览器 / 压测**：先有 `baseline_ref` 再加 runner kind；没有对照物仍是 `UNPROVEN`。
- **试运行反馈 / 进化**：只改 [evolve.md](evolve.md) 与本机 Skill。

## 产物落点

| 产物 | 路径 | 进 Git？ |
|------|------|----------|
| plan / report / feedback | `<票目录>/verify/` | 是 |
| 导体台账 / inbox / 提案 | `~/.cursor/skills/idev/verify/state/` | 否（本机实验） |
| 巡检包 | `doc_home.py --key patrol` | 是 |
| 运行日志 | `{module}/target/verify/` | 否 |
| 一次性测试 | `**/generatedverify/` | 否 |

禁止 `.scratch/`。测试设计长文仍用 `doc_home.py --key test-case` 输出的那份。

## UNPROVEN 面

`mode=test` 提测前必读 [unproven-gate.md](unproven-gate.md)。沉默的未覆盖面 = 拒过。
