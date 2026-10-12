# 提案 P1：后半段生命周期补里程（test → aligned → done → ops/promote）

- status: landed
- landed_at: "2026-10-01"
- landed_note: "真实票 joypaas-approval-pre-post-check → stage=done aligned=true by=wangwei794"
- scope: 非 idev 源码改动——需在真实产品仓跑一个完整票；idev 侧门禁/冒烟已由 P6 覆盖
- created: 2026-09-29
- updated: 2026-10-01
- signal: 人工审计；后半段实证空洞

## 诊断（证据，非主观）

前半段（req-review→arch→code）有真实产物背书，后半段几乎无真实里程（2026-09-29 审计）：

1. JoyPaaS 真实票停在 arch/code，无票到 done。
2. 无完整 ops.yaml / promote 从 accepted plan 快照的背书链。

## P6 已补（内核侧）

- `check-feature`：`aligned: true` / `stage: done` 须人名 `by`；FAIL HINT。
- `late-lifecycle-smoke.sh`：fixture 打穿 test → promote（拒 FAIL / 收 PASS）→ ops → 拒 `by: agent`。
- **仍缺：** 真实产品仓一张票走到 `aligned=true` + `stage=done`（须人确认用语，禁止伪造）。

## 剩余要做（跑票）

选接近完成的产品票，人确认后推完后半段。不为跑通伪造 aligned。

## 验收

- [x] 真实票 joypaas-approval-pre-post-check stage=done / aligned=true / by=wangwei794（2026-10-01）
- [ ] 可选 promote / ops.yaml（人未提则不做）

## 曾列剩余（已关闭主项）

- 至少 1 个真实产品票 `stage=done`（aligned=true, 人 by）。
- 可选 promote + ops.yaml 真实现象一条。
