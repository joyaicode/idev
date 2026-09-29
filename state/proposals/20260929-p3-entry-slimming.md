# 提案 P3：入口瘦身（降低 agent 冷启动出错率）

- status: landed (2026-09-29, 人要求「修复问题」)
- scope: SKILL.md / operator-cheatsheet.md / agent-brief.md / invoke.md
- created: 2026-09-29
- signal: 人工审计；违反自身「降低认知负荷」目标

## 诊断（证据）

Skill 自称「降低认知负荷，先看速查页」，但正确路由一次需要 agent 吃透多页，且同一规则在多页重复维护，有漂移风险：

1. `operator-cheatsheet.md` = 203 行，已不「速查」；本身又指向 s1-vs-s8 / deep-read / lite-change-pitfalls / scope 四篇长文。
2. **决策树三处各一份**：`SKILL.md`、`cheatsheet §0.5`、`invoke.md §路由速查` 都有一张 S1–S8 路由表。SKILL.md 已声明「本页决策树是路由唯一权威，其它页只是摘要」——但三份手工同步，任一改动漏改就分叉。
3. **H1–H6 全文出现在 4+ 页**（agent-brief / invoke / cheatsheet / skill-details），`invoke.md` 是声明的唯一权威，其余是复述。
4. 认票逻辑在 SKILL.md / agent-brief / cheatsheet / invoke 各写一遍（措辞略有差异）。

后果：新接手的 agent 或人，冷启动成本高；多副本增加「改一处忘另一处」的漂移面。

## 要改什么

思路：**唯一权威页保留全文，其余页改为「一句话 + 指针」，不复制表格。**

1. **决策树**：只在 SKILL.md 保留完整表；cheatsheet §0.5、invoke §路由速查改为「路由以 SKILL.md 决策树为准，见 [链接]」+ 最多 3 行最常用摘要，删除完整重复表。
2. **H1–H6**：只在 invoke.md 保留全文表；其余页引用「见 invoke.md H1–H6」，不重列六行。
3. **认票**：只在 invoke.md §认票 保留 5 步；其余页一句话「认票见 invoke.md」。
4. cheatsheet 目标行数从 203 压到 ~120（删重复表后自然瘦）。

## 不改什么

- SKILL.md 55 行入口结构（已足够精简，是权威）。
- agent-brief.md 的「最小执行回路 / 冲突听谁 / 编号只认一处」——这是 agent 的真入口，保留全文。
- 任何硬规则的**语义**（只去重复副本，不改规则本身）。

## Grill 要点（land 前必答）

1. 去重后，agent 单页路由时会不会因「摘要太薄、又要跳权威页」反而增加跳转成本？摘要保留几行是最优？
2. cheatsheet 定位到底是「self-contained 速查」还是「指针目录」？两者要求相反，必须先订死一个。
3. 三处决策树是否**当前就已存在语义分叉**？（land 前先 diff 三张表，若已分叉，先记录哪份为准。）

## 验收

- SKILL.md / agent-brief / invoke 的权威内容零删减。
- 决策树、H1–H6、认票各只有一份全文，其余是指针。
- refs-check / healthcheck 仍绿（链接不断）。
- 抽查：新 agent 只读 agent-brief + SKILL.md 能否完成一次正确路由（人工验证）。

## Grill 结论（落地时）

1. 摘要保留三行。认票与 H1–H6 必须打开 invoke，用一次跳转换掉行为分叉。
2. 速查订为指针目录加命令，不是自洽路由表。
3. 落地前已经分叉：agent-brief 认票少「最近一条 trace」；速查 H3 少「deliver/ops 调用 verify 不问」；速查把线上现象排在新需求前，invoke 的 S6 还写成「巡检、回退」。以 `SKILL.md` 决策树和 invoke 的认票 / H1–H6 为准。

## LAND 记录（2026-09-29）

认票五步与 H1–H6 全文仍只在 invoke，没有删步骤。删掉的是第二、第三张场景表，以及 agent-brief 里少一步的认票。决策树补了「本轮确认当前停问点」「clean」「done 后不改 goal」和「配方命中」。`coding_root` 改由 `packs/joypaas/workflow-defaults.yaml` 提供。后半段真实票里程（P1）这次没有跑。
