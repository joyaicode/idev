---
name: 精读可达审计阶段范围口径
description: 2026-11-07 deep-read-audit 展开阶段页全表范围，F2/F5/F6 进入自然阶段
type: project
---

2026-11-07 落地 `state/proposals/20261107-deep-read-stage-ranges.md`：`deep-read-audit.py` 把阶段页中的 `A1–A8` / `P1–P19` / `C1–C31` / `R1–R7` 展开为全表 `staged`；F2 进入 deliver 的依赖决策，F5 进入 verifier 的断言纪律，F6 进入 coder 的结构改动护栏。

**Why:** 原审计只认两端字面编号，把阶段页已经要求的整表扫描误报为「只有记账」；而真正缺阶段落点的是 F2 / F5 / F6 三个失败模式。

**How to apply:** 后续跑 `python3 scripts/deep-read-audit.py --all-books` 时，不要为提高可达率把 C/P/R 逐个塞进阶段页；全表范围和逐节扫描已算 staged。若出现新的只有记账编号，先判断它是否有自然阶段或明确代码形状，再决定阶段化或插件化。满额可达只表示 trigger / staged / enforced 至少一层可达，不表示全部可机检。
