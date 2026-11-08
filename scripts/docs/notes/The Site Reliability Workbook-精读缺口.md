# 《The Site Reliability Workbook》精读缺口报告

> 源文本：`/tmp/idev-books/TheSiteReliabilityWorkbook-全文.txt`（Google 官方在线版 35 个页面按目录顺序合并，16,288 行 / 1,072,796 字节）。单页 HTML 备查路径：`/tmp/idev-books/pages-final/TheSiteReliabilityWorkbook/`。本报告先在 `50357a7` 基线 worktree 中完成，再对照当前主线 `conventions/canon.md` 与 `conventions/coding-tables.md` 复核增量，不建第二套编号。

## 一、精读范围

35 个官方页面全部读完，覆盖前言、正文、附录、索引、编辑者介绍、版权页与总目录：

- 页 001–005：Foreword I、Foreword II、Preface、How SRE Relates to DevOps、Part I. Foundations。
- 页 006–011：Implementing SLOs、SLO Engineering Case Studies、Monitoring、Alerting on SLOs、Eliminating Toil、Simplicity。
- 页 012–021：Part II. Practices、On-Call、Incident Response、Postmortem Culture、Managing Load、Non-Abstract Large System Design、Data Processing Pipelines、Configuration Design and Best Practices、Configuration Specifics、Canarying Releases。
- 页 022–028：Part III. Processes、Identifying and Recovering from Overload、SRE Engagement Model、SRE: Reaching Beyond Your Walls、SRE Team Lifecycles、Organizational Change Management in SRE、Conclusion。
- 页 029–031：Example SLO Document、Example Error Budget Policy、Results of Postmortem Analysis。
- 页 032–035：Index、About the Editors、Colophon、Table of Contents。

索引页已逐项结构扫描，只含词条与章节锚点，不新增正文论点；页 018 与页 031 的表格另按 HTML 单元格补齐后复核。

## 二、对照结论

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
| 自动化、发布工程、可重复权衡记录 | T1、T6、T12 | 承载 |
| 分布式共识、周期调度、流水线的一致性与失败语义 | T10、T12 | 承载（算法细节不落） |
| 事故管理、事后复盘、On-call、团队管理 | 过程/组织经验；转化为测试时由 T6/A6 承载 | 不另立编码条 |
| Google 基础设施（Borg、Chubby、Bigtable、Colossus 等）与负载均衡算法 | T10、T11 只承载通用风险，系统细节不落 | 不抄入真源 |
| SLO / SLI / 错误预算 / 四黄金信号 / 可执行告警 | 基线缺失；当前主线已由 T11、A6 承载 | 基线真缺口 1，非当前增量 |
| 自动重试、退避、deadline、cancellation、过载专用错误 | 基线缺失；当前主线已由 T10、T11、§4「重试一下」承载 | 基线真缺口 2，非当前增量 |
| NALSD 的容量估算、失败域、组件隔离、优雅降级 | T9、T10、T12 部分承载；A6 原未要求容量与失败域 | 当前真缺口 3 |
| 负载均衡、自动扩缩容、丢弃负载、限流的组合反馈 | T10、T11 部分承载；缺少多控制器组合契约 | 当前真缺口 4 |

`coding-tables.md` 最近似的是 C7（失败不得吞掉）、C19（资源成对释放）、C26/C28（测试聚焦与金字塔）、R1/R6（护栏与先理解再动），它们能兜住普通代码级失败与测试问题，但覆盖不了本书的系统性缺口。

## 三、真缺口（基线 4 条；当前主线增量 2 条）

### 1. 用户视角 SLO / 错误预算与四黄金信号缺失

- **书中出处**：页 006–009，尤其 L1,600–L2,100、L2,600–L3,100。
- **关键论据**：SLO 必须从用户可感知症状定义 SLI，写明测量窗口、目标值与错误预算；监控需覆盖延迟、流量、错误、饱和四类信号；分页告警必须对应用户症状且有明确动作，低价值噪声转工单或日志。
- **当前主线裁定**：已由《Site Reliability Engineering》同轮落地到 T11 DO 与 A6 必答项；本书不重复改写。
- **落地状态**：已承载于 T11、A6。

### 2. 自动重试、deadline 与 cancellation 缺少系统性契约

- **书中出处**：页 016《Managing Load》L7,000–L7,062。
- **关键论据**：同步客户端重试会形成雷群；重试必须区分可重试 / 不可重试 / 过载专用错误，使用随机指数退避加 jitter，并限制重试预算；调用链必须传播 deadline / cancellation，整体注定失败时停止下游无谓工作。
- **当前主线裁定**：已由《Site Reliability Engineering》同轮落地到 T10/T11 与 §4「重试一下」；本书不重复改写。
- **落地状态**：已承载于 T10、T11。

### 3. 架构出门缺少容量与失败域论证

- **书中出处**：页 017《Introducing Non-Abstract Large System Design》L7,185、L7,313–L7,335、L7,449–L7,525。
- **关键论据**：NALSD 要求从白板结构出发，估算计算、存储、IO、网络等关键资源；逐轮评估单点失败、共享失败域和数据中心级故障，并把隔离、复制、降级 / failover 演化成具体资源方案。
- **与现有条目的边界**：T9 管优化测量，T10 管数据 / 资源权衡，T12 管被拒方案；A6 是架构出门清单，缺这一项时架构可以只写功能与观测，而不回答目标负载下资源是否够、失败域是否被枚举、降级后还剩什么能力。
- **落地状态**：已落地到 A6「容量与失败域」。

### 4. 自动资源控制器的组合反馈缺少契约

- **书中出处**：页 016《Managing Load》L7,000–L7,043、L7,047–L7,062。
- **关键论据**：Dressy 案例中，负载均衡器把丢弃负载产生的 503 当成“每请求成本更低”，把更多流量导向已经过载的区域。负载均衡、自动扩缩容、丢弃负载、重试等控制器组合时，必须显式建模相互作用；控制指标不能把失败 / 被拒绝请求当低成本成功；要观测控制器交集和反馈环，并协调停止、人工接管、资源上下限与保留容量。
- **与现有条目的边界**：T10 已有单阈值迟滞、队列公平性、等待观测和幂等重试；T11 已有超时、熔断、降级、观测与回滚。缺口在“多个自动控制器共同作用”的系统性契约：每个控制器局部正确，仍可能因为指标语义和反馈环互相放大故障。
- **落地状态**：已落地到 T10 DO 与 §2 自动控制组合信号。

## 四、不建议落的（防后人重复发现）

1. **SLO 数值、错误预算政策模板、几个九**：产品 / 业务决策，T11 只落“必须定义与耗尽动作”。
2. **Prometheus、Google Cloud Load Balancing、Maglev、GCLB、Paxos 等实现细节**：环境与算法绑定；通用风险已由 T10/T11/A4/A6 承载。
3. **数据管道的两阶段 mutation、checkpointing、热点数据阻断**：是按数据契约选择的实现模式；通用要求已由 T10 的幂等 / 失败语义和 T11 的观测、降级承载。
4. **配置语言选型、Jsonnet、Kubernetes 集成、运行时沙箱细节**：T1/T6/T8/T11/T12/T13 已承载最小配置、显式默认、验证、版本、灰度与回滚原则。
5. **金丝雀样本量、时长、时段与统计模型**：随流量形态和业务风险变化；T11 已要求分批灰度、对照组与判定指标。
6. **On-call 轮值、事故角色、复盘模板、团队生命周期、组织变更管理**：组织流程，不是通用编码 / 架构真源。
7. **Google 案例中的具体容量数字、区域拓扑和事故时间线**：只作论证材料，不复制成第二套知识库。
