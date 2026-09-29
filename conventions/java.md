# Java 领域（按仓）

以**当前仓** compiler 为准。不要把某一个产品的语言级别写成 idev 默认。compiler=8 的仓：无 `record` / `var` / text block。四准则正文在该仓自己的编码规约页。

## 语言级别（以仓为准）

1. 先看该仓 `pom.xml` / `maven.compiler.release|source|target` / Spring `java.version`。
2. compiler=8 的仓按 Java 8 写；分析器 JDK（如 `qodana.yaml` 的 `projectJDK: 17`）不授权把业务代码写成更高语法。
3. 升 11/17 的仓以该仓 compiler 为准，并在该仓规约写明。
4. **不要**在 compiler=8 的仓用 `List.of` / `record` / `var` / text block。

**编辑器 / Qodana 卫生：compiler=8 时现行真源就是本页。** 仓内四准则页若尚未同步，以本页 Qodana 表为准，不要默默升语法。

1. **收敛文件** — Query / Result / Exception / 小枚举嵌在公开接口或同文件；禁止 `model/` 下一文件一类。
2. **语法糖减代码** — 接口 `default`、Lombok `@Value`/`@Builder`、静态工厂、包可见工具、lambda / 钻石 `<>` / 经典 `switch`。不要匿名 Consumer、不要 `new ArrayList<String>()`、不要 `Integer.valueOf` / `.intValue()`、不要 switch 表达式。覆盖 `@NonNullApi` 用 `javax.annotation.Nonnull`。无用 import / 无用方法当场删。
3. **禁止贫血** — 校验、归一、派生状态跟类型走。`*Mappings` 只做协议形状，不做健康度 / 就绪 / 状态机。
4. **接口 + SPI** — 调用方只依赖公开接口。整类替换用 MissingBean；追加用多例 SPI。层内适配器不泄漏给 Controller / 产品代码。

YAGNI：单实现先写具体类型，不滥抽 `IXxx`。新能力：公开接口 + 默认实现 + `enabled` + enabled/disabled `*IT`。

编码规范入口见 [coding.md](coding.md) §0；全表见 [coding-tables.md](coding-tables.md)。本页只留四准则摘要与（compiler=8 时）Qodana 表。产品接入层取值不写在本页；有 pilot 时见该 pack。

## 编辑器 / Qodana（compiler=8，禁止留低端提示）

写完 Java 先当 `qodana.starter` 会扫，并打开 Problems。`qodana.yaml` 的 `projectJDK` 可能高于语言级别，**代码仍按该仓 compiler 写**。下列黄条在 compiler=8 仓视为未完成，禁止留下。

| 提示（中文） | 改法（Java 8） |
|------|------|
| 方法从未使用 | 删掉，或本文件立刻用上。禁止留「以后用」 |
| 不必要的装箱 | 不要 `Integer.valueOf(n)` / `Boolean.valueOf`；`return n` 即可 |
| 不必要的拆箱 | 不要 `.intValue()` / `.booleanValue()`；比较落到 `int`，或走类型自己的包含方法 |
| 显式类型参数可被替换为 `<>` | `new HashMap<>()`，禁止 `new HashMap<String, String>()` |
| 显式类型参数可以推断 | `Collections.emptySet()`，禁止 `Collections.<String>emptySet()` |
| 可替换为 `Map.computeIfAbsent()` | `get` + null 再 `put` 改成 `computeIfAbsent(k, x -> new HashSet<>())` |
| 可替换为集合工厂方法 | 只用 `Collections.empty*` / `singleton` / `unmodifiable*`。**禁止** `List.of` / `Set.of` / `Map.of` |
| 无用 import | 当场删 |

| 必做 | 不要 |
|------|------|
| 构造 `new Foo<>()`；能推断则 `Collections.emptyList()` 不写 `<T>` | 声明上剥掉 `Optional<T>` / `Stream<T>`（那不是钻石） |
| 无用 import / 无用方法当场删 | 为「看起来整齐」留着未引用类型或未调用方法 |
| 简单 getter/setter 用 Lombok（该模块**已有** lombok） | 无 lombok 的模块为消提示硬加 `@Getter`；有自定义空合并/拷贝的 getter 不要 `@Getter` |
| 覆盖 Spring `@NonNullApi` 的形参标 **`javax.annotation.Nonnull`**（JSR-305） | 只写 `org.springframework.lang.NonNull`：`qodana.starter` 的 `NullableProblems` 仍会报 |
| 公开方法 / `@Bean` 的返回类型必须是 **public** | 包可见类型从 public SPI 漏出（`ClassEscapesItsScope`） |
| `!stream.anyMatch` → `noneMatch`；手写大小比较 → `Math.max` / `Math.min`；匿名 `Runnable` → lambda | 为「更明确」保留恒真/恒假的 `== null`（如 `Resource[] getResources`、已归一的 `queryMap` / `emptyList()`） |
| 上游已判 `Boolean == null` 后直接用 boolean | 无必要的 `Boolean.TRUE.equals`；`catch (X e) { throw e; }`（后面的 catch 本就不会吃到 `X`） |
| String / enum 多分支配 **经典 `switch`**（`case x:`）；辅助类嵌进主类；覆盖已弃用 Servlet 方法时自己标 `@Deprecated` | `->` / switch 表达式；同文件第二份顶层 class；只写不读的 `ByteArrayOutputStream` |

启动类上 Eureka / Feign 解析失败若是 **Qodana 模块 classpath**，不要为消 Sanity 撕生产注解。


## 可选静态分析（仓内有则跑）

| 工具 | 何时 | 说明 |
|------|------|------|
| Checkstyle / Spotless | 仓内已配插件 | 格式/命名；不替代 [coding-tables.md](coding-tables.md) §1/§2 |
| PMD | 仓内已配 | 坏味道；命中用 `C#` 记入 review |
| SpotBugs / Find Security Bugs | 仓内已配 | bug 模式；同上 |
| Error Prone | 仓内已配 | 编译期检查 |

仓内已配则跑。未配置的工具**不要**为消 idev 门禁临时堆进父 POM。主门禁以该仓已有的静态检查为准。


## 增强扫描（Java）

`code` 阶段在 Problems / Qodana 之外，按 [coding-tables.md](coding-tables.md) §3.8：

1. `bash ~/.cursor/skills/idev/scripts/coding-scan.sh <repo>`
2. 按该仓 compiler 打开对应的 `code-review-skill` Java 指南。compiler=8 打开 `java8.md`。
3. 五轴：`code-review-and-quality`；安全敏感再开 `security-and-hardening` 与 plinth `124-java-secure-coding`
4. 命中回写 `review.md` 的 `P#`/`C#`，不要只留外挂严重度标签
