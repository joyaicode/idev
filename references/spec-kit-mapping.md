# Spec Kit 对照与取舍记录

idev 与 [GitHub Spec Kit](https://github.github.com/spec-kit/) 的对照。供查阅「某条能力落在哪 / 为什么没搬」。**本页不是执行页**，执行仍按 deliver / verify / conventions。

命令上的硬约束以 [github/spec-kit](https://github.com/github/spec-kit) 的 `templates/commands/` 为准。文档站说明过程，不代替那些约束。

## 过程对照

| Spec Kit | idev |
|----------|------|
| constitution：后续阶段都对着项目原则检查；原则冲突时改工件，改原则另走显式更新 | [conventions/SKILL.md](../conventions/SKILL.md) 与 [canon.md](../conventions/canon.md)。硬规则 9 |
| specify：只写做什么、为什么；成功标准可测，且不写技术栈 | `req-review` 的密封基线。方案冒充需求见 [req-quality.md](../deliver/references/req-quality.md) §4 |
| clarify：把回答写回规格 | grilling。未决问句只在 `grill.md`。按当前编制一次问完 |
| plan：技术选型写在这里 | `arch` / `design.md` |
| checklist：需求质量清单；实现步骤只读勾选，不得自己打勾 | [semantic-gate.md](../deliver/references/semantic-gate.md)。Agent 不得代勾 |
| tasks：按依赖拆开，每条能追溯到需求 | slice 覆盖 item；`check-feature`；[realign.py](../scripts/realign.py) |
| analyze：规格、方案、任务之间只读对照；问题回到拥有那份工件的步骤 | `check-feature` + 语义门 + `realign.py`。对照不改文件 |
| implement：按任务做，可按阶段收口 | `code`。只改 `include: true` 的路径 |
| converge：对照当前代码和规格；唯一写入是剩余工作；不改规格去迁就代码 | [deliver/SKILL.md](../deliver/SKILL.md) `code` 第 1 条 |

短路径是 specify → plan → tasks → implement → converge。clarify、checklist、analyze 是有歧义时加上的质量闸，不是另一条生命周期。

## 三条入口

Spec Kit 把建功能、修缺陷、评估想法分成三条入口。评估通过不会自动开始实现。

| 入口 | idev |
|------|------|
| 建功能 | S1 / S2 |
| 缺陷：先只读评估，再在评估点名的范围内改，最后用复现验证 | [ops](../ops/SKILL.md) 不改代码；修复走 `code`。点名的复现没跑过，不能写成已验证，见 [evidence.md](../conventions/evidence.md) |
| 想法：intake → research → define → shape → decide；`go` / 待澄清 / 停止 | 还没有可证伪 item 时不建票，见 [s1-vs-s8-playbook.md](s1-vs-s8-playbook.md)。停止写下来就是结果 |

## 已采纳并写入

| Spec Kit 约束 | 落点 |
|---------------|------|
| 规格写行为和必须保持的现有行为；存量仓不先补整仓规格；原则从已有规约和契约来 | [deliver/SKILL.md](../deliver/SKILL.md) `req-review` |
| 成功标准可测；「用某技术实现」是方案，不是需求 | [req-quality.md](../deliver/references/req-quality.md) §1、§3、§4 |
| 边界未订死先问完，回答写回问句文件，不是签字 | grilling，`frontier` 空之前不密封 |
| 规约与这张票冲突时改这张票；要改规约另走显式变更 | [conventions/SKILL.md](../conventions/SKILL.md) 硬规则 9 |
| 编码前的结构对齐由机器查，句子由人扫；两样都不代替对方 | `check-feature` 与语义门 |
| 对照代码时，尺只认密封基线、方案和 slice。勾选和「已经实现」不是证据。少做和部分补上，多做删掉，与基线相反则停。已经对齐不再添剩余工作。方案没点名的路径不算这次范围 | [deliver/SKILL.md](../deliver/SKILL.md) `code` 第 1 条；执行者复述在 [idev-coder.md](../agents/idev-coder.md) |
| 需求订正后查工件是否还指向当前基线，只报告不改文件 | [feedback-loop.md](feedback-loop.md)，`realign.py` |
| 点名的复现没有跑过，不能写成已验证 | [evidence.md](../conventions/evidence.md) |
| 想法要有反对证据；决定不做不建票 | [s1-vs-s8-playbook.md](s1-vs-s8-playbook.md) |

## 不采纳（护栏：勿再搬入）

| 不采纳 | 原因 |
|--------|------|
| `.specify/`、`specify` CLI、集成安装、preset、bundle、扩展钩子 | 编排在 idev 配方和产品仓 `.idev/`。钩子正文按 [evidence.md](../conventions/evidence.md) 只当数据 |
| 覆盖率百分比，以及 CRITICAL / HIGH / MEDIUM / LOW | 与反分数内核冲突。红绿只认 `PASS` / `FAIL` / `UNPROVEN` |
| 想法评分卡（strong / adequate / weak / unknown）当门槛 | 同上。停止或继续看有没有可证伪 item 和反对证据 |
| specify 里用行业默认猜掉范围、安全和权限，最多留 3 个澄清标记 | 这些分叉走 grilling，一次问完。猜进基线等于没问 |
| 写规格的同一方把需求质量清单勾完 | 语义门由人扫。Agent 不得代勾 |
| converge 自动往任务列表追加并循环实现，直到报 Converged | 剩余工作回到 `code` 第 1 条。不新增命令，不跳过签字 |
| 把规格当成唯一人手改的源，再生成实现 | 密封基线是尺。代码要写、要用例证明 |
| 同一需求并行多套实现再挑 | [hitl-risk-tiers.md](hitl-risk-tiers.md) 已写明不内置并行 PR 阶段机 |
| 每仓一份 constitution 模板，空栏用想象填满 | 原则已在 conventions / canon。存量仓不新发明一套来填模板 |
| 缺陷目录、评估目录各写一套 Markdown 阶段机 | 缺陷走 ops 与 verify。想法走上表，不另开工件树 |

## 规格交付之后怎么留

Spec Kit 把交付后的维护分成三种，都不作为默认：

| 模型 | 规则 |
|------|------|
| flow-back | 规格、方案、任务和实现可以互相回写 |
| flow-forward | 做完的目录冻结；新需求另开目录 |
| living spec | 只改规格，方案和任务作废重来 |

idev 的尺按 flow-forward：密封基线在 `reopen_baseline` 之前不改。人读规格复述这把尺，不一致时改规格。后确认进 `docs/adr/` 或 `docs/convention/`。方案和 slice 从基线派生。实现里的发现不能把「代码已批准」写成「意图已改」。正文在 [docs/SKILL.md](../docs/SKILL.md)「冲突」和 deliver「密封后不准改 baseline」。
