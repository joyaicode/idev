# 《Building Secure and Reliable Systems: Best Practices for Advancing Software Engineering》精读缺口报告

> 源文本：`/tmp/idev-books/BuildingSecureAndReliableSystems-全文.txt`（38 个官方来源页面，`002.html`–`039.html` 按顺序合并；1,228,768 字节，12,485 行）。本报告不访问网络，只读本地全文。
>
> 对照真源：`conventions/canon.md`（T1–T14 / A1–A8 / F1–F7）与 `conventions/coding-tables.md`（P1–P19 / C1–C40 / R1–R7）。
>
> 边界：本报告只裁定「已被承载」与「真缺口」，不抄目录、不建第二套知识库。书中章节号、Google 专有机制和案例只作溯源。

## 一、精读范围

38/38 个官方页面全部读完，无缺页：

| 区间 | 页面 | 覆盖内容 |
|---|---|---|
| 前置材料 | `002`–`009` | Praise、空白/版权前置页、Dedication、书名页、两篇 Foreword、Preface |
| Part I | `010`–`012` | Part I 导言、第 1 章 The Intersection of Security and Reliability、第 2 章 Understanding Adversaries |
| Part II | `013`–`021`、`022` | Part II 导言、第 3–10 章：Safe Proxies、Design Tradeoffs、Least Privilege、Understandability、Changing Landscape、Resilience、Recovery、DoS；`022` 为 Part III 导言 |
| Part III | `023`–`027` | 第 11–15 章：Publicly Trusted CA、Writing Code、Testing Code、Deploying Code、Investigating Systems |
| Part IV | `028`–`031` | Part IV 导言、第 16–18 章：Disaster Planning、Crisis Management、Recovery and Aftermath |
| Part V | `032`–`035` | Part V 导言、第 19–21 章：Chrome Security Team、Roles and Responsibilities、Culture of Security and Reliability |
| 结尾材料 | `036`–`039` | Conclusion、Appendix、Index、Editors |

正文主区间：前言与导言 L1–L4394；第 11–15 章 L4395–L6871；第 16–21 章 L6872–L9234；Conclusion / Appendix / Index / Editors L9235–L12485。索引只做结构核对，不参与缺口裁定。

## 二、对照结论

### 1. 主体原则已被真源承载

| 书中部分 | 主题 | 现有承载 |
|---|---|---|
| 第 1–2 章 | 安全/可靠性是设计期涌现属性、风险取舍、对手与内部人建模 | T1 T4 T6 T8 T10 T11 T12 · A1–A8 · F4–F6 |
| 第 3–5 章 | Safe Proxies、设计取舍、最小权限、跨信任域身份映射 | T4 T10 T11 T12 · A2 A3 A6 · C31 |
| 第 6–8 章 | 可理解性、框架化、变更适应、弹性与降级 | T1 T2 T3 T5 T6 T8 T10 T11 T12 · A1–A8 · C15 C22–C25 |
| 第 9–11 章 | 恢复、DoS、CA 案例 | T6 T10 T11 T12 · A3 A4 A6 · C25 C31 |
| 第 12–13 章 | 编码框架、强类型、静态/动态分析、测试 | T1 T3 T5 T6 T12 T14 · C2 C13 C18 C21 C25–C30 C37 · F5 · R1–R7 |
| 第 14–15 章 | 供应链、部署、调查与日志 | T11 T12 · A6 · C31 |
| 第 16–18 章 | 灾备、危机、恢复 | T6 T10 T11 T12 · A3 A4 A6 |
| 第 19–21 章 | Chrome 案例、角色、文化 | T1 T3 T6 T11 T12 · A1–A8 |
| 结尾材料 | 总结、附录、索引、编辑简介 | 结构与溯源，不新增工程规则 |

### 2. 跨章主题的承载判定

- 简单性、最小攻击面、统一语言：T1 / T2 / T3 / T5 / A1 / A7 与 C15、C22–C25 已承载。
- 最小权限、跨信任域主体映射、凭证隔离：T4 / A2 / C31 已承载。
- 降级、回滚、灰度、指标与日志：T11 / A6 / F4–F6 已承载。
- 数据真相之源、失败语义、恢复裁决：T10 / A4 已承载。
- 契约兼容与演进：T12 / T13 / A6 已承载。
- 测试金字塔、脆弱测试、过度 mock：C28–C30 / F5 / R1–R7 已承载。
- 组织、角色、演练、事件指挥、文化：属流程与组织层，不落编码表；其工程面已由 T6 / T10 / T11 / T12 / A3 / A4 / A6 承载。

## 三、真缺口（4 条）

### 1. 高风险特权操作缺少独立第二方批准与受控 breakglass

**书中依据**：L468 要求敏感操作由特定员工组合审查批准；L939–L1020 说明 Safe Proxies / Zero Touch Prod、MPA、审计与 breakglass；L1406、L1482、L1522、L1602–L1608 把 breakglass 定义为紧急例外并要求限制、告警与审计；L6294–L6298 要求部署 breakglass 罕见、可审计并立即告警。

**现有承载**：T4 已有最小授权、跨信任域身份映射、提权/降权与审计点；T11 已有日志、告警与回滚；C31 已有凭证与敏感信息。没有任何条目要求「高风险 / 破坏性特权操作由独立第二方批准」，也没有把 breakglass 限定为受控、可审计、非常规通道。

**最小落点**：`canon.md` T4 `DO` 增补一句，并在 §2 既有跨信任域特权信号上同步 MPA / breakglass。

### 2. 架构出门缺少爆炸半径 / 失效域 / 纵深防御

**书中依据**：L458–L464 要求 distinct failure domains、defense in depth、限制 blast radius；L2347、L2654、L2993–L3639 反复要求分层防御、独立失效域、受控降级与持续验证；L8443–L8471 以 Chrome 案例说明纵深防御与沙箱的实际效果。

**现有承载**：T10 管数据失败语义，T11 管降级 / 回滚 / 灰度，A6 管护栏与观测。三者都没有要求架构方案显式输出「失效域、爆炸半径、纵深防御」，执行者容易只写功能拓扑而漏掉故障传播边界。

**最小落点**：`canon.md` A6 必答项增补「失效域 / 爆炸半径 / 纵深防御」，并同步对应 T10/T11。

### 3. 发布链路缺少配置即代码、制品来源、可验证构建与上线后验证

**书中依据**：L5757 说明部署必须证明运行的是假设中的代码；L5885、L5903–L5905 要求配置按代码版本化、评审、测试；L5981–L6075 要求 binary provenance 与 provenance-based deployment policies；L6112–L6188 定义 verifiable builds；L6242–L6258 要求 post-deployment verification；L6294–L6298、L6320 总结 breakglass、configuration-as-code、binary provenance 与 verifiable builds。

**现有承载**：T11 已有指标、日志、告警、回滚、降级、灰度；T12 已有权衡记录。但没有要求发布链路说明配置评审、制品来源、部署校验与上线后复核，供应链完整性仍是空档。

**最小落点**：`canon.md` T11 `DO` 增补发布链路完整性一句，`RECORD` 增加 `制品来源=…`，并把 §2 上线信号扩展为包含制品来源说明。

### 4. 不可信输入解析缺少内存安全默认与持续 fuzz / sanitizer 证据（映射到 T4 / T6）

**书中依据**：L4457–L4511 的 CA 案例把不可信输入隔离到独立信任区，选择 Go 处理 CSR，并对 C++ 子系统做输入校验、sanitizer 与定向 fuzz；L4900–L4904 要求 memory-safe languages；L4998–L5035 说明 Valgrind / Google Sanitizers；L5254 起说明 fuzz testing 与 sanitizer 的互补关系；L8423–L8425 说明 Chrome 持续 fuzz 基建。

**现有承载**：C25 管领域类型，C31 管密钥与加密，C37 只管整数溢出，C18 管跨进程内存布局。没有任何条目要求「不可信输入 / 协议 / 文件格式解析优先内存安全或隔离，并为高风险解析面提供持续 fuzz / sanitizer 证据」。

**最小落点**：本轮明确不新增 C 编号，改为映射到 `canon.md` 既有 T4 / T6：T4 管不可信输入的信任边界、内存安全与隔离，T6 管高风险解析面的持续 fuzz / sanitizer 证据。

## 四、重点候选裁定（不建议落，防止重复发现）

- 逐章目录、索引、编辑简介、案例事实：只作溯源，不进真源。
- 组织角色、事件指挥、演练、文化、评审礼仪：流程与组织层，不落编码表。
- Google 专有机制（Borg、GKE、Tricorder、ClusterFuzz、Safe Proxies）：工具与平台事实，不进通用规则。
- 通用安全/可靠性原则（涌现属性、风险、简单性、演进、测试、恢复）：已由 T/A/F 与 P/C/R 既有编号承载。
- 语言/框架选型的一般建议：除「不可信解析的内存安全默认」外，不另立通用选型条目；本轮该默认映射到既有 T4 / T6，不新增 C 编号。
- CA 的具体架构、Chrome 的发布节奏、灾备演练细节：领域案例，不复制为规约。
- 日志脱敏、凭证隔离、加密实现：C31 已承载。
- 并发与死锁：T10、C34、C35、C37、C39 已承载。
