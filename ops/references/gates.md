# 请人签字前（ops）

先跑 `bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> ops`（内含 `outbound-skills-check.sh --repo <仓根>`）。当前产品 `.idev/marker.yaml` 为 `marker: idev` 且有 `handoff.yaml` 时，缺其中 required Skill 即 FAIL。没有标识就不要求任何产品的 Skill。  
脚本或本表有一条 `FAIL` 不准写 `resolved` / `defect_origin`（含对话确认代写）。

- [ ] 现场四件齐：现象 / 环境 / 产物 / 可观察物
- [ ] `kind` 已定；`unknown` 不准关单
- [ ] `onboard` / `runtime` 已写 `handoff` 且已换 Skill，不在本单改业务
- [ ] `outbound-skills-check.sh` PASS；缺失则不准关 `onboard`/`runtime` 单，只许手写 handoff 停单
- [ ] `feature`：原现象至少红过一次；根因能红/绿；`suspect_item_ids` 都在基线里
- [ ] 未确认 origin 不准回退；未 reopen 不准改 baseline
- [ ] 没有对生产做写操作
- [ ] `by:` 是人名，不是 agent；回退确认句须带 `origin=`
