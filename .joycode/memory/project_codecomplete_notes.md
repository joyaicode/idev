# 《代码大全》精读收口

- 2026-11-07 完成《代码大全》第一版中译全书第 1–33 章精读，是第十本；原始提取件为 `scripts/docs/notes/代码大全-全文.txt`（不入库）。
- 精读报告：`scripts/docs/notes/代码大全-精读缺口.md`；提案：`state/proposals/20261107-conventions-codecomplete-gaps.md`。
- 真缺口 1 条：C2 增补 `case/default` 未列值不得伪装成合法缺省；`default` 只承载显式合法缺省，否则报未知值。改既有行，不新增编号，不动 §3.5 与 canon §2/§4。
- 主体结论：信息隐藏 / 深模块归 T3/T4，防错性编程归 T8/C7/C13，命名归 T5/C12，全局数据归 T14，控制结构归 C1/C9 与圈复杂度 ≤10，测试 / 调试归 T6/C26/rootcause-guards，性能归 T9；语言级断言、防火墙多重消毒、最近改动启发式、错误集中 80/20、PDL / 布局、代码调整目录、项目管理与性格叙事均不落。
- 验证：`python3 scripts/deep-read-audit.py --report scripts/docs/notes/代码大全-精读缺口.md` PASS，33 个编号中 22 个到达代码层（trigger / staged / enforced 任一层）。
- 注意：这是第一版，不是第二版；后续再遇到《代码大全》建议先查本报告第四节，避免重复发现已裁定不落的语言 / 流程细节。
