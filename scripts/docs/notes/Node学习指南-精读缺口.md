# 《Node学习指南》精读缺口报告

> 源文本：`scripts/docs/notes/Node学习指南-OCR.txt`（Shelley Powers《Learning Node》中译，夏思雨、高亮译，人民邮电出版社 2014，379 页扫描版无文本层，经 macOS Vision OCR 识别）。本报告为第 87 本精读，对照 `conventions/canon.md`、`conventions/coding-tables.md` 裁定真缺口。
>
> 边界：编号真源仍只认 `canon.md` 的 T/A/F 与 `coding-tables.md` 的 P/C/R；本书「第 N 章」序号只作溯源，不建第二套编号。Node.js 语言特性与框架教程（Express/Connect/EJS/Jade/Redis/MongoDB/MySQL/Socket.IO/部署工具链）是技术栈参考，不进产品仓真源；可推广的工程原则（异步与事件驱动、模块化与信息隐藏、快速失败与错误传播、异步流程控制、中间件单一职责、鉴权与安全、测试、可运维、先测量再优化）落阶段页，不改 T/C/P/R 计数。

## 一、精读范围

全书 16 章 + 附录读完，文本主区间如下（行号指 `Node学习指南-OCR.txt`，PDF 页号随注）：

- 第 1 章 Node.js：启动与运行：搭建环境、Hello World、异步函数与事件循环、Node 的优势（L803–L1503）。
- 第 2 章 Node 与 REPL：REPL 命令、定制 REPL（L1504–L1980）。
- 第 3 章 Node 核心库：global/process/Buffer、定时器、Servers/Streams/Sockets（TCP/HTTP/UDP）、子进程、域名解析与 URL、Utilities、Events/EventEmitter（L1980–L3761）。
- 第 4 章 Node 模块系统：require 与默认路径、外部模块与 npm、创建自定义模块、发布模块（L3762 之前）。
- 第 5 章 控制流、异步模式和异常处理：Callback 而不使用 Promises、顺序调用/嵌套回调/异常捕获、异步模式与控制流模块（Step/Async）、Node 编码风格（L3762–L4560）。
- 第 6 章 路由寻址、服务文件和中间件：静态文件服务器、Connect 中间件、Routers、Proxies（L4560 之后）。
- 第 7 章 Express 框架：启动与运行、错误处理、Express 与 Connect 的关系、路由、MVC（L4560 之后）。
- 第 8 章 Express、模板系统和 CSS：EJS、Jade、Stylus（L4560 之后）。
- 第 9 章 结构化数据、Node 和 Redis：游戏得分排行榜、消息队列、统计中间件（L4560 之后）。
- 第 10 章 Node 和 MongoDB：原生驱动、Mongoose、重构 Widget 工厂（L4560 之后）。
- 第 11 章 Node 与关系型数据库：db-mysql、node-mysql、Sequelize ORM（L4560 之后）。
- 第 12 章 图形和 HTML5 Video：PDF、ImageMagick、Canvas（L4560 之后）。
- 第 13 章 WebSockets 和 Socket.IO：WebSockets、Socket.IO、Chat（L4560 之后）。
- 第 14 章 测试和调试：Node.js Debugger、单元测试（Assert/Nodeunit）、验收测试（Soda/Selenium/Tobi/Zombie）、性能测试（ApacheBench/Nodeload）、Nodemon（L11986–L14090）。
- 第 15 章 安全及防护：数据加密（TSL/SSL/HTTPS）、安全保存密码、认证/授权及 Passport（OAuth/OpenID/用户名密码）、保护应用程序防止攻击（eval/输入校验/node-validator）、沙箱执行（vm）（L14091–L15026）。
- 第 16 章 扩展和部署：package.json、Forever 保活（L15026 之后）。

重点复核段落：第 5 章「回调函数的第一个参数始终是一个 error 对象」「嵌套回调保证顺序」「if (err) throw err」（L3762–L4560）；第 14 章「单元测试/验收测试/性能测试」（L11986–L14090）；第 15 章「如何安全地保存密码」「认证/授权及 Passport」「不要使用 eval」「使用 node-validator」「在沙箱中执行代码」（L14091–L15026）；第 16 章「使用 Forever 让你的应用永不掉线」（L15026 之后）。

## 二、对照结论

### 1. 主体原则已被真源覆盖

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| 异步函数与事件循环（第 1/3 章「异步函数及 Node 事件循环」「不阻塞控制线程」） | C23 显式化状态与顺序约定 / C21 命令查询分离 / T11 外部依赖超时与连接池 | 承载 |
| error-first 回调与异常处理（第 5 章「回调函数的第一个参数始终是一个 error 对象」「if (err) throw err」） | T8 快速失败 / C7 不吞失败 / F4 静默兜底 | 承载 |
| 异步流程控制（第 5 章「嵌套回调保证顺序」「Step/Async 控制流模块」） | C9 卫语句 / C23 显式化 / C20 收敛论证 / C24 业务/语法分层 | 承载 |
| 模块系统与信息隐藏（第 4 章「require 与默认路径」「创建自定义模块」） | T3 深模块 / T4 依赖规则与边界 / T5 统一语言 | 承载 |
| 中间件（第 6 章「Connect 中间件」「定制 Connect 中间件」） | T1 先砍偶然复杂度 / T3 深模块 / C1 单一职责 / C23 显式化 | 承载 |
| Express 错误处理与 MVC（第 7 章「错误处理」「关于 MVC」） | T8 快速失败 / C24 业务/语法分层 / C21 命令查询分离 | 承载 |
| 测试（第 14 章「单元测试/验收测试/性能测试」） | R1 有自检护栏 / F5 自证式测试 / C28 测试金字塔 / C29 随机失败 / C30 过度 mock | 承载 |
| 性能测试（第 14 章「基准问题和负载测试」） | T9 先正确清晰，再度量再优化 | 承载 |
| 安全与防护（第 15 章「数据加密/HTTPS/安全保存密码/Passport/不要使用 eval/输入校验/沙箱」） | C31 密钥/凭证/敏感信息 / C37 边界检查 / P7 鉴权 Decorator | 承载 |
| 部署保活（第 16 章「Forever 让你的应用永不掉线」） | T11 可运维性是架构特性 / A6 指标日志回滚降级灰度 | 承载 |

### 2. 语言/框架教程不落

Node.js 语言/运行时 API（global/process/Buffer、timers、net/http/udp、child_process、dns/url、util、events/EventEmitter、vm）与框架/工具链教程（Express、Connect、EJS、Jade、Stylus、Redis、MongoDB、MySQL、Sequelize、Socket.IO、PDFKit/ImageMagick/Canvas、Forever、测试框架）是技术栈参考，不进产品仓真源。可推广的工程原则已由 T1/T3/T4/T5/T8/T9/T11、A6、F4/F5、P7、C1/C7/C9/C20/C21/C23/C24/C28/C29/C30/C31/C37、R1 等承载。

## 三、真缺口

**零缺口。** 本书是 Node.js 全栈教程，未发现 idev 编号体系尚未承载、且可推广到产品仓的独立工程原则。

## 四、重点候选裁定（防后人重复发现）

1. **异步/事件驱动不另立。** 第 1/3 章「异步函数及事件循环」是 C23/C21/T11 在异步场景的具体表现，不另立。
2. **error-first 回调与快速失败不另立。** 第 5 章「回调函数的第一个参数始终是 error 对象」已由 T8/C7/F4 承载，不另立。
3. **异步流程控制不另立。** 第 5 章「嵌套回调、Step/Async」已由 C9/C23/C20/C24 承载，不另立。
4. **模块化与信息隐藏不另立。** 第 4 章是 T3/T4/T5 的具体表现，不另立。
5. **中间件单一职责不另立。** 第 6 章是 T1/T3/C1/C23 的具体表现，不另立。
6. **测试金字塔与性能测试不另立。** 第 14 章已由 R1/F5/C28/C29/C30/T9 承载，不另立。
7. **鉴权与安全不另立。** 第 15 章「HTTPS、安全保存密码、Passport、eval、输入校验、沙箱」已由 C31/C37/P7 承载，不另立。
8. **可运维与保活不另立。** 第 16 章「Forever」已由 T11/A6 承载，不另立。

## 五、不建议落的内容

- Node.js 核心 API（global/process/Buffer、timers、net/http/udp、child_process、dns/url、util、events/EventEmitter、vm）：语言/运行时教程，不进真源。
- Express/Connect 框架（路由、中间件、错误处理、MVC）：框架教程，不进真源。
- 模板引擎与样式（EJS、Jade、Stylus）：模板语法教程，不进真源。
- 数据存储客户端（Redis、MongoDB、MySQL、Sequelize ORM）：数据库教程，不进真源。
- 图形与媒体（PDFKit、ImageMagick、Canvas、HTML5 Video）：媒体处理教程，不进真源。
- WebSockets 与 Socket.IO：实时通信教程，不进真源。
- 测试框架（Assert、Nodeunit、Soda、Selenium、Tobi、Zombie、ApacheBench、Nodeload）：测试工具教程，不进真源。
- 部署工具链（Forever、Nodemon、package.json）：运维工具教程，不进真源。
- 书中代码清单与伪码例程：只作理解材料，不进真源。
- 序 / 前言 / 致谢 / 版权声明 / 内容提要 / 译者注 / 目录 / 索引：版本与致谢信息，不进真源。
