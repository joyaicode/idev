---
name: 全量精读可达审计与测试阶段落点
description: 2026-11-07 deep-read-audit --all-books 已落地，C26/C28–C30 进入 verifier 起草步骤
type: project
---

2026-11-07 落地 `state/proposals/20261107-deep-read-all-books.md`：`scripts/deep-read-audit.py --all-books` 只审计 `scripts/docs/notes/*-精读缺口.md`，输出每份报告的可达数与全局「只有记账」编号；`agents/idev-verifier.md` 在 verify.plan 维度骨架后扫描 C26 / C28 / C29 / C30。

**Why:** 12 本书已读完，若只在编号表里记账，执行者冷上下文仍会在起草用例时漏掉测试套件质量经验；同时 DDD 逐章笔记的局部 F 编号不能被误当真源编号。

**How to apply:** 后续判断书摘是否需要重炼化时先跑 `python3 scripts/deep-read-audit.py --all-books`，再看全局只有记账编号；测试气味先由 verifier 阶段页承接，不因可达率低就给 C26/C28/C29/C30 加高误报插件。证据见 `state/proposals/20261107-deep-read-all-books.md` 与 `references/changelog.md`。
