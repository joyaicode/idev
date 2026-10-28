---
audience: AI models and agents that load idev
authority: normative（冲突裁决与最小执行回路以本页为准；细节以被指向的单一权威页为准）
---

# Agent 入口须知（先读这页，1 分钟）

## 冷启动（只读两页）

1. **本页**（回路 / STOP / 冲突 / 编号）
2. **`SKILL.md` 决策树**（认场景 S1–S8）

其它页按场景懒加载：认票/H1–H6 → [invoke.md](invoke.md)；模块步骤 → 该模块 SKILL 顶部「本阶段 5 步」；签字用语 → [chat-confirm-signoff.md](chat-confirm-signoff.md)。**不要**一上来打开 lifecycle / cheatsheet 全文 / 多模块。

## 你是谁、在做什么

你在 idev 里是**人机共驾**的执行者：起草、自测、写报告、跑命令由你做。没有未决分叉就在同一轮接着做。解封、回退、发布仍要点名。你不是无人值守流水线。

## 启用顺序

1. 先激活通用内核（本 Skill、conventions、idev `workflows/`）。
2. 产线仓有 `marker: idev` 时，先跑 `scripts/session-context.py --repo <仓根> --feature <feature> --scenario <S1–S8> --stage <deliver.stage>`。点了产品名就加 `--product`。只打开输出里的 `OPEN` 行，并把这些路径写入 trace 的 `extensions`（没有页就写 `extensions: []`）与 `opened`。交出口、流水线、扩展根的 `workflow-defaults.yaml` 在用到那一步时再读。会话仓写了 `extension_root` 时不要读本仓那份空文件。启用时不整包打开 `pack/`。
3. 本轮又识别出只在这条产线成立的约束时，写入扩展根的 `.idev/pack/`，并在 `.idev/extensions.yaml` 的当前阶段挂上相对路径。对所有产线成立的句子等人说「提升到内核」。写文档前打开 [docs/SKILL.md](../docs/SKILL.md)。还没有 `.idev/` 时，本轮需要保存再创建它。

## 最小执行回路（每轮都走）

1. **认票**：见 [invoke.md](invoke.md)「认票」五步。本页不复述步骤，不要用更短的清单顶替。
2. **认场景**：按 `SKILL.md` 决策树选 S1–S8 之一（**路由以 `SKILL.md` 决策树为准**，其它页的路由表只是摘要）。
3. **只开一个执行模块**（deliver / verify / ops 不同时加载）。
4. **动手前**：写架构方案或改代码先读 [conventions/coding.md](../conventions/coding.md) 文首底线与 §0；涉及“加层/拆分/缓存/队列/重试/重写”先走 [conventions/canon.md](../conventions/canon.md) §1。读代码结构、做根因、写文档小结之前，先 `bash scripts/codegraph-sync.sh --repo <仓根> <reason>`。`reason` 只认 [boost.md](boost.md)「索引何时更新」。
5. **落笔之前两道一起过**：`check-feature.sh`（结构）+ `stage-gate.py --feature <f> --all`
   （七视角拒过清单里可机检的那一半）。两道都过、没有未决分叉，就写下这一关。
   这一格该用哪个工具，看 `SKILL.md` 的「分阶段的能力」索引表，不要凭印象找。
6. **有不清楚处先 grilling**（`~/.cursor/skills/grilling/SKILL.md`）。frontier 空了就落笔，不再请人确认。
7. **记录不是收尾。** `scripts/trace.sh append` 记下这一轮（产品仓进 `.idev/traces/`，导体自身会话才进内核）。`stop` 为空、下一步已由当前阶段决定时，写完立刻做那一步。不把「接着做」留成 `next` 等人说继续。`next` 只在真要停时写：未决分叉、要点名的不可逆动作、或缺了只有人知道的输入。技能调起、委派决定、模型与一行思考按 [trace.md](trace.md) 写上；缺了不挡本轮，不准编造。

## 什么时候必须停下来问人（STOP）

- 检查没过，或还有未决分叉，却要写 `sealed` / `accepted` / `aligned` / `resolved` / `semantic_gate.*.passed`。检查过了就写，不问确认。`reopen_baseline` 仍要点名。P1/P2 的 plan / resolved 机检无信号时写 `auto:`。
- 进入阶段先看 `STAFFING` 行。一个人兼任全部岗位就一次问全。多人只问当前这个人持有的岗位，别人的列成待。岗位还没写明时只问一次岗位表。做法见 [chat-confirm-signoff.md](chat-confirm-signoff.md)。
- 执行者回报出现 `SIGNAL`（`BLOCKED(logic)`、`[承重]` 假设、`ARTIFACT: UNKNOWN`）：按决策包问，答案用 `workflow.py decide` 记。`BLOCKED(domain)` 不是停问：按 [agents.md](agents.md)「角色能力」另派 `DOMAIN` 点名的执行者咨询一次。
- 全表与档位：[chat-confirm-signoff.md](chat-confirm-signoff.md)。
- 要改 goal（必须人说「解除密封」或 `reopen`）。
- 要跑 `promote.sh`、写生产、回退 origin（人没提就不问，也不做；见 H2）。
- 多张 `stage != done` 的票且原话没点名。
- 需要 `product` 的配方而原话没点明恰好一个产品名。

## 什么时候不要停（H1–H6，别为它们请签）

见 [invoke.md](invoke.md)「非门禁不停」。核心一句：**没有未决分叉就在同一轮接着做。检查过了就写这一关。不请人确认，不擅自 promote，不为观测再停。**

## 冲突时听谁（从高到低）

1. **人本轮的明确话**（确认不能改 goal，不能绕过证据优先）。
2. **内核硬规则**：签字、证据、不跳阶段、红绿只走 verify（`SKILL.md` 共享硬规则 + [conventions/SKILL.md](../conventions/SKILL.md) 的硬规则）。
3. **产线规范文档**：交付时打开 [docs/SKILL.md](../docs/SKILL.md)。目录认 setup-agents-docs（Matt Pocock），问句认 grilling。与 `.idev` 同名副本冲突时，规范文档优先。
4. **这条产线的其余取值**：`.idev/` 里还没有被规范文档盖过的路径、服务码、角色、流水线参数。这里不改写第 2 条。
5. **[canon.md](../conventions/canon.md)**（T/A/F 编号，架构与设计判断）。
6. **[coding.md](../conventions/coding.md)**（P/C/R 编号，落到具体代码）。
7. 其余 references / 配方 / 速查页（都是摘要或操作手册；与上面冲突时以上面为准，并把冲突写进 trace 的 `notes`）。

## 编号只认一处（禁止自造第二套）

| 编号 | 含义 | 唯一权威 |
|------|------|----------|
| S1–S8 | 场景 | `SKILL.md` 决策树 |
| H1–H6 | 非门禁不停（旧称 C1–C6，已改名以免与编码气味混淆） | [invoke.md](invoke.md) |
| P / C / R | 模式 / 代码气味 / 重构条件 | [coding-tables.md](../conventions/coding-tables.md) |
| T / A / F | 架构范式 / 出门问题 / AI 失败模式 | [canon.md](../conventions/canon.md) |

## 术语

见 [glossary.md](glossary.md)。遇到不认识的词先查那页，**不要猜**。
