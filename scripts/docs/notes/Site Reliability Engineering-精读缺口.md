# 《Site Reliability Engineering》精读缺口报告

> 源文本：`/tmp/idev-books/SiteReliabilityEngineering-全文.txt`（Google SRE Book 官方在线版全文合并文本，1,217,116 字符 / 15,651 行；49 个官方页面，001 Foreword 至 049 Table of Contents，已按目录顺序合并）。本报告在 `50357a7e4deb309ec3f4fd40d64f7129d0ad1040` 的干净检出中完成，严格对照 `conventions/canon.md`（T1–T14 / A1–A8 / F1–F7）与 `conventions/coding-tables.md`（P1–P19 / C1–C40 / R1–R7）裁定真缺口。
>
> 边界：编号真源仍只认 `canon.md` 的 T/A/F 与 `coding-tables.md` 的 P/C/R；本书章节号、Google 内部系统名和事故案例只作溯源，不建第二套编号。本报告只落“真缺口”，不摘抄书籍目录，也不改任何规范文件。

## 一、精读范围

全书 49 个官方页面全部读完，覆盖前言、序言、五大部分、34 章、附录 A–F、参考文献与总目录：

- 页 001–002，L1–L470：Foreword、Preface。
- 页 003–005，L471–L1187：Part I，Chapter 1 Introduction、Chapter 2 The Production Environment at Google, from the Viewpoint of an SRE。
- 页 006–013，L1188–L3530：Part II，Chapter 3 Embracing Risk、Chapter 4 Service Level Objectives、Chapter 5 Eliminating Toil、Chapter 6 Monitoring Distributed Systems、Chapter 7 The Evolution of Automation at Google、Chapter 8 Release Engineering、Chapter 9 Simplicity。
- 页 014–032，L3531–L10990：Part III，Chapter 10 Practical Alerting、Chapter 11 Being On-Call、Chapter 12 Effective Troubleshooting、Chapter 13 Emergency Response、Chapter 14 Managing Incidents、Chapter 15 Postmortem Culture、Chapter 16 Tracking Outages、Chapter 17 Testing for Reliability、Chapter 18 Software Engineering in SRE、Chapter 19 Load Balancing at the Frontend、Chapter 20 Load Balancing in the Datacenter、Chapter 21 Handling Overload、Chapter 22 Addressing Cascading Failures、Chapter 23 Managing Critical State: Distributed Consensus for Reliability、Chapter 24 Distributed Periodic Scheduling with Cron、Chapter 25 Data Processing Pipelines、Chapter 26 Data Integrity: What You Read Is What You Wrote、Chapter 27 Reliable Product Launches at Scale。
- 页 033–038，L10991–L13024：Part IV，Chapter 28 Accelerating SREs to On-Call and Beyond、Chapter 29 Dealing with Interrupts、Chapter 30 Embedding an SRE to Recover from Operational Overload、Chapter 31 Communication and Collaboration in SRE、Chapter 32 The Evolving SRE Engagement Model。
- 页 039–041，L13025–L13646：Part V，Chapter 33 Lessons Learned from Other Industries、Chapter 34 Conclusion。
- 页 042–047，L13647–L15023：Appendix A Availability Table、Appendix B A Collection of Best Practices for Production Services、Appendix C Example Incident State Document、Appendix D Example Postmortem、Appendix E Launch Coordination Checklist、Appendix F Example Production Meeting Minutes。
- 页 048–049，L15024–L15651：Bibliography、Table of Contents。

重点复核段落：错误预算与 SLO 定义 L776–L790、L1778–L1935；四黄金信号与告警噪声 L2385–L2505；自动重试、截止时间与取消传播 L8210–L8299；持久数据备份、恢复与端到端恢复验证 L9947–L10315；生产服务最佳实践 L14030–L14100。

## 二、对照结论

### 1. 主体原则已被现有真源承载

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| 简单、稳定与敏捷的取舍、删除偶然复杂度与死代码 | T1、T3、C6 | 承载 |
| 依赖方向、跨上下文显式契约、服务边界 | T4、T13、A2 | 承载 |
| 统一语言与命名 | T5 | 承载 |
| 护栏先行、小步可逆、测试金字塔与触及面测试 | T6、R1、C26、C28、A5、A6 | 承载 |
| 发布分批、灰度、回滚、监控、关联标识 | T11、A6 | 承载 |
| 快速失败、降级语义、错误分类 | T8、T11、C7 | 承载 |
| 数据真相之源、派生副本、失败语义、一致性、Schema 演进 | T10、A4 | 承载 |
| 外部调用超时、连接池、熔断、慢响应快速失败 | T10、T11 | 承载 |
| 自动化、发布工程、可重复构建、权衡记录 | T1、T6、T12 | 承载 |
| 分布式共识、周期调度、流水线的一致性与失败语义 | T10、T12 | 承载（算法细节不落） |
| 事故管理、事后复盘、On-call、团队管理 | 过程/组织经验；转化为测试时由 T6/A6 承载 | 不另立编码条 |
| Google 基础设施（Borg、Chubby、Bigtable、Colossus 等）与负载均衡算法 | T10、T11 只承载通用风险，系统细节不落 | 不抄入真源 |

`coding-tables.md` 最近似的是 C7（失败不得吞掉）、C19（资源成对释放）、C26/C28（测试聚焦与金字塔）、R1/R6（护栏与先理解再动），它们能兜住普通代码级失败与测试问题，但覆盖不了 SRE 书的四条系统性缺口。

## 三、真缺口

### 1. 用户视角 SLO / 错误预算与四黄金信号未成为上线出门项

**书中依据**：L1778–L1802 要求先定义 SLI/SLO，并从用户关心的行为反推指标；L1886–L1908 要求写清测量窗口、目标与错误预算，并把预算耗尽作为发布决策输入；L2465–L2489 给出延迟、流量、错误、饱和四黄金信号；L14035–L14050 再次强调从用户视角定义 SLO、错误预算与冻结变更策略。

**idev 现状**：T11 已要求“指标、结构化日志、告警条件”，A6 已要求“指标、日志、回滚、降级、灰度”，但都没有要求：

- 用户可见路径定义 SLI/SLO 与测量窗口；
- 目标值和错误预算；
- 错误预算耗尽时的动作（冻结非紧急变更 / 只放安全修复）；
- 延迟、流量、错误、饱和四类信号的最小观测面；
- 分页告警必须对应用户症状且有明确动作，噪声告警降级为工单或日志。

这不是 Google 特有流程，而是所有用户可见在线路径的通用可运维性契约。当前 T11 只要求“有指标”，无法阻止实现者交出一堆内部技术指标却没有任何用户视角目标。

**最小落点**：增补 `T11` DO，并同步 `A6` 护栏项；不新增编号。

### 2. 自动重试、截止时间与取消传播缺少跨层纪律

**书中依据**：L8216–L8228 要求随机指数退避、限制每请求重试、全局重试预算、避免多层重试相乘、区分可重试与不可重试错误、过载时返回“不要重试”专用状态；L8232–L8278 要求传播 RPC deadline，在处理前检查剩余时间，并把取消传播到整棵调用树以停止注定失败的工作；L14089–L14095 明确“Every client that makes an RPC must implement exponential backoff (with jitter)”。

**idev 现状**：T10 与 §4 已覆盖幂等、限次数与退避、禁止无界重试；T11 已覆盖超时、连接池、熔断与快速失败。缺口在于：

- 退避必须是随机指数并带 jitter，避免同步重试波；
- 只在紧邻上游层重试，避免多层重试相乘；
- 区分可重试 / 不可重试 / 过载专用错误，过载时抑制重试；
- 传播 deadline，进入下一阶段前检查剩余时间；
- 整体注定失败时传播 cancellation，停止下游无谓工作。

当前规则只阻止“无界重试”，不能阻止每层各重试三次造成 4^N 放大，也不能阻止客户端已放弃后服务端继续消耗资源。

**最小落点**：增补 `T11` DO，并同步 §4“重试一下”行；不新增编号。

### 3. 持久数据的恢复目标与端到端恢复验证缺失

**书中依据**：L9947–L9963 明确“备份不是目的，恢复才是”，并要求写清可接受数据丢失窗口与恢复时长；L10007–L10017 要求为多种失败模式定义数据可用性 SLO 并实践恢复；L10114–L10148 要求由恢复场景驱动备份策略、分层恢复与可接受丢失；L10247–L10280 要求持续测试恢复过程，且只有完整端到端恢复测试才能证明可恢复。

**idev 现状**：T10 覆盖真相之源、副本、失败语义、一致性、Schema 演进；T11 覆盖回滚；A4 覆盖数据模型。但没有任何编号要求：

- 持久数据定义恢复目标：可接受丢失窗口与恢复时长；
- 区分备份与归档，副本不等于恢复；
- 由恢复场景驱动备份策略；
- 关键数据用软删除 / 带外校验等纵深防御；
- 用端到端恢复演练证明“最近状态可恢复”。

这不是数据库实现细节，而是数据系统出门前的可恢复性契约。当前 T10 能阻止双写与一致性漂移，但不能阻止“有副本、无恢复路径、无恢复演练”的假可用。

**最小落点**：增补 `T10` DO，并同步 `A4` 架构必答；不新增编号。

### 4. 交付产物缺少可复现 / 密封构建契约

**书中依据**：L3170 要求可靠服务依赖可复现、自动化的发布过程，发布不能是“唯一雪花”；L3196 要求同一源码版本在不同构建机上得到相同产物，构建不依赖构建机本地库或外部服务，只依赖已知版本的构建工具与依赖；L3226 要求产物能关联构建日期、源码版本与构建标识；L3280–L3286 要求配置入库并接受评审，配置包与二进制同版本发布，避免配置漂移。

**idev 现状**：T11 已覆盖发布、回滚、灰度与观测；T12 覆盖决策记录；`idev-ops` 有制品身份排查，但通用架构真源没有要求同一源码 / 配置 / 工具版本产出相同产物，也没有把“配置与产物同版本”作为出门契约。缺这一步时，回滚、排障和“重新构建一个一样的包”都建立在不成立的假设上。

**最小落点**：增补 `T11` DO 与 TRIGGER，并同步 `A6` 护栏项；不新增编号。

## 四、重点候选裁定（防后人重复发现）

1. **SLO 数值与“几个九”不落。** 目标值是产品决策，随业务变化；只落“必须定义 SLI/SLO、错误预算与四黄金信号”的契约。
2. **尾延迟分位数不单独立条。** 并入 SLI/SLO 缺口；T9 已要求测量边界，T11 增补用户视角观测后可覆盖。
3. **Google 基础设施与专用系统不落。** Borg、Chubby、Bigtable、Colossus、全球负载均衡等只作理解材料。
4. **负载均衡算法不落。** DNS、数据中心、客户端节流等算法是环境特定实现；通用风险已由 T10/T11 的资源隔离、过载与降级承载。
5. **分布式共识算法细节不落。** Paxos/Zab 等属于实现细节；T10 已要求一致性权衡，不应鼓励自研协调系统。
6. **50% 运维上限、On-call 人数、事故角色、复盘仪式不落。** 组织流程，不是通用编码规约。
7. **N+2 容量、发布检查单、事故文档模板不落。** 属运营模板与公司策略，按场景落到产品仓契约即可。
8. **自动化框架与发布流水线细节不落。** 通用原则已由 T1/T6/T12 承载，具体工具链随基础设施变化。

## 五、不建议落的内容

- 34 章逐章目录与 Google 内部案例：重复书籍内容，不进第二套知识库。
- On-call、招聘、团队管理、沟通协作章节：组织实践，不进编码真源。
- Google 专用监控、调度、发布、存储系统实现：环境绑定，不可通用执行。
- 具体告警系统、容量规划、负载均衡、共识算法参数：随系统与业务变化，不进规约。
- 示例事故文档、复盘模板、生产会议纪要：只作理解材料，不抄入真源。
