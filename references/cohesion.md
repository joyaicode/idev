# 内聚：五个模块，禁止 skill 成灾

| 模块 | 只许拥有 | 禁止塞进来 |
|------|----------|------------|
| conventions | **核心**类（evidence / coding）+ 当前产品的叠加页 | Confirm 表、把试点特例写成核心、阶段机、runner |
| docs | 产线文档落点：怎么打开 setup-agents-docs（目录）与 grilling（问句），`doc_home.py` 解析 | 自定第二套目录、改写那两份技能的正文、阶段机 |
| deliver | 阶段机、密封基线、专家拒过、回退指针 | runner、巡检包、接入 Confirm、集群预案 |
| verify | plan / run / promote / clean、维度与 runner 表 | 拷问密封、分类 handoff、改 goal |
| ops | 现场分类、handoff、origin 指针 | 第二套断言、交出口正文、拆解 slices |
| 入口 traces | 路由 / 技能调起 / 委派 / 模型 / 组件跳 / 拒过 / 停问的可观测记录 | 分数、签字、第二套 eval |
| workflows | 快捷指令配方登记表与 run 契约 | 新模块、第二套阶段机、跳过签字 |
| agents | 执行者定义 + `kind → agent` 登记表 | **顶层 `name:`**、签字、trace、第二套路由 |

加能力 = 改**已有模块**的登记表（schema / experts / classify / plan-schema / workflow-schema / kind_agents）。不再加模块。  
**禁止**再开第二个顶层 Skill。入口只许 `idev`；各模块头写 `module:` 与 `parent: idev`，不写 `name:`。产品旧名留在该 pack 的 README，不要写回核心入口。  
不兼容才在本目录加 ADR 副本并升该模块 `schema_version`。

## agents 不是第二个 Skill

`agents/*.md` 是**执行者定义**，不是模块、也不是 skill：

- 它们的 `name:` 是 **subagent 名**（`idev-coder` 等），由 Claude Code / Cursor 的 agent 机制读，
  **不是** skill 名——两套机制不同命名空间，`/idev` 仍然唯一。
- 它们不持签字权（`workflow_spec.is_human()` 按词表拒绝 agent / 模型 / 角色名，存在 `people.yaml` 时还须在白名单里）、
  不写 trace、不做路由。换的只是「这一步由谁执行」。
- 扩展方式和别的模块一样：改 `scripts/lib/kind_agents.py` 的 `KIND_AGENTS` 一行 +
  `references/agents.md` 散文一行，两者不一致则 `agents-check.py` 失败。

所以「禁止第二个顶层 Skill」原样成立：**skill 只有 `/idev` 一个**（导体，注入主会话，持签字权），
agent 是它委派的执行者。职责分离见 [agents.md](agents.md)。
