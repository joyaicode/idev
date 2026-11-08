# 《Head First设计模式》精读缺口报告

> 源文本：`scripts/docs/notes/HeadFirst设计模式-OCR.txt`（Eric Freeman / Elisabeth Freeman《Head First Design Patterns》中译「Head First 设计模式」，O'Reilly Taiwan 公司译，中国电力出版社 2007，扫描版无文本层，经 macOS Vision OCR 逐页识别）。本报告为第 84 本精读，对照 `conventions/canon.md`、`conventions/coding-tables.md`、`deliver/references/experts.md` 裁定真缺口。
>
> 边界：编号真源仍只认 `canon.md` 的 T/A/F 与 `coding-tables.md` 的 P/C/R；本书「第 N 章」与 GoF 模式名只作溯源，不建第二套编号。面向对象原则（抽象/封装/继承/多态与九个 OO 原则）是设计方法论，落阶段页；23 个 GoF 模式是 `coding-tables.md` §1 P1–P19 的场景实现，不改 T/C/P/R 计数。

## 一、精读范围

全书正文（第 1–14 章）与附录 A 读完，主区间如下（行号指 `HeadFirst设计模式-OCR.txt`，书页号随注）：

- **第 1 章 设计模式入门**（书页 2–34，L1640 起）：模拟鸭子应用、继承 / 接口的取舍、分开变化和不变部分（L1889）、封装行为、「有一个」比「是一个」更好、策略模式（Strategy）、OO 原则总览（抽象 / 封装 / 继承 / 多态）。
- **第 2 章 观察者模式**（书页 36–74，L3035 起）：出版者 + 订阅者 = 观察者模式（Observer）、一对多关系、松耦合、Java 内建观察者。
- **第 3 章 装饰者模式**（书页 76–105，L5430 起）：装饰对象（Decorator）、继承滥用、装饰者过度使用会让程序变复杂（L5921）。
- **第 4 章 工厂模式**（书页 106–140，L6053 起）：简单工厂、工厂方法（Factory Method）、抽象工厂（Abstract Factory）、从复杂依赖脱困。
- **第 5 章 单例模式**（书页 141–159）：单例（Singleton）、多线程单例。
- **第 6 章 命令模式**（书页 160–189）：命令模式（Command）、队列请求、日志请求。
- **第 7 章 适配器与外观模式**（书页 190–217）：适配器（Adapter）、外观（Facade）、最少知识原则（Law of Demeter）。
- **第 8 章 模板方法模式**（书页 218–241）：模板方法（Template Method）、好莱坞原则（Hollywood Principle）。
- **第 9 章 迭代器与组合模式**（书页 242–273）：迭代器（Iterator）、组合（Composite）、单一职责原则。
- **第 10 章 状态模式**（书页 274–299）：状态（State）、开放-关闭原则。
- **第 11 章 代理模式**（书页 300–321）：代理（Proxy）、远程代理 / 虚拟代理 / 保护代理。
- **第 12 章 复合模式**（书页 322–357）：复合模式、MVC（L1442）、戴着模式的有色眼镜看 MVC。
- **第 13 章 与设计模式相处**（书页 358–377）：模式类目、反模式（L1512）、共享词汇、用模式思考。
- **第 14 章 剩下的模式**（书页 378–393）：Bridge / Builder / Chain of Responsibility / Flyweight / Interpreter / Mediator / Memento / Prototype / Visitor。
- **附录 A 剩下的模式**：成熟、典型、正式的四人组模式概览。

重点复核段落：第 1 章「分开变化和不变部分」与「有一个比是一个更好」（L1889–L2556，书页 8–28）；第 3 章「装饰者过度使用会让程序变复杂」（L5921，书页 105）；第 7 章「最少知识原则」（书页 202–204）；第 8 章「好莱坞原则」（L1230，书页 223–225）；第 13 章「以反模式歼灭恶势力」（L1512，书页 358）。

## 二、对照结论

### 1. 主体原则已被真源覆盖

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| 抽象 / 封装 / 信息隐藏（第 1 章 OO 基本概念） | T3（深模块：接口小、内部厚、信息隐藏） | 承载 |
| 继承与多态的取舍、继承滥用（第 1 章「Joe 想到继承」、第 3 章「继承滥用」） | C27（继承覆写前置条件只能放宽）、T3 | 承载 |
| 分开变化和不变部分、封装变化（第 1 章 L1889） | T3（信息隐藏）、T1（先砍偶然复杂度） | 承载 |
| 针对接口编程，不针对实现编程 | T4（依赖规则与边界）、T3（深模块） | 承载 |
| 组合优于继承（「有一个」比「是一个」更好） | T4、P#（组合）、C27 | 承载 |
| 单一职责原则（第 9 章 SRP） | C1（函数能用「并且」说出两个变更理由就拆开）、T3 | 承载 |
| 开放-关闭原则（第 10 章 OCP） | T13（扩展沿现有契约加，不改已有分支的含义）、T1 | 承载 |
| 依赖倒置原则（DIP） | T4（依赖规则与边界：业务核心不依赖框架与协议） | 承载 |
| 最少知识原则（Law of Demeter，第 7 章） | C22/C23（耦合）、T4（跨上下文只走显式契约） | 承载 |
| 好莱坞原则（Don't call us, we'll call you，第 8 章 L1230） | T4（依赖方向）、P4（追加「通过后做什么」用 SPI/Strategy） | 承载 |
| 里氏替换原则（LSP） | C27（继承覆写时前置条件只能放宽、返回只能收窄） | 承载 |
| 23 个 GoF 设计模式（Strategy/Observer/Decorator/Factory/Singleton/Command/Adapter/Facade/Template/Iterator/Composite/State/Proxy/MVC/Bridge/Builder/Chain/Flyweight/Interpreter/Mediator/Memento/Prototype/Visitor） | P1–P19（`coding-tables.md` §1 场景→运用：工厂/Adapter/Strategy/Command/Decorator/Proxy/Memento/Template/Composite/Builder/Specification 等） | 承载 |
| 何时不该使用模式、避免对模式过度狂热（第 3 章「装饰者过度使用会让程序变复杂」L5921） | T1（先砍偶然复杂度）、F1（模式堆砌）、P6（只有一种实现写具体类型） | 承载 |
| 反模式（第 13 章「以反模式歼灭恶势力」L1512） | F1（模式堆砌：只有 1 个实现的 interface/工厂/策略/事件） | 承载 |
| 共享模式词汇（第 13 章「共享词汇的威力」） | T5（统一语言、命名即设计） | 承载 |
| 用模式思考、先理解问题再选模式（第 13 章「使用模式的心智」） | T1（写出本质问题一句话）、P1–P19（按「正在做的事」匹配，不先想模式名） | 承载 |

### 2. 语言 / 框架 / 工具链知识不落

Java 内建实现（`java.util.Observable`/`Observer`、`java.util.Iterator`、`InputStream` 装饰者、Swing `JButton`/`ActionListener`、`java.lang.reflect.Proxy`）、具体示例（鸭子 / 气象站 / 星巴兹咖啡 / 比萨店 / 遥控器 / 糖果机）是 Java 语言与教学示例，不进产品仓真源（`coding.md` 文首「不抄目录」边界）。

## 三、真缺口

**无。** 本书可推广的设计方法论（抽象 / 封装 / 信息隐藏、继承与多态的取舍、分开变化和不变部分、针对接口编程、组合优于继承、单一职责、开放-关闭、依赖倒置、最少知识、好莱坞、里氏替换、何时不该使用模式、反模式、共享模式词汇、先理解问题再选模式）均已被 T1/T3/T4/T5/T13、C1/C22/C23/C27、F1、P1–P19 承载；23 个 GoF 模式是 `coding-tables.md` §1 P1–P19 的场景实现，Java 内建实现与教学示例是语言课/示例内容，不落真源。

## 四、重点候选裁定（防后人重复发现）

1. **九个 OO 原则不另立。** 单一职责 → C1/T3；开放-关闭 → T13/T1；依赖倒置 → T4；最少知识 → C22/C23/T4；好莱坞 → T4/P4；里氏替换 → C27；组合优于继承 → T4/C27；封装变化 / 针对接口编程 → T3/T4。均已承载。
2. **23 个 GoF 模式不另立。** P1–P19 已按「场景→运用」承载（工厂 P1/P2、Adapter P3、Strategy/SPI P4/P5、具体类型 P6、Decorator P7、Command P8、Chain P9、Proxy P10、Memento P11、Template P12、Composite P13、Builder P14、Specification P18、闭合操作 P19）；GoF 原书报告已单独收口。
3. **何时不该使用模式不另立。** T1（先砍偶然复杂度）、F1（模式堆砌）、P6（只有一种实现写具体类型）已承载；「装饰者过度使用会让程序变复杂」是 F1 的具体表现。
4. **反模式不另立。** F1（模式堆砌）已承载。
5. **共享模式词汇不另立。** T5（统一语言、命名即设计）已承载。
6. **用模式思考、先理解问题再选模式不另立。** T1（本质问题一句话）与 P1–P19（按「正在做的事」匹配）已承载。

## 五、不建议落的内容

- Java 内建实现（`java.util.Observable`/`Observer`、`java.util.Iterator`、`InputStream` 装饰者、Swing、`java.lang.reflect.Proxy`）：语言/标准库事实，不进真源。
- 具体教学示例（模拟鸭子、气象站、星巴兹咖啡、比萨店、遥控器、糖果机、MVC 歌曲）：教学示例，不进真源。
- Head First 学习原则 / 元认知 / 大脑学习法：学习方法论，不进真源。
- 引子 / 谁适合读这本书 / 技术审校 / 致谢 / 业界推荐：版本与致谢信息，不进真源。
