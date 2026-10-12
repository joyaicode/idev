# 提案 P6：综合缺陷修复与改善（评定闭环）

- status: landed
- scope: 门禁补齐 / 后半段冒烟 / 遵从可观测 / 冷启动减负 / 可移植 / 自进化 SLA
- created: 2026-10-01
- landed_at: "2026-10-01"
- confirmed_by: wangwei794
- confirmation: "修复所有缺陷，然后按改善建议进行调整"
- signal: 人工综合评定 + P1 实证空洞

## 诊断对照

| 缺陷 | 本提案动作 |
|------|------------|
| P0 后半段实证空洞 | 补 `aligned/done` 门禁；加 `late-lifecycle-smoke`（test→promote→ops→伪造 aligned 拒）；**不伪造**真实产品票签字 |
| P1 冷启动过载 | agent-brief 钉死两页冷启动；三模块 SKILL 顶加「本阶段 5 步」；check-feature FAIL 带 HINT |
| P2 可移植未验 | Linux systemd 模板 + `second-product-smoke.sh` |
| P3 产线耦合观感 | 不扩 joypaas 词；第二产线冒烟走 generic |
| P4 摩擦 / 进化慢 | evolve-curator 14d→`stale`；evolve-review 把超龄 draft 当硬信号；audit 软信号 grill-not-opened |
| lite-change 无 trace | 本轮真实跑 preflight 路径并 append 诚实 trace |

## 要改

1. `check-feature.py`：`aligned: true` 或 `stage: done` 须人名 `by`；`done` 须 `aligned: true`；FAIL 末尾打印 HINT
2. `scripts/late-lifecycle-smoke.sh` + 挂入 healthcheck / refs-check
3. `audit_traces_lib.py`：S1 未打开 grilling → 软信号 `grill-not-opened`（进 MUST_ZERO，不进 HARD）
4. `evolve-curator.sh`：`--stale-days` 默认 14，标 `stale`；原 `--days` 30 仍 archive
5. `evolve-review.sh`：超龄 draft/stale 提案计入 signal
6. `agent-brief` / 三模块 SKILL / `skill-details` / `self-evolution` / `portability-checklist` / `changelog`
7. `scripts/second-product-smoke.sh` · `references/linux-schedulers.md`
8. P1 提案改为 `partial`：门禁冒烟已覆盖；真实产品票 done 仍等人确认

## 不改

- 不伪造任何产品仓 `aligned`/`sealed`/`accepted`
- 不加分数门禁、不加第二顶层 Skill、不自动 seal
- 不把 JoyPaaS UI 配方写回内核 description

## 验收

- healthcheck PASS；lite-change WARN 消除（有诚实 trace）
- late-lifecycle-smoke PASS（含 promote 拒 FAIL、aligned 拒 agent by）
- selfcheck 仍绿（补 aligned 负例）
- refs-check 登记新脚本
