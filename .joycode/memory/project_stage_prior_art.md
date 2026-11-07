---
name: 阶段入口已过闸经验注入
description: 2026-11-07 已过闸经验/程序同时进入阶段入口与委派包，候选不进执行上下文
type: project
---

2026-11-07 落地 `state/proposals/20261107-stage-prior-art.md`：`scripts/lib/prior_art.py` 统一既往召回，`session-context.py` 输出 `PRIOR` / `PRIOR_NOTE`，`workflow.py` 委派包复用同一读取器并保持 `既往:` 行为。

**Why:** 阶段入口与执行者冷上下文都读不到这张票已经确认的经验；只把召回放进委派包会漏掉单人自做步骤。候选结论一旦以上下文身份进入，会把一次局部错误变成系统性错误。

**How to apply:** 只自动带出 `lessons.py` 的 `authoritative` 与 `sediment.py` 的 `kept`；candidate / retired 不进执行上下文。`PRIOR` 是约束、边界和证据指针，不是答案，采纳与否仍看本轮证据。内核台账在 `state/`；PyYAML 缺失时既往召回安静降级，不阻塞阶段入口。证据见 `state/traces/20261107-002.yaml`。
