# 编码规范（公共）

**现行真源就是本页 + [coding-tables.md](coding-tables.md)。** 改任何代码或写 `review.md` 必须先开本页 §0。  
§1 / §2 / §3 全表只在命中念头、要对号、或 Review 扫表时再开。  
Java 四准则 / SPI 仍在该仓规约页。Qodana 表：[java.md](java.md)。前端 lint 走该仓；有 pilot 时再开该 pack 的前端页。  
阶段清单：[deliver `code`](../deliver/SKILL.md) · [experts.md](../deliver/references/experts.md) · [gates.md](../deliver/references/gates.md) · [review.example.md](../deliver/references/review.example.md)。

不要把 GoF 23 名录、《Clean Code》章节或《重构》全书手法目录抄进产品仓。

上游原则层：[canon.md](canon.md)（T1–T12）。命中“加一层 / 拆分 / 缓存 / 重写”类念头先走 canon §1 协议（§2 信号 + §4 念头），再回本页落到 P/C/R。

裁决先于模式：**YAGNI + Rule of Three。** 第 1 次写具体；第 2 次仍可并列；第 3 次才抽。会说过度设计就简化。  
结构变、行为不变时走 [coding-tables.md](coding-tables.md) §3；缺测试护栏或与加功能混做 = 不准重构。

**规范总则（编码与 Review 共用；命中落 `P#`/`C#`/`T#`，不另起编号）**

1. **控制膨胀**：本轮净增行数要能一句话说出换来什么（消除第 3 次重复 / 收拢散逻辑 / 新基线行为）。说不出的增行命中 **T1**（预置抽象）/ **C3**（两行包装）/ **C6**（未引用符号）。
2. **高内聚低耦合**：一个文件只为一种变更理由改动（C12 到文件级）；跨模块只走显式契约（**T4**）；职责不同的两条通道不合流（**P16**）。
3. **条件链先上模式**：按类型分派已有 ≥2 分支且还会增，先扫 §1 **P5**（Strategy / 经典 switch / 查表）；零命中才写直白 if 链。
4. **语法糖优先**：在该仓语言级别内先用语法糖减行（Java 见 [java.md](java.md) 四准则 2；Go 表驱动 / 函数值 / composite literal；Vue/TS 查表 + `computed` + 早返回）。不以「更明确」为由写笨代码。
5. **复杂度有界**：[coding-tables.md](coding-tables.md) §2.4 全表（函数级五行 + 变更级两行）；超线要么当轮改，要么 `review.md` 写清为何允许并落 `C#`。

---

## 0. 自动运用（编码 / Review 都要跑）

**编码（写第一行之前）**

1. 用一句话说清本轮变化：校验？换协议？追加行为？加头？两通道？**只改结构**还是**也改可观察行为**？
2. 若本轮含结构调整：先过 [coding-tables.md](coding-tables.md) §3「满足条件」；不满足就先补测试 / 拆轮次，不准硬改。
2a. 若这句话涉及**新增一层、拆分、缓存、队列、重试、重写、新依赖**：先按 [canon.md](canon.md) §1 协议扫 §2 信号与 §4 念头，命中即停并按 DO 做，`review.md` 记 `T#`。
3. 用这句话扫 [coding-tables.md](coding-tables.md) §1，命中**第一行**就停，按「运用」做，按「不要」拒绝。
4. 零命中 → 写具体类型，**不准**为对称先上模式。
5. 每新增一个函数 / 导出，立刻扫 [coding-tables.md](coding-tables.md) §2 + §2.4 量化阈值；命中当场改，不准留到「写完再说」。气味驱动的结构整理按 §3 小步做。
6. 写完按文首**规范总则**回扫本轮 diff：净增行说得出换来什么、一文件一变更理由、条件链过了 §1、语法糖用了、§2.4 变更级两行已扫。

**Review（对照基线之后、请人签字之前）**

1. 先扫文首**规范总则**五条（含 [coding-tables.md](coding-tables.md) §2.4 变更级粗筛：净增行去向 / 一文件一理由）；命中译成 `T#`/`P#`/`C#`。
2. 再扫 §1：该用的没用、不该用的用了，都是拒过。
3. 逐条扫 §2：命中必须当轮改掉，只记账不算过。
4. 若有重构：核对 §3 满足条件与「两顶帽子」；混做加功能 / 无护栏绿 = 拒过。
5. 按 §3.8 跑 `bash ~/.cursor/skills/idev/scripts/coding-scan.sh <repo>` + 五轴 + 栈指南；blocking 命中译成 `P#`/`C#` 当轮改。
6. 把命中与纠正写入 `review.md`「编码规范」节（模板见 review.example）；写五轴 / 栈指南 / 增强扫描。
7. 跑该仓扫描（Java Problems / `qodana.starter`；前端 `lint-fix`）。黄条视为未完成。

**例外（仅 S8 `review.report`）**：`code-review` 报告步允许只记账并标「待签收」，本步不改代码。`deliver.code_pass` 与 `review.fix` 对已签收 `I*` 仍当轮必改。全文 [workflow-code-review.md](../references/workflow-code-review.md)。

命令式代码读一遍说不出失败条件 = 还在兜底 = §2 命中。

**写的时候对念头（命中立刻改，不准写完再扫）**

| 听到自己在想 | 立刻 |
|--------------|------|
| 空就跳过 / 用配置默认值补 | C2 + P15，立刻抛 |
| 再包一层 `currentX` / 两行转一手 | C3，删包装 |
| 抽 `IXxx`，以后好扩展 | P6，写具体类型 |
| 拦截器顺便带上业务查询字段 | P16，两条通道分开 |
| 看起来重复，合成一个 | P17，先问省略规则是否相反 |
| 这段复制第三遍了 | P1，静态工厂，非法即抛 |
| `of(..., null)` 两种语义 | P2，两个工厂 |
| 只有一种实现也先接口 | P6 |
| 页面和 Controller 各写一份分支 | P5，收到一处 |
| 产品仓再写一套登录解析 | P9，用已有链 |
| 回放再猜默认身份 | P11，只用快照 |
| 布尔参数切两种创建 | C8 |
| 函数名能用「并且」 | C1，拆开 |
| `catch` 后返回空 | C7，该失败就失败 |
| 名字叫 `util` / `helper` / `manager` | C12，按职责改名 |
| 注释还写遗留 / 以后 | C5，改或删 |
| Review 只写「能跑」 | C14，写 §1/§2 命中行 |
| 顺便把结构也调漂亮再加功能 | §3，换「重构帽」；先绿再改结构，加功能另轮 |
| 没测、想大改目录 / 抽公共 | §3 不满足，先补触及面测试或缩小步子 |
| 第三次同样逻辑还在复制 | P1 + §3 Rule of Three，提取并保持行为不变 |

念头命中后打开 [coding-tables.md](coding-tables.md) 对应该行，按「运用 / 不要 / 纠正」做完再写下一处。

---

## 3.5 编号真源（禁止第二套表号）

| 编号 | 含义 | 全表 |
|------|------|------|
| `T1`–`T12` / `A1`–`A8` / `F1`–`F7` | 架构原则 / 架构出门 / Agent 失败模式 | [canon.md](canon.md) |
| `P1`–`P17` | 场景 → 模式 | [coding-tables.md](coding-tables.md) §1 |
| `C1`–`C15` | 气味 → 纠正 | [coding-tables.md](coding-tables.md) §2 |
| `R1`–`R6` | 重构满足条件 | [coding-tables.md](coding-tables.md) §3 |

仓内 `<票目录>/current.md`、clean-code 票、`review.md` **必须用上表编号**。禁止另起「表号 / 气味码 / 模式码」。  
产品仓自己的编码页是四准则 / SPI / 运行时，不是第二套 P/C 表。

---

## 5. 写完 / Review 出门

- [ ] §1 已匹配或确认零命中（全表在 coding-tables.md）
- [ ] §2 全表扫过，命中已改
- [ ] §2.4 量化阈值已扫（函数≤20行 / 嵌套≤2 / 参数≤3 / 复杂度≤10 / 无三次重复 / 净增行可解释 / 一文件一理由）；超线已改或 `review.md` 写清理由并落 `C#`
- [ ] 若有结构调整：§3 R1–R6 满足，且 `review.md` 写了重构动机与护栏
- [ ] 已按 §3.8 做增强扫描（`coding-scan.sh` + 五轴 + 栈指南）；blocking 已改
- [ ] `review.md` 用本页 `P#`/`C#`/`R#`；写了命中行与纠正；写了五轴 / 栈指南 / 增强扫描
- [ ] `check-feature.sh <feature> code` 已 PASS（含编码规范弱门禁）
- [ ] 废弃符号已删；注释/文档与代码一致
- [ ] Java：Problems / `qodana.starter` 无本轮黄条；前端：扩展根 `commands.lint_fix` 干净。没有这个键就问人，不猜命令

违反本页 = `code` 拒过。  
`review.report` 出门：`I*` / `O*` / UNPROVEN 已记即可，不要求本步已改，不跑 `check-feature code`。`review.fix` 用上表。
