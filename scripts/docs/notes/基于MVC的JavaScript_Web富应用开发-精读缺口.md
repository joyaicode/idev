# 《基于MVC的JavaScript Web富应用开发》精读缺口报告

> 源文本：`scripts/docs/notes/基于MVC的JavaScript_Web富应用开发-全文.txt`（Alex MacCaw《JavaScript Web Applications》中译，电子工业出版社 2012，全书 13 章：MVC / 事件与观察者 / 模型与数据 / 控制器与状态 / 视图与模板 / 依赖管理 / 文件 / 实时 Web / 测试 / 部署 / Spine / Backbone / JavaScriptMVC）。本报告为第 44 本精读，对照 `conventions/canon.md`、`conventions/coding-tables.md` 与 `deliver/references/experts.md` 裁定真缺口。
>
> 边界：编号真源只认 T/A/F 与 P/C/R；本书 jQuery / DOM / Spine / Backbone / JavaScriptMVC 等库与框架内容只作溯源。

## 一、精读范围

全书 13 章读完，文本主区间（53/57 文本页，页 1/4/16/57 为空白页）如下：

- 第 1 章「MVC 与类」（L502–L700，PDF 17–22）：MVC 模式、模型/视图/控制器职责、类与继承。
- 第 2 章「事件与观察者」（L703–L938，PDF 23–39）：jQuery 事件绑定、事件委托、自定义事件、Pub/Sub 发布订阅。
- 第 3 章「模型与数据」（L938–L1143，PDF 39–48）：ORM、JSON 持久化、模型校验、RESTful 数据。
- 第 4 章「控制器与状态」/ 第 5 章「视图与模板」（L1143–L1267，PDF 48–52）：控制器状态管理、视图渲染与绑定。
- 第 6 章「依赖管理」（L1267–L1306，PDF 52–54）：CommonJS / AMD / RequireJS 模块化。
- 第 7 章「文件」/ 第 8 章「实时 Web」（L1306–L1374，PDF 54–56）：WebSocket、Socket.IO、RPC。
- 第 9 章「测试与调试」（L1374–L1409，PDF 56–57）：QUnit / Jasmine 单元测试。
- 第 10 章「部署」与第 11–13 章「Spine / Backbone / JavaScriptMVC」（L1409–L1410，PDF 57）：压缩、性能、框架选型。

重点复核段落：MVC 职责划分 L502–L700（PDF 17–22）；Pub/Sub 发布订阅 L703–L938（PDF 23–32）；ORM 与模型校验 L938–L1143（PDF 39–48）；CommonJS/RequireJS 模块化 L1267–L1306（PDF 52–54）；WebSocket 实时 L1306–L1374（PDF 54–56）。

## 二、对照结论

### 1. 工程原则已被真源承载

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| MVC 关注点分离：模型/视图/控制器各司其职 | T3（深模块：接口小、内部厚）；T4（依赖规则与边界）；C24（业务与语法/协议分层） | 承载 |
| 事件与观察者 / Pub/Sub 解耦组件 | T4（依赖方向，组件不直接依赖）；T10/T11（事件驱动、异步、背压）；A4（失败语义含消息消费拓扑） | 承载 |
| 模型 / ORM / 数据层与持久化 | A4（数据真相之源、派生/副本、一致性等级）；C25（领域概念以裸 string/number 传播 → 建值对象） | 承载 |
| 模型校验：非法输入立刻拒绝 | T8（快速失败）；C2（未列值当合法缺省 → 抛错） | 承载 |
| 控制器状态管理 / 视图与模板绑定 | T14（可变状态默认纯值）；C11（Mapping 只做形状，不做角色推断）；C24 | 承载 |
| 依赖管理 / 模块化（CommonJS / AMD） | T3/T4/T5（边界、公开面、统一语言） | 承载 |
| 实时 Web / WebSocket / 连接管理 | T10/T11（连接池上限、可运维性、背压） | 承载 |
| 测试（QUnit / Jasmine 单元测试） | C26/C28/C29/C30（测试维度）；F5（自证式测试）；verify 阶段页 | 承载 |
| 部署 / 压缩 / 性能 | T9（先正确清晰，再度量再优化，无基线不优化） | 承载 |

### 2. 库与框架内容不落真源

jQuery 事件 API、DOM 操作、Spine / Backbone / JavaScriptMVC 三套 MVC 框架的具体实现与选型、CommonJS/AMD 加载器（Yabble/RequireJS/Sprockets/LABjs）、WebSocket 与 Socket.IO 客户端 API、QUnit/Jasmine 断言语法，均为具体库、框架或工具教程，不构成可执行的工程缺口。

## 三、真缺口

**零缺口。** 本书可推广的工程原则（MVC 关注点分离、事件/观察者解耦、数据层与真相之源、模型校验快速失败、状态与视图分层、模块化依赖管理、实时连接的连接池与背压、测试维度、无基线不优化）已由 T3/T4/T5/T8/T9/T10/T11/T14、A4、C2/C11/C24/C25/C26/C28/C29/C30、F5 承载；其余为 jQuery / Spine / Backbone / JavaScriptMVC 等库与框架教程，不落真源。

## 四、重点候选裁定（防后人重复发现）

1. **MVC / MVP / MVVM 不另立为独立架构条目。** 其本质是“关注点分离 + 依赖方向”，已由 T3/T4/C24 承载；把某一种前端架构模式固化成通用规则会与多语言仓的既有边界重复。
2. **Pub/Sub 发布订阅不另立为独立模式。** 其“组件通过事件解耦、不直接依赖”的风险与收益由 T4（依赖方向）、T10/T11（事件驱动与背压）与 A4（消息消费拓扑）承载；客户端级 Pub/Sub 是具体实现手段。
3. **ORM / 数据层抽象不另立。** 数据真相之源、派生与一致性已由 A4 与 C25 承载；具体 ORM 库（Spine/Backbone 的 sync）是工具选择。
4. **CommonJS / AMD / ES module 加载器不另立。** 现代 ES module 已统一；其“边界与公开面”由 T3/T4/T5 承载，不把历史加载器（Yabble/RequireJS/LABjs）固化成规则。
5. **WebSocket / Socket.IO 具体 API 不另立。** 实时连接的架构要求（连接池、背压、可运维性、关联标识）已由 T10/T11 承载；具体传输协议与库是选型。
6. **Spine / Backbone / JavaScriptMVC 三框架对比不另立。** 属框架选型；工程原则已由上述条目承载，不把框架 API 抄进真源。

## 五、不建议落的内容

- MVC 三框架（Spine / Backbone / JavaScriptMVC）的类、事件、模型、视图 API 目录：框架教程，非工程缺口。
- jQuery 事件绑定 / 委托 / 自定义事件 / DOM 操作的逐条 API：库教程。
- CommonJS / AMD 加载器（Yabble / RequireJS / Sprockets / LABjs）实现目录：历史工具。
- WebSocket / Socket.IO 客户端与 RPC 示例：协议与库教程，架构要求已由 T10/T11 承载。
- QUnit / Jasmine 断言语法目录：测试框架细节，已被 C26/C28/C29/C30 与 verify 阶段页覆盖。
- 书中具体案例（Holla 聊天应用、标签页、PubSub 实现）：只作理解材料。
