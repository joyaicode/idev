# 精读层（书 → 缺口 → 真源编号）

这一层是**中间产物**，不是真源，也不是知识库。真源只有两处：
`conventions/canon.md`（T1–T14 / A1–A8 / F1–F7）与
`conventions/coding-tables.md`（P1–P19 / C1–C40 / R1–R7）。

为什么不在这里建知识库：`coding.md` 文首明令「不要把 GoF 23 名录、《Clean Code》章节或
《重构》全书手法目录抄进产品仓」，`coding-tables.md` §3.5 明令「禁止另起表号 / 气味码 /
模式码」，`canon.md` §9 说出处「只作溯源」。一本书读完的产物是**落到既有编号上的缺口**，
不是一份新目录。

## 三层

| 层 | 在哪 | 入库 |
|---|---|---|
| 原始材料 | `scripts/docs/*.pdf` · `notes/*-OCR.txt` · `notes/*-全文.txt` | **不入库**。体量大（184M pdf + 5.6M ocr）且可再生：书在手上，OCR 可重跑 |
| 精读产物 | `notes/*-精读缺口.md` · `notes/DDD-精读笔记-*.md` | **入库**。592K，几小时的逐条对照，没有任何东西能把它再生出来 |
| 执法真源 | `conventions/canon.md` · `conventions/coding-tables.md` | 入库。改它走提案 + 拷问（SKILL.md 硬规则 7） |

`.gitignore` 按这个边界切。没有这一刀，要紧的 592K 没有历史，而一次 `git add .`
会把不要紧的 190M 永久写进历史。

## 已精读

「涉及编号」是该报告正文引用到的真源编号，**既含已覆盖也含缺口** —— 哪几条真的落了，
看该报告的「对照结论」节和对应提案。

| 书 | 报告 | 涉及编号 |
|---|---|---|
| 程序设计方法 | `程序设计方法-精读缺口.md` | T2 T3 T5 T6 T7 T9 T10 T11 T13 T14 · C1 C5 C9 C11 C12 C15 C19 C20 C21 · P1 · R1 R4 R5 · F5 |
| 代码整洁之道 | `代码整洁之道-精读缺口.md` | T1 T3 T4 T5 T6 T7 T8 T9 T10 T11 T12 T14 · C1 C2 C4 C5 C6 C7 C9 C10 C11 C12 C15 C20 C21 C28 C29 · P2 P3 P5 P15 · R1 R2 R4 R6 · F2 F5 |
| 重构 | `重构-精读缺口.md` | T1 T2 T3 T4 T5 T6 T7 T8 T9 T10 T14 · C1 C2 C3 C5 C6 C8 C9 C10 C11 C12 C15 C20 C21 C22 C25 C27 · P1 P2 P3 P4 P5 P6 P12 P15 · R1 R2 R3 R4 R5 R6 R7 · F5 F6 |
| 编写可读代码的艺术 | `编写可读代码的艺术-精读缺口.md` | T1 T2 T3 T4 T5 T6 T7 T9 T10 T14 · C1 C3 C4 C5 C6 C9 C12 C24 C26 · R1 · F2 F5 |
| 领域驱动设计（Eric Evans，全书 17 章 + 结束语 + 附录，7 份逐章笔记 Ch1-4 / Ch4余-5 / Ch6-7 / Ch8-9 / Ch10-12 / Ch13-14 / Ch15-17 收口） | `领域驱动设计-精读缺口.md` | A1 A2 A8 · T1 T3 T4 T5 T12 · P1 P5 P6 P17 P18（新增）P19（新增） · C2 C15 C20 C21 · F1 |
| 设计模式两书（设计模式之禅 + HeadFirst 设计模式） | `设计模式-精读缺口.md` | T1 T3 T4 T9 T10 T14 · C1 C22 C24 C27 · P1–P14 P18 · F1 |
| 程序设计实践 | 无独立报告；成果见 `state/proposals/20261030-conventions-seven-gaps.md` | 落 T13 · C16 C17 C18 C19 · `evidence.md` 排查第 1 步 |
| 微服务设计（全书第 1–11 章，十批精读完毕：架构师 / 建模 / 集成 / 分解单块 / 部署 / 测试 / 监控 / 安全 / 康威定律 / 规模化） | `微服务设计-精读缺口.md` | T1 T2 T4 T5 T6 T7 T8 T10 T11 T12 T13 · C6 C26 C28–C31 · R1 · F5 · A1–A8 |
| 修改代码的艺术（Feathers：遗留代码 = 无测试的代码；测试用具 / 接缝 / 特征测试 / 24 种解依赖技术的定位与边界） | `修改代码的艺术-精读缺口.md` | T2 T3 T4 T5 T6 T7 T10 T12 T14 · C1 C6 C21 C23 C26 C28 C30 · P3 P4 P5 P6 P7 · R1（「不满足时」列增补解依赖路径）R2 R3 R4 R5 R6 R7 · F5 F6 · A1 A2 A6 |
| 代码大全（第一版中译，全书第 1–33 章） | `代码大全-精读缺口.md` | T1 T3 T4 T5 T6 T8 T9 T10 T11 T12 T14 · C1 C2（default 增补）C5 C7 C9 C10 C12 C13 C26 C31 · P1 P5 · R4 R6 R7 · F5 · A1–A8 |
| 设计模式：可复用面向对象软件的基础（GoF，全书第 1–6 章与附录 A–C） | `设计模式：可复用面向对象软件的基础-精读缺口.md` | T1 T3 T4 T5 T7 T9 T10 T12 T14 · C19 C22 C23 C27 · P1–P14 P19 · F1 · A4 |
| 测试驱动开发（Kent Beck，全书第 1–32 章与附录 A–B） | `测试驱动开发-精读缺口.md` | T1 T3 T4 T5 T6 T7 T8 T12 T14 · C1 C6 C19–C30 · P1–P8 P12 P13 P15 · R1 R2 R4 R5 R7 · F1 F2 F5 · A1 A5 A6 A8 |
| 程序员修炼之道：从小工到专家（Andrew Hunt / David Thomas，全书 70 条 tip） | `程序员修炼之道-精读缺口.md` | T1 T3 T4 T5 T6 T7 T8 T9 T10 T11 T12 T13 T14 · A1 A3 A4 A5 A8 · C2 C7 C13 C19 C22 C23 C26 C27 C28 C29 C30 · P5 P6 P18 · R1 R2 R3 R4 R5 R6 R7 · F5 |
| 程序员的职业素养（Robert C. Martin，全书第 1–14 章与附录） | `程序员的职业素养-精读缺口.md` | T6 T12 · C26 C28 C29 C30 · F5 |
| Web 性能权威指南（Ilya Grigorik，全书 18 章 331 页） | `Web性能权威指南-精读缺口.md` | A1 A2 A3 A4 A6 A8 · C1 C31 · F1 F4 F5 F6 F7 · P1 P19 · R1 R7 · T1 T6 T8 T9 T10 T11 T13 T14 |
| Effective Java 中文版（第 2 版，Joshua Bloch，全书 11 章 78 条 + 附录） | `EffectiveJava中文版第2版-精读缺口.md` | C2 C7 C23 C25 C27 · F2 F4 · P1 P2 P4 P5 P6 P14 P15 · T1 T3 T4 T5 T7 T8 T9 T10 T11 T12 T14 |
| 高效程序员的 45 个习惯（Venkat Subramaniam / Andy Hunt，全书第 1–9 章、附录 A 与 45 个习惯） | `高效程序员的45个习惯-精读缺口.md` | A1 A3 A8 · C1 C3 C5 C7 C16 C17 C22 C24 C26 C27 C28 C30 C31 · F1 F2 F4 F5 F7 · P1 P6 P18 P19 · R1 R7 · T1 T2 T3 T5 T6 T8 T9 T11 T12 T14 |
| 大型网站技术架构（李智慧，全书第 1–16 章、附录 A/B 与后记） | `大型网站技术架构-精读缺口.md` | A4 A6 A8 · C1 C26 C28 C29 C30 C31 · F1 F7 · T1 T3 T4 T8 T9 T10 T11 T12 |
| UNIX 编程艺术（Eric S. Raymond，全书 20 章、4 部分） | `UNIX编程艺术-精读缺口.md` | C1 C2 C6 C7 C12 C22 C23 · P5 P15 P18 · T1 T2 T3 T4 T5 T7 T8 T9 T10 T11 T14 |
| 企业应用架构模式（Martin Fowler，全书引言 + 第 1–18 章共 51 个模式） | `企业应用架构模式-精读缺口.md` | A1 A2 A4 · C2 C13 C25 C27 C30 · F1 · P3 P5 P6 P15 P18 P19 · T1 T3 T4 T5 T8 T9 T10 T11 T14 |
| 企业集成模式：设计、构建及部署消息传递解决方案（Gregor Hohpe / Bobby Woolf，全书引言 + 14 章正文与参考文献） | `企业集成模式-精读缺口.md` | A2 A3 A4 · T4 T7 T8 T10 T11 T12 T13 |
| Java 编程思想（第 4 版，Bruce Eckel《Thinking in Java》，全书 22 章 + 前言 / 译者序 / 读者评论 / 附录） | `Java编程思想（第4版）-精读缺口.md` | C7 C19 C27 C32 · P18 · T1 T3 T4 T7 T8 T9 T10 T14 |
| 编程珠玑（第 2 版，Jon Bentley《Programming Pearls》，全书三部分 15 章 + 附录 A–E + 第 1/2 版跋 + 习题提示/答案 + 索引） | `编程珠玑（第2版）-精读缺口.md` | A1 · T1 T2 T3 T5 T6 T7 T9 T10 T13 · C12 C20 C23 C25 C26 C33（新增） · R1 · F5 |
| C 专家编程（Peter van der Linden《Expert C Programming》，全书 11 章 + 附录 A/B） | `C专家编程-精读缺口.md` | T1 T3 T4 T7 T11 · P5 · C27 C33 |
| Go 程序设计语言（Alan A. A. Donovan / Brian W. Kernighan《The Go Programming Language》，全书 12 章 + 前言 / 译者序 / 致谢） | `go程序设计语言-精读缺口.md` | T1 T3 T4 T5 T8 T10 T11 T14 · C2 C7 C19 C23 C28 C34（新增）C38（新增） · P6 · R1 · F4 |
| C 陷阱与缺陷（Andrew Koenig《C Traps and Pitfalls》，全书 8 章 + 附录 A/B） | `C陷阱与缺陷-精读缺口.md` | T4 T5 T6 T7 T8 · C2 C9 C18 C19 C20 C33 C35（新增）C36（新增）C37（新增） · R1–R7 · F4 |
| C 程序设计语言（第 2 版，Brian W. Kernighan / Dennis M. Ritchie《The C Programming Language, Second Edition》中译「K&R C」，全书 8 章 + 附录 A/B/C） | `C程序设计语言（第2版）-精读缺口.md` | T1 T3 T4 T5 T7 T14 · C1 C2 C7 C10 C16 C17 C19 C20 C21 C35 C36 C37 · P15 · F4 |
| Go 语言实战（William Kennedy / Brian Ketelsen / Erik St. Martin《Go in Action》中译，全书 9 章 + 译者序 / 序 / 前言） | `Go语言实战-精读缺口.md` | T1 T3 T4 T7 T9 T10 T11 T14 · C2 C7 C19 C26 C27 C28 C30 C34 C38 C39（新增） · P6 P15 · R1 · F4 |
| Go 学习笔记（第 4 版，雨痕《Go 学习笔记》，基于 Go 1.4，全书三部分：语言 / 源码 / 附录） | `Go学习笔记（第4版）-精读缺口.md` | T9 T10 T14 · C6 C19 C23 C35 C38 C39 C40（新增） · F4 F5 |
| C 语言接口与实现（David R. Hanson《C Interfaces and Implementations》中译「创建可重用软件的技术」，全书 20 章） | `C语言接口与实现-精读缺口.md` | T1 T3 T4 T9 T10 T11 T12 T14 · C1 C2 C5 C7 C15 C16 C17 C19 C24 C38 C39 · F4 F5 |
| Go 学习笔记（第 6 版下卷，雨痕《Go 学习笔记》，基于 Go 1.10，66 页运行时源码：启动 / 内存分配器 / GC / scavenge） | `Go学习笔记（第6版下卷）-精读缺口.md` | T5 T9 T11 · C13 C17 C19 C23 C39 |
| Go 源码剖析（雨痕《Go 学习笔记》第五版下册《源码剖析》，基于 Go 1.5.1，全书 10 章：准备 / 引导 / 初始化 / 内存分配 / 垃圾回收 / 并发调度 / 通道 / 延迟 / 析构 / 缓存池） | `Go源码剖析-精读缺口.md` | T1 T2 T9 T10 T11 T14 · C19 |
| HTTP 权威指南（David Gourley / Brian Totty / Marjorie Sayer / Sailu Reddy / Anshu Aggarwal《HTTP: The Definitive Guide》中译，全书 21 章 + 8 附录） | `HTTP权威指南-精读缺口.md` | A4 A6 · C7 C18 C21 C23 C31 C38 · T9 T10 T11 |
| 计算的本质：深入剖析程序和计算机（Tom Stuart《Understanding Computation》中译，张伟译，306 页 9 章 + 前言/后记：Ruby 基础 / 程序的含义 / 有限自动机 / 下推自动机 / 图灵机 / 从零开始编程 / 通用性无处不在 / 不可能的程序 / 抽象解释） | `计算的本质：深入剖析程序和计算机-精读缺口.md` | T1 T2 T3 T8 T14 · R6 |

## 读一本书的流程

1. **精读 + 逐条对照真源**，不是摘抄。产出 `<书名>-精读缺口.md`，格式沿用
   `代码整洁之道-精读缺口.md`：精读范围 → 对照结论（哪些已被承载、承载在哪条）→ 真缺口。
2. **只有缺口进下一步。** 真源已经承载的，在报告里写明承载于哪条就够了。
3. **落到既有编号**，按最小 diff。不另起编号体系 —— 新条目接在 `T`/`C`/`P`/`R` 的末尾，
   并同步 `canon.md` §0/§3 与 `coding-tables.md` §3.5 的编号范围。
4. **配 TRIGGER —— 这一步决定它将来会不会被想起来。** 新的 **T#** 必须同时落：
   - `canon.md` §2 一行可 grep 的信号（diff 或计划里能看见的东西）
   - `canon.md` §4 一行念头（人动手前心里会冒出来的那句话）

   §2 的标题就是理由：「**不依赖你"想没想到"**」。只进 §3 规则表、不配 §2/§4 的条目，
   只能靠人记得去查 —— 那正是这套设计要消除的东西。T13 落地时同步加了
   「修改对外 API / 消息 / 字段语义但保留原名 → T13 T12」，有这一行它才会在 diff 里被撞上。
   `trigger-check.py` 对 T# 强制这一条，`selfcheck.sh` 会因它失败。

   **C# / P# / R# 不走这条路，是有意的**（`trigger-check.py` 文首写了原因）：气味靠扫表，
   不靠信号 —— `coding.md` §0 第 5 步每写一个新函数扫一遍全表，Review 第 4 步再扫一遍。
   拿 §2/§4 去判它们，会把一条设计决策误读成缺口（2026-11-05 就这么误判过一次）。
5. **走提案 + 拷问**（硬规则 7），人确认后才改真源。
6. **质检：落了表不等于拦得住。** 不看已精读表，跑：

   ```bash
   python3 scripts/deep-read-audit.py --report scripts/docs/notes/<书>-精读缺口.md
   python3 scripts/deep-read-audit.py --all-books
   ```

   `--all-books` 只收 `*-精读缺口.md`，给出每份报告的可达数和全局「只有记账」编号；DDD 逐章笔记的局部编号与《程序设计实践》的提案直落成果不进这批。

   它按四层报每条到达了哪里：`defined`（只是记账）→ `trigger`（T# 的 §2/§4）→
   `staged`（阶段页点名，含 `A1–A8` / `P1–P19` / `C1–C40` / `R1–R7` 这类全表范围）→ `enforced`（插件能判形状）。只有后三层会在没人想起时起作用。

   判据取自真源自己的设计意图，不要自造一把尺 —— 这是上一条那次误判的来源。
7. **反思与重炼化。** `enforced` 那一列是可以变的：条目的气味若有明确代码形状，
   就做进 `scripts/plugin/canon_smells.py`，让它从「靠记得扫表」变成「程序撞上」。
   做之前先认清代价边界：

   - **按条目原文划范围，不要扩。** C7 原文只说 `return []` / `{}` / `false`；首版把
     `null` / `None` 也算进去，在本仓真实代码上命中 77 处，收回原文范围后是 35 处。
   - **每个检测器当场写正例和反例**（`references/failure-modes.md` 三的教训），
     并在真实代码上量一次密度。插件是人每轮要读的告警，**误报的代价高于漏报**。
   - **形状分不清正当写法的，就明确不做**，把理由写进 `canon_smells.py` 的 `DECLINED`，
     让「没覆盖」读起来不像「没人管」。

   **什么时候该重读这本书：** 不是 `enforced` 少就重读。落到 C#/P#/R# 本来就多数不可机检。
   真正该重炼化的信号是——这本书的条目在 `deep-read-audit` 里**一条都没到达代码**
   （脚本此时 exit 1），或者精读报告写的「真缺口」与真源里实际落下的编号对不上。
   前者说明读出来的东西没找到落点，后者说明落的时候走样了。两种都要回到第 1 步重读，
   而不是在原条目上补字。

## 两条边界

**局部编号不得外泄。** 笔记里可以有自己的要点序号，但它只在那份笔记内有效。
`DDD-精读笔记-Ch1-4.md` 的 `F1`–`F13` 是该笔记的要点序号（F1 模型是公共语言的核心、
F2 语言鸿沟……），与 `canon.md` 的失败模式 `F1`–`F7`（F5 = 自证式测试）**同形不同义**。
票目录 `current.md`、`review.md`、clean-code 票里写编号，只认真源那两页 —— §3.5 的
「不要双语记账」说的就是这件事。引用笔记要点时写文件名加标题，不要写裸编号。

**召回不靠检索。** `context-stage.py` 是两阶段读（薄目录 → 加载一个区间），两路来源都是
确定的：`codegraph` 给符号位置，`lessons` 给该票证据里的路径。它服务的是读代码，不负责
让你想起某条规范。曾有第三路本地向量检索，2026-11-03 因零使用退役（`attic/MOVED.md`）——
这件事本身就是本页这条结论的注脚：**规范的召回归 §2 信号、§4 念头和 `coding.md` §0 的
强制对表，不归检索。**
