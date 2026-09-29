# 内聚：五个模块，禁止 skill 成灾

| 模块 | 只许拥有 | 禁止塞进来 |
|------|----------|------------|
| conventions | **核心**类（evidence / coding）+ 当前产品的叠加页 | Confirm 表、把试点特例写成核心、阶段机、runner |
| docs | 产线文档落点：怎么打开 setup-agents-docs（目录）与 grilling（问句），`doc_home.py` 解析 | 自定第二套目录、改写那两份技能的正文、阶段机 |
| deliver | 阶段机、密封基线、专家拒过、回退指针 | runner、巡检包、接入 Confirm、集群预案 |
| verify | plan / run / promote / clean、维度与 runner 表 | 拷问密封、分类 handoff、改 goal |
| ops | 现场分类、handoff、origin 指针 | 第二套断言、交出口正文、拆解 slices |
| 入口 traces | 路由 / 拒过 / 停问的可观测记录 | 分数、签字、第二套 eval |
| workflows | 快捷指令配方登记表与 run 契约 | 新模块、第二套阶段机、跳过签字 |

加能力 = 改**已有模块**的登记表（schema / experts / classify / plan-schema / workflow-schema）。不再加模块。  
**禁止**再开第二个顶层 Skill。入口只许 `idev`；各模块头写 `module:` 与 `parent: idev`，不写 `name:`。产品旧名留在该 pack 的 README，不要写回核心入口。  
不兼容才在本目录加 ADR 副本并升该模块 `schema_version`。
