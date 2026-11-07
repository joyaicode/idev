---
name: 阶段专家唯一权威指导
description: 2026-11-07 experts.md 收敛产物质量/效率路径/拒过清单，五执行者同读，stage-gate --list 输出真实规则 ID
type: project
---

2026-11-07 落地阶段专家指导最小升级：`deliver/references/experts.md` 声明为各阶段专家指导唯一权威落点，每个阶段补「产物质量 / 效率路径 / 拒过清单」三段读法；五名执行者与 `deliver/SKILL.md` 均按这三件套触达。`stage-gate.py --list` 从只列阶段名改为输出真实规则 ID，`agent-smoke.sh` 锁住代表性规则。

**Why:** 旧表已覆盖专业拒过下限，但执行者只被点名“拒过清单”，质量和最快可信路径分散在各阶段页；`--list` 承诺列出各档检查却只打印阶段名，降低触达率。另建第二份专家页会破坏唯一真源。

**How to apply:** 阶段工作先按 `experts.md` 对应行的效率路径取证和收敛，再检查产物质量，最后过拒过清单；`experts.md` 低于人本轮明确话与内核硬规则。不要新增专家角色、编号、评分、第二门禁或第二权威页；可机检半边只认 `stage-gate.py`，结构性检查不重复搬进它。验证：`stage-gate --list`、`syntax-check`、`trigger-check`、`selfcheck` 全部 PASS（2026-11-07）。
