# 《Software Engineering at Google》精读缺口报告

> 源文本：`scripts/docs/notes/Software Engineering at Google-全文.txt`（官方在线正文 34 页合并；12,960 行 / 224,385 词 / 1,421,176 字节）。官方入口：<https://abseil.io/resources/swe-book/html/toc.html>。本报告只对照 `conventions/canon.md` 与 `conventions/coding-tables.md`，本轮不修改真源。

## 一、精读范围

官方在线正文已完整读完，覆盖：

- 前言（Foreword）与序言（Preface）。
- Part I. Thesis：第 1 章。
- Part II. Culture：第 2–7 章。
- Part III. Processes：第 8–15 章。
- Part IV. Tools：第 16–25 章。
- Part V. Conclusion：第 26 章 Afterword。
- 全书索引（Symbols、A–Z）。
- 五个 Part 分隔页仅为标题页，无实质正文，也已逐页核对。

本地全文证据按官方页面顺序合并 34 页：Foreword、Preface、Part 1–5、Chapter 1–26、Index。索引页的章节链接解析到 `ch01.html`–`ch26.html`，与已抓取正文章节一一对应；索引本身只提供词条与章节锚点，不新增正文主题。

## 二、对照结论

本书的主张大致分三类：已有真源承载的工程判据、Google 专属工具与流程机制、组织文化叙事。只有第一类需要落编号；后两类不进编码/架构真源。

| 书中主题 | 已被承载的位置 | 裁定 |
|---|---|---|
| 软件工程是随时间演化的编程；可持续性、规模化与权衡 | T12、A3、A8；变更与小步可逆归 T6 | 已承载 |
| Hyrum’s Law：调用方会依赖可观察行为；契约变更须显式迁移 | T13、T12、T4；重构时的可观察行为不变归 R2 | 已承载 |
| Beyoncé Rule、Shifting Left、快速反馈与公共 CI 护栏 | T6、R1、A6；测试可常跑与失败定位归 C28、C29 | 已承载 |
| 团队协作、知识共享、心理安全、导师制、技术布道 | 代码侧的概念一致与先读后写归 T2；文档与决策同轮更新归 T12、T5、C5 | 文化/流程叙事不另立编码条目 |
| 工程公平、团队领导、规模化领导、工程效能度量 | 权衡记录归 T12；度量须有方法边界归 T9 | 组织治理内容不属编码真源 |
| 风格指南：一致性、为读者优化、规则要值回成本、自动化 | T2、T5、C5、C12；无效复杂度与死代码归 T1、C6 | 已承载 |
| 代码评审：正确性、可理解性、一致性、小变更、知识传播 | C14、T2、T6；变更拆小与可回退归 R4；代码是负债归 T1、C6、R5 | 已承载 |
| 文档像代码一样维护：受众、类型、评审、 freshness | T12、T5、C5 | 已承载 |
| 测试总览、测试规模与测试范围、测试金字塔 | T6、F5、C26、C28、C29、R1、A6 | 已承载 |
| 单元测试：测公共 API、测行为不测实现、清晰失败信息、DAMP | T6、F5、C26、C30；脆弱测试归 C29 | 已承载 |
| 测试替身、fake 保真度、大型测试补真实环境缺口 | C30、R1、F2、C28；不可靠测试当轮处理归 C29 | 已承载 |
| 弃用：设计期考虑下线、迁移、告警、防回潮 | T13、T12、T4；迁移计划与被拒方案归 A3 | 已承载 |
| 版本控制：单一事实源、One-Version、少长生命周期分支 | T7、A4；小步可逆与结构/行为分离归 T6、R3 | 已承载 |
| 构建系统：显式依赖、artifact-based、最小可见性 | T4、A2、C18；重复知识收敛归 T7 | 已承载 |
| Code Search、Critique、静态分析平台 | 代码侧仍归评审纪律 C14 与概念一致 T2；工具本身是执行机制 | 不新增编码条目 |
| 依赖管理：兼容承诺、SemVer 边界、Live at Head、外部依赖风险 | T4、T13、F2、T12；密钥与外部依赖安全归 C31 | 已承载 |
| 大规模变更：拆分、测试、评审、工具化、防回退 | T6、R1、R4、T12、A6 | 已承载 |
| 持续集成：presubmit/postsubmit、自动化、hermetic、快速反馈 | T6、T11、A6；测试结构归 C28、C29 | 已承载 |
| 持续交付：小批次、feature flag、release train、指标与回滚 | T11、T6、A6；决策记录归 T12 | 已承载 |
| 计算即服务：自动化、容器与多租户、面向失败设计、批处理/服务、状态管理 | T10、T11、A4、A6；边界与依赖方向归 T4 | 已承载 |
| Afterword 与索引 | 全书结论与交叉引用，无新增判据 | 不落条目 |

本报告实际引用的既有编号：T1、T2、T3、T4、T5、T6、T7、T8、T9、T10、T11、T12、T13、T14；A1、A2、A3、A4、A5、A6、A7、A8；F2、F5、F6；C5、C6、C12、C14、C18、C26、C28、C29、C30、C31；R1、R2、R3、R4、R5、R6、R7。T8、T9、T10、T11、T14 与 A1、A5、A7、F6 主要由版本管理、度量、CaaS、依赖与风险控制主题间接承载。

`canon.md` §9 的出处列表只作溯源，不因新增一份精读报告自动加书名；没有新条目落地时，不把书名补录当成缺口。

## 三、真缺口

无。

理由：本书所有能约束本仓代码与架构判断的主张，都已有更通用的编号承载；Piper、Critique、Tricorder、Rosie、Borg、One-Version、Beyoncé Rule、release train 等 Google 专属机制只是这些原则的规模化实现，不宜复制成第二套流程知识库。组织文化、工程公平、领导力和工程效能治理属于仓库流程/管理主题，也不是 `canon.md` 或 `coding-tables.md` 的编码与架构真源缺口。

因无真缺口，本轮不生成提案草稿，也不修改 `conventions/canon.md`、`conventions/coding-tables.md`、`scripts/docs/notes/README.md`、`references/changelog.md`。
