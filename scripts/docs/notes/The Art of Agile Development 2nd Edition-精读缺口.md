# 《The Art of Agile Development, 2nd Edition》精读缺口报告

> 源文本：`/tmp/idev-books/TheArtOfAgileDevelopment2-全文.txt`（作者官网 70 个页面按目录顺序合并；9,383 行 / 652,938 字节；单页 HTML 位于 `/tmp/idev-books/pages-final/TheArtOfAgileDevelopment2/`）。本报告只对照 `conventions/canon.md` 与 `conventions/coding-tables.md`，本轮不修改真源。

## 一、精读范围

本地全文 70/70 页已读完，四个部分与所有章节、实践页均覆盖：

- Part I（001–006）：What is Agile?、How to Be Agile、Choose Your Agility、Invest in Agility、Invest in Change、Scaling Agility。
- Part II（007–040）：Focusing on Value 引言；Teamwork、Planning、Ownership、Accountability、Improvement 五章引言及全部实践页：Whole Team、Team Room、Safety、Purpose、Context、Alignment、Energized Work、Stories、Adaptive Planning、Visual Planning、The Planning Game、Real Customer Involvement、Incremental Requirements、Task Planning、Capacity、Slack、Stand-Up Meetings、Informative Workspace、Customer Examples、Done Done、Stakeholder Trust、Stakeholder Demos、Forecasting、Roadmaps、Management、Retrospectives、Team Dynamics、Impediment Removal。
- Part III（041–066）：Delivering Reliably 引言；Collaboration、Development、Design、DevOps、Quality 五章引言及全部实践页：Collective Code Ownership、Pair Programming、Mob Programming、Ubiquitous Language、Zero Friction、Continuous Integration、Test-Driven Development、Fast, Reliable Tests、Refactoring、Spike Solutions、Incremental Design、Simple Design、Reflective Design、Build for Operation、Feature Flags、Continuous Deployment、Evolutionary System Architecture、No Bugs、Blind Spot Discovery、Incident Analysis。
- Part IV（067–070）：Optimizing Outcomes 引言；Autonomy、Discovery、Into the Future。

本地正文来自作者官网摘录，不是完整印刷书；全文含 39 处 “to continue reading, buy the book!” 续读提示。本报告的结论限定于本地可读的 70 页内容，不声称读到了未提供的印刷正文。

## 二、对照结论

本书的主张可分为三类：已被 idev 真源承载的工程判据、团队/组织/流程机制、以及书籍专属的操作仪式。只有第一类需要落到编号；后两类不进入编码与架构真源。

| 书中主题 | 已被承载的位置 | 裁定 |
|---|---|---|
| Part I 敏捷哲学、流益区、投资与规模化 | 代码侧的快速反馈、小步演进、权衡记录归 `T6`、`T12`、`A1`–`A8` | 主体是组织与流程；代码侧已承载 |
| Part II 团队协作、规划、所有权、问责、改进 | 命名/概念一致归 `T2`、`T5`；完成定义与可验证交付归 `T6`、`R1`、`A6`、`T11` | 流程内容不另立编码条目 |
| Collective Code Ownership、Pair/Mob Programming、Ubiquitous Language | `T2`、`T5`、`T6`、`A2`、`R1`–`R7` | 语言与协作判据已承载；结对/群体编程是团队执行方式 |
| Zero Friction | `T6`、`R1`、`A6`、`C28`、`C29`、`T11` | 原则已承载；具体秒数与五个脚本名是团队执行选择 |
| Continuous Integration | `T6`、`A6`、`T11` | 已承载 |
| Test-Driven Development | `T6`、`R1`–`R7`、`F5`、`C26`、`C28`、`C29`、`C30` | 已承载 |
| Fast, Reliable Tests | `C28`、`C29`、`C30` | 已承载 |
| Refactoring | `R1`–`R7`、`T6` | 已承载 |
| Spike Solutions | `T1`、`T12`、`A3`、`A5` | 学习实验与被拒方案记录已承载；“丢弃实验”仪式不是代码形状 |
| Incremental / Simple / Reflective Design | `T1`、`T3`、`T5`、`T7`、`T8`、`T9`、`T12`、`T14`、`A1`、`A3`、`A8`、`R1`–`R7` | 已承载 |
| Build for Operation | `T4`、`T8`、`T10`、`T11`、`T12`、`A2`、`A6`、`C31` | 已承载；具体 runbook/log code 格式是产品执行细节 |
| Feature Flags | `T1`、`T8`、`T11` | 已承载 |
| Continuous Deployment | `T10`、`T11`、`A6` | 已承载；发布节奏是流程选择 |
| Evolutionary System Architecture | `T1`、`T4`、`T12`、`A8` | 已承载 |
| No Bugs | `T6`、`F5`、`C7`、`C28`、`C29`、`C30`、`T12` | 已承载；“无 bug 流程”本身不是新的编码规则 |
| Blind Spot Discovery / Incident Analysis | `T12`、`A6`；可运维性归 `T11`，安全与可观测细节归 `C31` | 学习与复盘机制不另立条目；代码侧护栏已承载 |
| Part IV Optimizing Outcomes | 权衡记录归 `T12` | 组织/产品治理内容，不属于编码真源 |

本报告实际引用的既有编号：`T1`、`T2`、`T3`、`T4`、`T5`、`T6`、`T7`、`T8`、`T9`、`T10`、`T11`、`T12`、`T14`；`A1`–`A8`；`F5`；`C7`、`C26`、`C28`、`C29`、`C30`、`C31`；`R1`–`R7`。其中 `T13` 未被本书触发；架构决策、迁移与命名语义已有更通用规则承载。

`canon.md` §9 的出处列表只作溯源，不因新增一份精读报告自动补书名；没有新条目落地时，不把书名补录当成缺口。

## 三、真缺口

无。

理由：本书所有能约束本仓代码与架构判断的主张，均已由更通用的既有编号承载。其余内容是团队协作、组织治理、产品发现、流程仪式或工具链落地方式，不应复制成第二套知识库。

几个最强的候选也不构成真缺口：

1. **Zero Friction 的时间阈值与五个脚本**：`T6`、`R1`、`A6`、`C28`、`C29`、`T11` 已承载小步、护栏、反馈速度与可运维性；具体阈值和脚本名属于团队执行选择。
2. **Spike Solutions 的丢弃实验仪式**：`T1`、`T12`、`A3`、`A5` 已承载偶然复杂度削减、权衡记录、被拒方案与实验边界；实验后是否删代码是流程约束，不是代码形状。
3. **ADR 与并行动作/迁移**：`T12`、`A3`、`A8`、`T13`、`C6`、`R4` 已承载决策记录、迁移、契约变更与死代码清理。
4. **Runbook、日志编码与告警类别**：`T11` 与 `C31` 已承载可运维性、可观测性、关联 ID 与敏感信息保护；具体格式是产品选择。
5. **Feature Flags 与部署节奏**：`T1`、`T8`、`T10`、`T11`、`A6` 已承载相关代码与架构判据；发布节奏本身是流程选择。
6. **TDD 与 No Bugs 的流程细节**：`T6`、`R1`–`R7`、`F5`、`C26`、`C28`–`C30` 已承载测试、重构、失败暴露与可靠性要求。

因无真缺口，本轮不生成提案草稿，也不修改 `conventions/canon.md`、`conventions/coding-tables.md`、`scripts/docs/notes/README.md`、`references/changelog.md`。
