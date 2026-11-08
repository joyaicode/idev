# 《The Architecture of Open Source Applications》精读缺口报告

> 源文本：`/tmp/idev-books/TheArchitectureOfOpenSourceApplications-全文.txt`（官方在线页面按目录顺序合并，编号 001–092、官方缺 041，共 91 页；65,077 行 / 572,105 词 / 3,662,195 字节）。本轮未访问网络，直接精读本地全文。本报告只对照 `conventions/canon.md` 与 `conventions/coding-tables.md`，不修改真源。

## 一、精读范围

官方站点聚合的四个系列卷已全部读完，页面覆盖如下：

| 分卷 | 官方页面 | 覆盖内容 |
|---|---:|---|
| AOSA Volume 1 | 002–028 | 前言 / Contributors / Acknowledgments / Dedication、25 个正文章、Bibliography |
| AOSA Volume 2 | 029–055 | 前言 / Contributors / Acknowledgments / Contributing、24 个正文章、Bibliography；官方编号缺 041，未跳过任何存在的页面 |
| The Performance of Open Source Software（POSA） | 056–068 | 前言 / Contributors / Acknowledgements / Contributing / Colophon、12 个正文 essay |
| 500 Lines or Less | 069–091 | 前言 / Contributors / Acknowledgments / Contributing / Colophon、22 个正文项目章 |
| 站点与许可 | 001、092 | 购买页与 Creative Commons 许可页 |

正文篇目逐篇覆盖：AOSA Vol.1 为 Asterisk、Audacity、The Bourne-Again Shell、Berkeley DB、CMake、Eclipse、Graphite、The Hadoop Distributed File System、Continuous Integration、Jitsi、LLVM、Mercurial、The NoSQL Ecosystem、Python Packaging、Riak and Erlang/OTP、Selenium WebDriver、Sendmail、SnowFlock、SocialCalc、Telepathy、Thousand Parsec、Violet、VisTrails、VTK、Battle for Wesnoth；AOSA Vol.2 为 Scalable Web Architecture and Distributed Systems、Firefox Release Engineering、FreeRTOS、GDB、The Glasgow Haskell Compiler、Git、GPSD、The Dynamic Language Runtime and the Iron Languages、ITK、GNU Mailman、matplotlib、MediaWiki、Moodle、nginx、Open MPI、OSCAR、Processing.js、Puppet、PyPy、SQLAlchemy、Twisted、Yesod、The Yocto Project、ZeroMQ；POSA 为 High Performance Networking in Chrome、From SocialCalc to EtherCalc、Ninja、Parsing XML at the Speed of Light、MemShrink、Applying Optimization Principle Patterns to Component Deployment and Configuration Tools、Infinispan、Talos、Zotonic、Secrets of Mobile Network Performance、Warp、Working with Big Data in Bioinformatics；500 Lines or Less 为 Blockcode、A Continuous Integration System、Clustering by Consensus、Contingent、A Web Crawler With asyncio Coroutines、Dagoba、DBDB、An Event-Driven Web Framework、A Flow Shop Scheduler、An Archaeology-Inspired Database、Making Your Own Image Filters、A Python Interpreter Written in Python、A 3D Modeller、A Simple Object Model、Optical Character Recognition、A Pedometer in the Real World、The Same-Origin Policy、A Rejection Sampler、Web Spreadsheet、Static Analysis、A Template Engine、A Simple Web Server。

各章的目录、小节、脚注、参考文献、作者 / 贡献者信息均随对应页面读完。购买页只含系列入口与购买信息，许可页只含法律条款；二者已核对，不新增工程判据。500 Lines or Less 的引言明确称其为该系列第四卷，本轮按 AOSA Vol.1、AOSA Vol.2、POSA、500 Lines or Less 四卷逐卷覆盖。

## 二、对照结论

全书的主张可归为四类：可推广的架构 / 编码判据，具体项目的历史与实现事实，语言 / 运行时 / 协议 / 算法细节，以及社区与出版信息。只有第一类需要进入本仓真源；其余内容是证据或背景，不应复制成第二套知识库。

| 书中主题 | 已被承载的位置 | 裁定 |
|---|---|---|
| 先解决本质问题、砍偶然复杂度、避免为未来预置层和扩展点；小接口、厚实现；知识单一来源 | T1、T3、T7、A1、A7、F1 | 已承载 |
| 概念完整性、统一语言、沿用既有风格、命名与跨模块一致性 | T2、T5、F3、C5 | 已承载 |
| 依赖方向、模块 / 服务边界、插件与宿主边界、平台差异收敛、跨信任域授权 | T4、A2、C16、C17 | 已承载 |
| 测试优先、CI、回归测试、测试金字塔、脆弱测试、mock 边界、小步可逆重构 | T6、A6、F5、F6、C26、C28、C29、C30、R1–R7 | 已承载 |
| 快速失败、异常与失败语义、资源获取 / 释放、进程退出与库边界 | T8、F4、C19、C38 | 已承载 |
| 度量优先、避免过早优化、热点证明、性能文化与权衡 | T9、T11、A6 | 已承载 |
| 存储真相之源、副本 / 缓存 / 队列、一致性、恢复、Schema 演进、并发控制与共享状态 | T10、A4、T14、C34、C39 | 已承载 |
| 可运维性、观测指标、日志、回滚、灰度与生产运行约束 | T11、A6 | 已承载 |
| 架构是记录过的权衡；演进、重写 / 重构取舍、明确不做什么 | T12、A3、A8、F7 | 已承载 |
| 兼容性、契约语义变化、版本迁移、旧行为保持 | T13、T12、T4 | 已承载 |
| 安全边界、身份传递、凭证与敏感信息、浏览器同源策略等项目中的安全教训 | T4、A2、P7、C31 | 已承载 |
| 构建系统、依赖图、增量执行、可复现产物 | T4、T7、T9、A6 | 已承载 |
| “约束解放设计”、小实验降低失败成本、原型先行、先让真实问题驱动设计 | T1、T6、T9、A3 | 已承载 |

本报告实际引用的既有编号：T1、T2、T3、T4、T5、T6、T7、T8、T9、T10、T11、T12、T13、T14；A1、A2、A3、A4、A6、A7、A8；F1、F3、F4、F5、F6、F7；P7；C5、C16、C17、C19、C26、C28、C29、C30、C31、C34、C38、C39；R1–R7。

`canon.md` §9 的出处列表只作溯源，不因新增一份精读报告自动加书名；没有新条目落地时，不把书名补录当成缺口。

## 三、真缺口

无。

理由：四个系列卷中所有能约束本仓代码与架构判断的原则，均已有更通用的 T / A / F / C / P / R 编号承载。Asterisk、Berkeley DB、HDFS、Git、ZeroMQ、Chrome、Paxos、Warp 等具体项目的实现细节、历史决策、协议事实、算法与领域示例，只是这些原则的证据，不宜抄成第二套知识库；语言 / 运行时差异、工具用法、社区治理、出版购买信息、参考文献与许可条款也不属于编码或架构真源。

因无真缺口，本轮不生成 `state/proposals/20261108-aosa-gaps.md`，也不修改 `conventions/canon.md`、`conventions/coding-tables.md`、`scripts/docs/notes/README.md`、`references/changelog.md`。
