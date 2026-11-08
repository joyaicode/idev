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
| 程序员的自我修养：链接、装载与库（俞甲子 / 石凡 / 潘爱民，2009 年电子工业出版社，485 页 4 部分 13 章：温故而知新 / 编译和链接 / 目标文件 / 静态链接 / Windows PE/COFF / 装载与进程 / 动态链接 / Linux 共享库 / Windows DLL / 内存 / 运行库 / 系统调用与 API / MiniCRT） | `程序员的自我修养-精读缺口.md` | T3 T4 T10 T13 T14 · C18 |
| 七周七语言：理解多种编程范型（Bruce A. Tate《Seven Languages in Seven Weeks》中译，全书 9 章 + 附录参考书目） | `七周七语言：理解多种编程范型-精读缺口.md` | T1 T3 T5 T8 T10 T11 T14 · C2 C7 C21 C25 C38 · P15 |
| Docker 从入门到实践（第 3 版）（开源书《Docker — 从入门到实践》0.9.0 版，370 页带文本层，经 macOS PDFKit 逐页提取） | `Docker从入门到实践（第3版）-精读缺口.md` | T1 3 7 8 10 11 14 · C6 13 31 |
| JavaScript设计模式与开发实践（曾探著，人民邮电出版社 2015，全书 22 章：第一部分「基础知识」第 1–3 章、第二部分「设计模式」第 4–17 章共 16 个模式、第三部分「设计原则和编程技巧」第 18–22 章） | `JavaScript设计模式与开发实践-精读缺口.md` | T1 2 3 4 5 6 7 8 9 10 11 12 13 14 · C1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 · P1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 · R1 2 3 4 5 6 7 |
| JavaScript语言精粹（Douglas Crockford《JavaScript: The Good Parts》中译修订版，电子工业出版社 2012，正文 10 章 + 附录 A–E） | `JavaScript语言精粹-精读缺口.md` | T2 3 4 5 8 14 · F3 4 · C2 5 16 34 |
| javascript面向对象编程（Stoyan Stefanov《Object-Oriented JavaScript》中译，Packt 2008，全书 7 章：第一部分「现代 JavaScript 简介」第 1 章、第二部分「专业的 JavaScript 开发」第 2–4 章、第三部分「Unobtrusive JavaScript」第 5–7 章） | `javascript面向对象编程-精读缺口.md` | T2 3 4 5 6 7 · F5 · C11 26 28 29 30 |
| 你不知道的JavaScript（上卷）（Kyle Simpson《You Don't Know JS: Scope & Closures / this & Object Prototypes》中译上卷，人民邮电出版社 2015，两部分：第一部分「作用域和闭包」第 1–5 章 + 附录 A–D、第二部分「this 和对象原型」+ 附录 A） | `你不知道的JavaScript（上卷）-精读缺口.md` | T3 4 5 8 14 · C2 34 |
| 你不知道的JavaScript（中卷）（Kyle Simpson《You Don't Know JS: Types & Grammar / Async & Performance》中译中卷，人民邮电出版社 2015，两部分：第一部分「类型和语法」第 1–5 章、第二部分「异步和性能」第 1–6 章 + 附录 A–B） | `你不知道的JavaScript（中卷）-精读缺口.md` | T5 8 9 10 11 14 · C24 35 |
| 你不知道的JavaScript（下卷）（Kyle Simpson《You Don't Know JS: Up & Going / ES6 & Beyond》中译下卷，人民邮电出版社 2015，两部分：第一部分「起步上路」第 1–2 章、第二部分「ES6 及更新版本」第 1–8 章） | `你不知道的JavaScript（下卷）-精读缺口.md` | T3 4 8 10 11 14 · A2 · C2 38 |
| 基于MVC的JavaScript Web富应用开发（Alex MacCaw《JavaScript Web Applications》中译，电子工业出版社 2012，全书 13 章：MVC / 事件与观察者 / 模型与数据 / 控制器与状态 / 视图与模板 / 依赖管理 / 文件 / 实时 Web / 测试 / 部署 / Spine / Backbone / JavaScriptMVC） | `基于MVC的JavaScript_Web富应用开发-精读缺口.md` | T3 4 5 8 9 10 11 14 · A4 · F5 · C2 11 24 25 26 28 29 30 |
| MongoDB 实战（《MongoDB 实战》中译，91 页带文本层，经 macOS PDFKit 逐页提取） | `MongoDB实战-精读缺口.md` | T9 10 11 · A4 6 · C31 |
| MySQL 必知必会（Ben Forta《MySQL 必知必会》中译，252 页带文本层，经 macOS PDFKit 逐页提取） | `MySQL必知必会-精读缺口.md` | T1 3 9 10 11 · A4 6 · C31 |
| MySQL 性能调优与架构设计（简朝阳《MySQL 性能调优与架构设计》，302 页带文本层，经 macOS PDFKit 逐页提取） | `MySQL性能调优与架构设计-精读缺口.md` | T9 10 11 · A4 6 · C31 |
| Redis 开发与运维（付磊 / 张益军《Redis 开发与运维》，890 页带文本层，经 macOS PDFKit 逐页提取） | `Redis开发与运维-精读缺口.md` | T8 9 10 11 · A4 6 · F4 |
| Python Cookbook（David Beazley / Brian K. Jones《Python Cookbook（第 3 版）》中译，702 页带文本层，经 macOS PDFKit 逐页提取） | `Python_Cookbook-精读缺口.md` | T1 3 5 8 9 10 14 · F4 · C7 18 19 26 28 · R1 |
| Python 编程：从入门到实践（Eric Matthes《Python 编程：从入门到实践》中译，482 页带文本层，经 macOS PDFKit 逐页提取） | `Python编程：从入门到实践-精读缺口.md` | T1 3 4 5 8 · F4 5 · C1 19 26 28 · R1 |
| Python 核心编程（Wesley Chun《Python 核心编程（第 2 版）》中译，925 页带文本层，经 macOS PDFKit 逐页提取） | `python核心编程-精读缺口.md` | T2 3 4 5 8 10 14 · F4 · C7 19 27 |
| 深入 Linux 内核架构（Wolfgang Mauerer《Professional Linux Kernel Architecture》中译，1058 页带文本层，经 macOS PDFKit 逐页提取） | `深入Linux内核架构-精读缺口.md` | T3 4 10 11 14 · A4 · C19 31 |
| 深入理解Nginx：模块开发与架构解析（第2版）（陶辉著，机械工业出版社 2016，全书 16 章：第一部分「Nginx 能帮我们做什么」第 1–2 章、第二部分「如何编写 HTTP 模块」第 3–7 章、第三部分「深入 Nginx」第 8–16 章） | `深入理解Nginx-精读缺口.md` | T1 2 3 4 7 8 9 10 11 12 14 · A6 · C19 24 |
| 跟我一起写 Makefile（陈皓《跟我一起写 Makefile》，75 页带文本层，经 macOS PDFKit 逐页提取） | `跟我一起写makefile-精读缺口.md` | T7 11 |
| JavaScript函数式编程（Michael Fogus《Functional JavaScript》中译，人民邮电出版社 2015，全书 9 章 + 附录 A–B） | `JavaScript函数式编程-精读缺口.md` | T3 4 10 14 · F5 · C20 21 24 26 27 33 34 · P6 19 |
| JavaScript设计模式（Ross Harmes / Dustin Diaz《Pro JavaScript Design Patterns》中译，人民邮电出版社 2009，全书 17 章：第一部分面向对象基础 + 第二部分具体设计模式） | `JavaScript设计模式-精读缺口.md` | T1 3 4 5 9 10 11 · C3 22 27 · P1 2 3 4 6 7 8 9 10 13 16 19 |
| 精通JavaScript（John Resig《Pro JavaScript Techniques》中译，人民邮电出版社 2008，全书 13 章：现代 JavaScript / 面向对象 / 可重用代码 / 调试测试 / DOM / 事件 / JS 与 CSS / 表单 / 图库 / Ajax / blog / 自动补全 / wiki） | `精通JavaScript-精读缺口.md` | T2 3 4 5 7 8 10 11 · F5 · C2 11 26 28 29 30 |
| JavaScript DOM编程艺术（Jeremy Keith《DOM Scripting: Web Design with JavaScript and the Document Object Model》中译，人民邮电出版社 2007，全书 12 章） | `JavaScript_DOM编程艺术-精读缺口.md` | T1 4 8 · C11 24 |
| 如何阅读一本书（Mortimer J. Adler / Charles Van Doren《How to Read a Book》中译，郝明义 / 朱衣译，145 页带文本层，经 macOS PDFKit 逐页提取） | `如何阅读一本书-精读缺口.md` | T2 · F2 |
| Pro Git（中文版）（Scott Chacon《Pro Git》中译，236 页带文本层，经 macOS PDFKit 逐页提取） | `ProGit中文版-精读缺口.md` | T6 7 · A3 4 · C31 · R3 4 7 |
| GitHub 入门与实践（大塚弘记《GitHub 入门与实践》中译，支鹏浩 / 刘斌译，286 页带文本层，经 macOS PDFKit 逐页提取） | `GitHub入门与实践-精读缺口.md` | T6 · A3 · R3 4 7 |
| MongoDB 权威指南（Kristina Chodorow《MongoDB：The Definitive Guide》中译，192 页扫描版，经 macOS Vision OCR 提取） | `MongoDB权威指南-精读缺口.md` | T9 10 11 · A4 6 · C31 |
| 深入学习 MongoDB（Kristina Chodorow《Scaling MongoDB》中译，145 页扫描版，经 macOS Vision OCR 提取） | `深入学习MongoDB-精读缺口.md` | T3 4 9 10 11 · A4 6 |
| TCP/IP 详解卷 1：协议（W. Richard Stevens《TCP/IP Illustrated, Volume 1: The Protocols》中译，423 页带文本层，经 macOS PDFKit 逐页提取） | `TCP_IP详解卷1：协议-精读缺口.md` | T3 4 8 9 10 11 · A4 · C23 31 |
| TCP/IP 详解卷 2：实现（Gary R. Wright / W. Richard Stevens《TCP/IP Illustrated, Volume 2: The Implementation》中译，872 页带文本层，经 macOS PDFKit 逐页提取） | `TCP_IP详解卷2：实现-精读缺口.md` | T3 4 7 8 14 · A4 · F4 · C1 19 23 39 |
| TCP/IP 详解卷 3：TCP 事务协议，HTTP，NNTP 和 UNIX 域协议（W. Richard Stevens《TCP/IP Illustrated, Volume 3: TCP for Transactions, HTTP, NNTP, and the UNIX Domain Protocols》中译，250 页带文本层，经 macOS PDFKit 逐页提取） | `TCP_IP详解卷3：TCP事务协议，HTTP，NNTP和UNIX域协议-精读缺口.md` | T8 10 11 · A4 · F4 · C7 16 17 18 |
| Linux 内核设计与实现（第三版）（Robert Love《Linux Kernel Development（第三版）》中译，353 页扫描版，经 macOS Vision OCR 提取） | `Linux内核设计与实现（第三版）-精读缺口.md` | T3 4 6 9 10 11 14 · C16 17 |
| 深入理解计算机系统（Randal E. Bryant / David R. O'Hallaron《Computer Systems: A Programmer's Perspective》中译「深入理解计算机系统」，2001-11-16 Beta Draft，1616 页混合 PDF：第 1–833 页中文扫描版经 macOS Vision OCR 逐页识别、第 834–1616 页英文 Beta Draft 文本层经 macOS PDFKit 逐页提取） | `深入理解计算机系统-精读缺口.md` | T3 4 8 9 10 11 13 14 · C18 19 37 |
| 图解HTTP（上野宣《图解HTTP》中译，人民邮电出版社 2014，全书 11 章：网络基础 / HTTP 协议 / 报文 / 状态码 / 协作服务器 / 首部 / HTTPS / 认证 / 追加协议 / Web 内容 / 攻击技术） | `图解HTTP-精读缺口.md` | T8 9 10 11 14 · A4 · C2 31 · P9 10 |
| MySQL 技术内幕：InnoDB 存储引擎（姜承尧著，机械工业出版社 2010，全书 10 章扫描版，经 macOS Vision OCR 逐页识别） | `MySQL技术内幕：InnoDB存储引擎-精读缺口.md` | T3 4 8 9 10 11 · C2 39 · A4 6 |
| Docker 容器与容器云（第 2 版）（浙江大学 SEL 实验室著，人民邮电出版社 2016，全书 8 章 + 附录扫描版，经 macOS Vision OCR 逐页识别） | `Docker容器与容器云（第2版）-精读缺口.md` | T1 3 4 6 7 10 11 · C31 · P6 · A2 6 |
| UNIX 环境高级编程（第三版）（W. Richard Stevens / Stephen A. Rago《Advanced Programming in the UNIX Environment》第 3 版中译，全书 19 章扫描版，经 macOS Vision OCR 逐页识别） | `UNIX环境高级编程(第三版)-精读缺口.md` | T8 9 10 11 · C16 17 18 19 35 38 39 |
| UNIX 网络编程卷 1：套接字 API（W. Richard Stevens《UNIX Network Programming, Volume 1: The Sockets Networking API》第 2 版中译，施振川 / 周利民 / 孙宏晖等译，清华大学出版社，全书 27 章 + 附录扫描版，经 macOS Vision OCR 逐页识别） | `UNIX网络编程卷1：套接字API-精读缺口.md` | T4 8 9 10 11 · C16 17 18 19 38 39 · A2 |
| 剑指 Offer：名企面试官精讲典型编程题（何海涛《剑指 Offer》第 1 版，278 页扫描版无文本层，经 macOS Vision OCR 逐页识别） | `剑指offer名企面试官精讲典型编程题-精读缺口.md` | T1 2 3 5 8 9 10 · C1–C40 · F4 |
| 算法心得：高效算法的奥秘（第 2 版）（Henry S. Warren, Jr.《Hacker's Delight, Second Edition》中译「Hacker's Delight」，爱飞翔译，78 页扫描版无文本层，经 macOS Vision OCR 逐页识别） | `算法心得：高效算法的奥秘（第2版）-精读缺口.md` | T5 9 · C20 31 33 37 |
| 算法设计与分析（第 3 版）（Anany Levitin《Introduction to the Design and Analysis of Algorithms, Third Edition》中译，潘彦译，437 页扫描版无文本层，经 macOS Vision OCR 逐页识别） | `算法设计与分析（第3版）-精读缺口.md` | T5 9 10 · C20 33 37 · P5 |
| 现代操作系统（第 3 版）（Andrew S. Tanenbaum《Modern Operating Systems, Third Edition》中译，陈向群 / 马洪兵等译，606 页扫描版无文本层，经 macOS Vision OCR 逐页识别） | `现代操作系统（第3版）-精读缺口.md` | T3 4 9 10 11 13 14 · C19 31 39 · A2 4 |
| JavaScript 高级程序设计（第 3 版）（Nicholas C. Zakas《Professional JavaScript for Web Developers》第 3 版中译，人民邮电出版社 2012，全书 25 章 + 附录） | `JavaScript高级程序设计(第3版)-精读缺口.md` | T3 4 5 8 9 10 11 14 · C7 11 12 19 24 25 27 31 34 · P1–P19 · A4 |
| C++ Primer Plus（第5版）（Stephen Prata《C++ Primer Plus, Fifth Edition》中译，人民邮电出版社 2005，806 页扫描版，经 macOS Vision OCR 逐页提取） | `C++ Primer Plus（第5版）-精读缺口.md` | T1 2 3 6 8 13 14 · C7 19 27 33 34 38 39 40 · P5 · F4 5 |
| 数据结构与算法分析：C语言描述（第2版）（Mark Allen Weiss《Data Structures and Algorithm Analysis in C, Second Edition》中译，机械工业出版社 2004，406 页扫描版，经 macOS Vision OCR 逐页提取） | `数据结构与算法分析：C语言描述（第2版）-精读缺口.md` | T1 2 3 9 10 |
| Node.js实战（Mike Cantelon / Marc Harter / T. J. Holowaychuk / Nathan Rajlich《Node.js in Action》中译，吴海星译，人民邮电出版社 2014，360 页带文本层，经 macOS PDFKit 逐页提取） | `Node.js实战-精读缺口.md` | T1 2 3 4 5 8 9 10 11 14 · C1 7 9 12 13 18 19 20 21 23 24 28 29 30 31 37 38 · P4 7 · F2 4 5 · A4 6 · R1 |
| 深入浅出Node.js（朴灵著，人民邮电出版社 2013，353 页带文本层，经 macOS PDFKit 逐页提取，全书第 1–11 章 + 附录 A–D） | `深入浅出Node.js-精读缺口.md` | T3 4 5 6 8 9 10 11 14 · C1 7 9 31 38 40 · F5 · A6 |

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
