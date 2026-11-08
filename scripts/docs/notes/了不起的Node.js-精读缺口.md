# 《了不起的Node.js》精读缺口报告

> 源文本：`scripts/docs/notes/了不起的Node.js-OCR.txt`（Guillermo Rauch《Smashing Node.js: JavaScript Everywhere》中译，Goddy Zhao 译，电子工业出版社 2014，313 页扫描版无文本层，经 macOS Vision OCR 识别）。本报告为第 86 本精读，对照 `conventions/canon.md`、`conventions/coding-tables.md` 裁定真缺口。
>
> 边界：编号真源仍只认 `canon.md` 的 T/A/F 与 `coding-tables.md` 的 P/C/R；本书「第 N 章」序号只作溯源，不建第二套编号。Node.js 语言特性与框架教程（fs/net/http/Connect/Express/WebSocket/Socket.IO/MongoDB/MySQL/Redis/测试工具链）是技术栈参考，不进产品仓真源；可推广的工程原则（异步与事件驱动、模块化与信息隐藏、快速失败与错误传播、资源成对释放、异步流程控制、中间件单一职责、鉴权与安全、测试、可运维、先测量再优化、环境差异收拢）落阶段页，不改 T/C/P/R 计数。

## 一、精读范围

全书 16 章（五大部分）读完，文本主区间如下（行号指 `了不起的Node.js-OCR.txt`，PDF 页号随注）：

- 第 1 章 安装：Windows/OS X/Linux 安装、编译、Node REPL、执行文件、NPM（L900–L1255）。
- 第 2 章 JavaScript 概览：类型、函数、this/call/apply、闭包、类、继承、try/catch、V8 特性（L1256–L1621）。
- 第 3 章 阻塞与非阻塞 IO：阻塞、单线程的世界、错误处理（uncaughtException/error 事件/error-first 回调）、堆栈追踪（L1622–L1800）。
- 第 4 章 Node 中的 JavaScript：global 对象、模块系统（绝对/相对模块、暴露 API）、事件、buffer（L1800–L2201）。
- 第 5 章 编写首个 Node 程序：需求、创建模块、同步还是异步、流、fs、CLI（argv/工作目录/环境变量/退出/信号）、监视（L2202–L2782）。
- 第 6 章 TCP：TCP 特性（面向连接/保证顺序/字节/可靠性/流控制/拥堵控制）、Telnet、聊天程序、net.Server/net.Stream API、IRC 客户端（L2783–L3358）。
- 第 7 章 HTTP：HTTP 结构、头信息、简单 Web 服务器、让程序更健壮、Twitter Web 客户端、superagent、up 重启（L3359–L3784）。
- 第 8 章 Connect：中间件、书写可重用的中间件、static/query/logger/body parser/cookie/session/basicAuth 中间件（L3785–L4190）。
- 第 9 章 Express：小型应用、SETUP、路由、模板引擎、错误处理、中间件、代码组织策略（L4190–L4536）。
- 第 10 章 WebSocket：Ajax、HTML5 WebSocket、ECHO 示例、关闭与断开、JSON、重连、广播（L4536–L4900）。
- 第 11 章 Socket.IO：传输、断开 VS 关闭、事件、命名空间、聊天程序、DJ 应用（L4900–L5300）。
- 第 12 章 MongoDB：用户认证示例、创建/查找文档、身份验证中间件、校验、原子性、安全模式、Mongoose（模型/嵌套键/索引/中间件/查询）（L5300–L6100）。
- 第 13 章 MySQL：node-mysql、sequelize ORM（L6100–L6600）。
- 第 14 章 Redis：Redis 查询语言、数据类型、node-redis 社交图谱（L6600–L7100）。
- 第 15 章 代码共享：什么样的代码可以共享、书写兼容的 JavaScript 代码、导出模块、模拟实现 API、browserbuild（L7100–L10089）。
- 第 16 章 测试：简单测试、测试目标、测试策略、expect.js、Mocha、测试异步代码、BDD/TDD/export 风格、浏览器端 Mocha（L10090–L10859）。

重点复核段落：第 3 章「错误处理：uncaughtException、error 事件、error-first 回调」「每步都要正确进行错误处理」（L1622–L1800）；第 5 章「同步还是异步」「理解什么是流」（L2202–L2782）；第 7 章「让程序更健壮」（L3359–L3784）；第 8 章「书写可重用的中间件」（L3785–L4190）；第 12 章「身份验证中间件、校验、原子性、安全模式」（L5300–L6100）；第 15 章「书写兼容的 JavaScript 代码」（L7100–L9000）；第 16 章「测试异步代码、BDD/TDD 风格」（L10090–L10859）。

## 二、对照结论

### 1. 主体原则已被真源覆盖

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| 阻塞与非阻塞 IO、单线程（第 3 章「阻塞与非阻塞 IO」「单线程的世界」） | C23 显式化状态与顺序约定 / C21 命令查询分离 / T11 外部依赖超时与连接池 | 承载 |
| 错误处理（第 3 章「uncaughtException、error 事件、error-first 回调」「每步都要正确进行错误处理」） | T8 快速失败 / C7 不吞失败 / F4 静默兜底 / C38 不自行终止进程 | 承载 |
| 模块系统与暴露 API（第 4/5 章「模块系统」「暴露 API」「创建模块」） | T3 深模块（公开面最小）/ T4 依赖规则与边界 / T5 统一语言 | 承载 |
| 同步还是异步（第 5 章「同步还是异步」「理解什么是流」） | C23 显式化 / C21 命令查询分离 | 承载 |
| 让程序更健壮（第 7 章「让程序更健壮」） | T8 快速失败 / C7 不吞失败 | 承载 |
| 中间件单一职责与可重用（第 8 章「书写可重用的中间件」） | T1 先砍偶然复杂度 / T3 深模块 / C1 单一职责 / C23 显式化 | 承载 |
| Express 错误处理与代码组织（第 9 章「错误处理」「代码组织策略」） | T8 快速失败 / C24 业务/语法分层 | 承载 |
| 鉴权、校验与原子性（第 12 章「身份验证中间件、校验、原子性、安全模式」） | P7 鉴权 Decorator / C31 密钥凭证 / C37 边界检查 / A4 一致性等级 | 承载 |
| 跨环境代码共享（第 15 章「书写兼容的 JavaScript 代码」「模拟实现 API」） | C16 只用共同子集 / C17 环境差异收拢为类型或独立实现 | 承载 |
| 测试（第 16 章「测试目标、测试策略、expect.js、Mocha、测试异步代码、BDD/TDD」） | R1 有自检护栏 / F5 自证式测试 / C28 测试金字塔 / C29 随机失败 / C30 过度 mock | 承载 |

### 2. 语言/框架教程不落

Node.js 语言/运行时 API（global、fs、net、http、stream、buffer、events、process、child_process）与框架/工具链教程（Connect、Express、WebSocket、Socket.IO、MongoDB/Mongoose、MySQL/sequelize、Redis/node-redis、superagent、browserbuild、expect.js/Mocha）是技术栈参考，不进产品仓真源。可推广的工程原则已由 T1/T3/T4/T5/T8/T9/T11、A4/A6、F4/F5、P7、C1/C7/C16/C17/C21/C23/C24/C28/C29/C30/C31/C37/C38、R1 等承载。

## 三、真缺口

**零缺口。** 本书是 Node.js「Learning by Doing」教程，未发现 idev 编号体系尚未承载、且可推广到产品仓的独立工程原则。

## 四、重点候选裁定（防后人重复发现）

1. **异步/非阻塞 IO 不另立。** 第 3 章「阻塞与非阻塞 IO、单线程」是 C23/C21/T11 在异步场景的具体表现，不另立。
2. **错误处理不另立。** 第 3 章「uncaughtException、error 事件、error-first 回调、每步都要正确错误处理」已由 T8/C7/F4/C38 承载，不另立。
3. **模块化与信息隐藏不另立。** 第 4/5 章「模块系统、暴露 API」是 T3/T4/T5 的具体表现，不另立。
4. **中间件单一职责与可重用不另立。** 第 8 章「书写可重用的中间件」是 T1/T3/C1/C23 的具体表现，不另立。
5. **鉴权、校验与原子性不另立。** 第 12 章「身份验证中间件、校验、原子性、安全模式」已由 P7/C31/C37/A4 承载，不另立。
6. **跨环境代码共享不另立。** 第 15 章「书写兼容的 JavaScript 代码」已由 C16/C17 承载，不另立。
7. **测试不另立。** 第 16 章「测试目标/策略、expect.js、Mocha、测试异步代码」已由 R1/F5/C28/C29/C30 承载，不另立。

## 五、不建议落的内容

- Node.js 核心 API（global、fs、net、http、stream、buffer、events、process、child_process）：语言/运行时教程，不进真源。
- Connect/Express 框架（中间件、路由、模板引擎、错误处理）：框架教程，不进真源。
- WebSocket 与 Socket.IO：实时通信教程，不进真源。
- 数据存储客户端（MongoDB/Mongoose、MySQL/sequelize、Redis/node-redis）：数据库教程，不进真源。
- 工具链（superagent、browserbuild、expect.js、Mocha）：第三方库/测试工具教程，不进真源。
- 书中代码清单与伪码例程：只作理解材料，不进真源。
- 序 / 前言 / 致谢 / 版权声明 / 内容简介 / 译者注 / 目录 / 索引：版本与致谢信息，不进真源。
