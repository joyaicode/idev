# idev 操作员速查（命令与预算）

**权威关系：** 本页是操作手册。路由以 `SKILL.md` 决策树为准；认票与 H1–H6 以 [invoke.md](invoke.md) 为准；grilling 触发细则在本页 §7.2；术语见 [glossary.md](glossary.md)；入口须知见 [agent-brief.md](agent-brief.md)。

目的：降低认知负荷。先拿命令和打开预算，规则全文不在这里复制。  
idev 适用**所有端到端交付产品**。产线做交付时先走内核；idev 识别产线特性，需要保存时写入该工程 `.idev/`，后续会话再读。人机共驾，非无人值守自动 seal。  
长段：[guide.md](guide.md) · [s1-vs-s8-playbook.md](s1-vs-s8-playbook.md) · [deep-read.md](deep-read.md) · [lite-change-pitfalls.md](lite-change-pitfalls.md) · [scope.md](../conventions/scope.md)

## 0. 真源（只认这一套）

| 角色 | 路径 |
|------|------|
| idev 真源（实目录） | `~/.cursor/skills/idev/` |
| 产线文档技能 | `~/.cursor/skills/idev/docs/SKILL.md` |
| grilling 真源（实目录） | `~/.cursor/skills/grilling/` |
| 文档目录技能 | `~/.cursor/skills/setup-agents-docs/`（可软链到它自己的真源） |
| 软引用 | `~/.agents` / `~/.joycode` 的同名 `skills/*` → 对应技能 |

改 idev / grilling 只改各自真源。产线文档的目录正文改 `setup-agents-docs`，idev 只改 `docs/SKILL.md` 里怎么接进交付。自愈：`scripts/link-idev-aliases.sh`、`scripts/link-companion-skills.sh`。

## 0.5 路由（不复制决策树）

以 `SKILL.md` 决策树为准，含「配方命中」。最常用三行（冲突时以决策树为准）：

| 输入 | 走 |
|------|----|
| 小改 / 轻量 / 不改 goal 的已有票 | **S8** `lite-change`（必须绑票） |
| 原话命中配方别名 | **S8**，最长别名优先于只含 stage 动词的 S2/S3 |
| 综合评审 skill / 导体 | **S4**；产品仓代码审查走 S8 `code-review` |

产线快捷配方：S8，配方在产品仓 `.idev/workflows/`，执行说明看 `session-context --workflow <id>` 的 `OPEN`。导体复盘：S8 `self-evolve-review`。  
说不清先看 `deliver.yaml` 的 `stage`。逐步剧本：[s1-vs-s8-playbook.md](s1-vs-s8-playbook.md)。

## 0.6 S8 前置探针

开跑任一 S8 配方前：

```bash
bash ~/.cursor/skills/idev/scripts/s8-preflight.sh <feature> <workflow_id> [--product <点名的产品>]
```

缺 `<票目录>/deliver.yaml`（配方需要时）、路径不可读、`patrol-replay` 缺巡检包 → 立刻 **BLOCKED** 并列缺项；不准编造 seal / 覆盖率结论。`<票目录>` 只认 `doc_home.py --key task`。

可选编译探针：`IDEV_PREFLIGHT_COMPILE=1`。模块列表由当前产品给出，核心不写默认模块名。

## 2. 打开预算（硬）

- **每轮只开一个执行模块**（deliver / verify / ops / 当前 workflow step）。
- 场景以 `SKILL.md` 决策树为准。认票与 H1–H6 打开 [invoke.md](invoke.md)。
- **不要**每轮打开：`lifecycle.md` / `trace.md` / `cohesion.md`。
- **不要**一次加载 deliver+verify+ops。
- S8：禁止把多步配方展开成「全模块灌进上下文」。

## 3. 轻量模式（小改动）

同时满足：已有票且 `stage` 在 `code` / `test`（或人说小改）；**不**改 goal / baseline / 架构；改动面已 `include` 或人指定。  
走 S8 **`lite-change`**（定界 → 编码 → selftest → 实现审核）。禁止改密封正文、跳阶段、自动 `sealed`/`accepted`、不问就 promote。  
踩坑：[lite-change-pitfalls.md](lite-change-pitfalls.md)。

## 3.5 自测、实现审核、提测、结果、巡检

| 格 | 是什么 | 谁触发 | 产物 |
|----|--------|--------|------|
| **selftest** | 开发自测：`plan.mode=selftest`，证明实现不漂基线 | 架构通过后直接起草并跑，计划不单独请签 | `verify/plan.yaml` + 跑证；`stage` 仍在 `code` |
| **实现审核** | 自测完成后看用例、diff、跑证 | 确认用语写入 `semantic_gate.code`，stage 改为 `test` | 不另问要不要提测 |
| **test** | 提测：`plan.mode=test`，维表六族齐（缺则 UNPROVEN 明示） | 实现审核通过后，或 S8 `test-pack` | `check-feature <f> test` |
| **aligned** | 人接受提测结果与残留 UNPROVEN 风险 | 测试结果那一次确认 | `deliver.aligned=true` → `stage=done` |
| **promote** | 把**当前** accepted+已跑 plan 快照成巡检包 | 人说提升 / 巡检包 / promote / 「继续」（done 后） | `doc_home.py --key patrol` |

钉死：promote 吃的是快照那份 plan（可以是 selftest 或 test）。aligned 是人签，promote 是另一刀（H2，全文见 invoke）。

## 3.6 HITL 与自进化

闸门在**不可逆之前**：seal / aligned / promote / 生产写。请签 = `将代写` + 证明上下文。档位：[hitl-risk-tiers.md](hitl-risk-tiers.md)。

| 动作 | 怎么走 |
|------|--------|
| 复盘挖信号 | S8 `self-evolve-review` 或 `bash ~/.cursor/skills/idev/scripts/evolve-review.sh` |
| 归档超龄提案 | `bash ~/.cursor/skills/idev/scripts/evolve-curator.sh`（落地归档加 `--apply`） |
| 清理执行残留 | `bash ~/.cursor/skills/idev/scripts/execution-clean.sh`（删除加 `--apply`）。`--compact` 在引用满 2 次或满 3 代时先写入 `.idev/memory.md` 再删热集合以外的文件。不碰 `docs/task`、打开的提案和 `memory.md` |
| nudge | 修缺口 / inbox 同类 tag≥2 / HARD>0 / 人要沉淀 → **一句话**问要不要写提案 |

细节：[self-evolution.md](self-evolution.md)。禁止未确认改 SKILL、分数门禁、未经摘要就硬删提案。

## 4. 非门禁不停（H1–H6）

全文只在 [invoke.md](invoke.md)。无当前停问点不请签，不擅自 promote，不为观测再停。`继续` ≠ 确认用语。

签字前：`bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> <stage>`

## 5. 每轮观测（含运行路径）

```bash
bash ~/.cursor/skills/idev/scripts/trace.sh append
bash ~/.cursor/skills/idev/scripts/path-view.sh
```

必填：`route.scenario`（缺省当 S1）、`invoke.trigger` / `matched`、真实 `calls[]` / `opened[]`。不准伪造调用。写完后在对话里给出一行运行路径。不为观测另停（H5）。

## 6. 命令

```bash
bash ~/.cursor/skills/idev/scripts/healthcheck.sh
bash ~/.cursor/skills/idev/scripts/audit-traces.sh 50
bash ~/.cursor/skills/idev/scripts/refs-check.sh
bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> <stage>
bash ~/.cursor/skills/idev/scripts/promote.sh <feature>
```

healthcheck：真源实目录、软链、配方、最近 50 条审计、outbound、grilling。导体验收看 `state/ledger.yaml`，不走产品仓票。审计怎么读：[deep-read.md](deep-read.md)。

## 7. 长规则

### 7.2 边界未订死必须自动唤起 grilling（触发细则全文）

下列任一成立时，**本轮立刻**打开并执行 `~/.cursor/skills/grilling/SKILL.md`（缺则先 `scripts/link-companion-skills.sh`），不准用「自己拷问几句」顶替，不准跳过直接请签/代写：

- S1 / `req-review`：需求分析、正确性/合理性/边界/细节未订死；`grill.md` 的 frontier 不是 `empty`；`objections` 或 `review_questions` 非空。本轮能问的一次问完
- 任意阶段出现 `open_questions` / `baseline-conflict` / 目标或边界含糊 / 人说「不确定」「再想想」「帮我定一下」
- 即将请签前，仍有未回答分叉或未清空异议
- 架构方案已经交出，人 Review 时仍有分叉；`code` 发现像基线写错（先问清冲突，禁止默许改 goal）

frontier 未空之前禁止写 `sealed`。答问不是签字。共享理解写在需求通过那一次确认里。架构没有分叉就不要先拷问再给方案。

### 7.3 认票

五步全文只在 [invoke.md](invoke.md)「认票」。本页不复述。

### 7.4 S8 小改必绑票

小改先认票；无票不裸改。走 S8 `lite-change`，第一步 `bash ~/.cursor/skills/idev/scripts/s8-preflight.sh <feature> lite-change`。
