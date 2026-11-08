# 《JavaScript DOM编程艺术》精读缺口报告

> 源文本：`scripts/docs/notes/JavaScript_DOM编程艺术-OCR.txt`（Jeremy Keith《DOM Scripting: Web Design with JavaScript and the Document Object Model》中译，人民邮电出版社 2007，全书 12 章）。本报告为第 58 本精读，对照 `conventions/canon.md`、`conventions/coding-tables.md` 与 `deliver/references/experts.md` 裁定真缺口。
>
> 边界：编号真源只认 T/A/F 与 P/C/R；本书 JavaScript 语法 / DOM / 事件 / 动画 / CSS-DOM / HTML5 等前端教程只作溯源。

## 一、精读范围

全书 12 章读完，OCR 主区间如下：

- 第 1 章「JavaScript 简史」（L1030–L1273，PDF 22–30）：语言起源、DOM 标准、浏览器不兼容。
- 第 2 章「JavaScript 语法」（L1274–L2142，PDF 30–46）：语句、变量、数组、对象、函数、条件、循环。
- 第 3 章「DOM」（L2143–L2672，PDF 46–57）：DOM 树、节点类型、getElementById/getElementsByTagName/getAttribute。
- 第 4 章「案例研究：JavaScript 美术馆」（L2673–L3271，PDF 57–70）：图片切换、事件处理函数、占位符。
- 第 5 章「JavaScript 编程原则和良好习惯」（L3272–L3749，PDF 70–99）：预留退路、分离 JavaScript、向 CSS 学习、循序渐进。
- 第 6 章「案例研究：JavaScript 美术馆改进版」（L3750–L4643，PDF 99–123）；第 7 章「动态创建 HTML 内容」（L4644–L5496，PDF 123–146）；第 8 章「充实文档的内容」（L5497–L6698，PDF 146–177）；第 9 章「CSS-DOM」（L6699–L7719，PDF 177–204）；第 10 章「用 JavaScript 实现动画效果」（L7720–L9051，PDF 204–241）；第 11 章「学以致用：JavaScript 网站设计实战」（L9052–L10803，PDF 241–287）；第 12 章「展望 DOM 脚本编程技术」（L10804–L11991，PDF 287–…）。

重点复核段落：预留退路与渐进增强 L3392–L3578（PDF 89–94）；分离 JavaScript 与向 CSS 学习 L3578–L3749（PDF 94–99）；三层分离（结构/表现/行为）L3578–L3749（第 5 章）。

## 二、对照结论

### 1. 工程原则已被真源承载

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| 分离 JavaScript：把网页结构与内容同脚本动作行为分开 | T4（依赖规则与边界，业务核心不依赖框架/协议）；C11（Controller/Mapping 只做形状，不做角色推断）；C24（业务与语法/协议分层） | 承载 |
| 内容/表现/行为三层分离（向 CSS 学习） | T4（依赖方向）；C24（按层级拆函数：高层说业务，低层说语法） | 承载 |
| 预留退路（graceful degradation）：无 JavaScript 时基本操作仍能完成 | T4（业务核心不依赖框架/协议）；T8（快速失败，不静默兜底） | 承载 |
| 循序渐进（progressive enhancement）：额外信息层包裹原始数据，不强依赖增强层 | T4（依赖方向，核心不依赖增强层）；T1（先砍偶然复杂度） | 承载 |
| 避免 `javascript:` 伪协议与内嵌事件处理函数 | C11（Mapping 只做形状）；T4（依赖方向）；C24 | 承载 |
| 以用户为中心 / 可访问性 | 交付基线、产品判断；可执行部分由 T4/T8 承载 | 原则承载 |

### 2. 语言与工具内容不落真源

JavaScript 语法、DOM 树与节点操作、事件处理函数、`window.open`/BOM、动画、CSS-DOM、HTML5 新特性、Ajax（Hijax）、图片库与幻灯片案例，均为前端语言与工具教程，不构成可执行的工程缺口。

## 三、真缺口

**零缺口。** 本书可推广的工程原则（分离 JavaScript、内容/表现/行为三层分离、预留退路、循序渐进、避免伪协议与内嵌事件）已由 T1/T4/T8、C11/C24 承载；其余为 JavaScript/DOM/CSS/HTML5 前端教程，不落真源。

## 四、重点候选裁定（防后人重复发现）

1. **预留退路 / 渐进增强不另立为独立条目。** 其本质是“核心不依赖增强层、无 JS 仍可用”，已由 T4（依赖方向）与 T8（快速失败）承载；再加一条会与既有条目重复。
2. **分离 JavaScript（Unobtrusive JavaScript）不另立。** 其本质是“内容/表现/行为分离”，已由 T4、C11、C24 承载。
3. **避免 `javascript:` 伪协议与内嵌事件处理函数不另立。** 属前端反模式；其“行为与结构分离”由 C11/C24 承载，不把具体 HTML 写法固化成通用规则。
4. **向 CSS 学习的三层分离不另立。** 已由 C24（按层级拆函数）承载；前端三层（结构/表现/行为）是具体技术栈的分离方式。
5. **Hijax（渐进增强式 Ajax）不另立。** 属前端技术；异步纪律由 T10/T11 承载，具体 Hijax 写法是工具教程。

## 五、不建议落的内容

- JavaScript 语法、DOM 树导航、节点操作、事件处理、动画等前端语言教程：学习向。
- `window.open`/BOM、`javascript:` 伪协议、内嵌事件处理函数的具体写法：前端反模式细节。
- CSS-DOM、HTML5、Ajax（Hijax）的具体实现：工具教程。
- 书中具体案例（JavaScript 美术馆、图片库、幻灯片、动态创建标记）：只作理解材料。
