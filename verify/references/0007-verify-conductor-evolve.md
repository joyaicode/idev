# 证据导体试运行：评估可数、反馈进inbox、拷问后才改 Skill

`idev/verify` 在 `phase: trial` 必须可评估、能收反馈，并且**自进化不是自行改文件**。改进先写成提案，按 grilling 对齐后再落地。禁止分数门禁和 LLM 自评盖章。

## Considered Options

- **每次反馈直接改 SKILL.md**：把一次对话的脾气写成四仓规则。拒绝。
- **Darwin / LLM 打总分当进化门禁**：和「完成=证据、AI 不能当批准人」冲突，且 LLM-as-judge 接近随机。拒绝。
- **另做进化平台或平行 Skill**：违反「不建平行 AI 流程」。拒绝。
- **试运行也闭反馈口**：无法修正导体自己的漏影响面 / 假绿。拒绝。

## Consequences

- 评估只计 `conductor-eval` 件数 + 诚实性检查，写在当次 `report.md`。
- 反馈标签是登记表。产品会话的 inbox 在该工程 `.idev/inbox/`；没有当前产品时才在内核 `verify/state/inbox/`。
- 落地只改真源 `~/.cursor/skills/idev/verify/`（检查脚本受影响时改 `idev/scripts`）。不要写回产品仓。不兼容升 `schema_version` 并写本机 ADR 副本。
- `phase: ga` 必须再拷问一次，不能因「用过几次」自动转正。

契约：[evolve.md](evolve.md)

在线复盘与 nudge 映射见入口 [references/self-evolution.md](../../references/self-evolution.md)（`evolve-review.sh` / S8 `self-evolve-review`）；仍须 grill + 人确认才 land。
