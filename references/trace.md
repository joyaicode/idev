# 执行与决策可观测

每轮 **路由之后、对用户说话之前** 必须留下决策，方便人看导体有没有走偏，也方便以后进化。  
不是验收、不是打分、不为观测另停一次。

## 两处输出（都要）

1. **对话**：贴 `## idev-trace` 短表（用下面的 `render`）。
2. **产品仓**：`<repo>/.idev/traces/<YYYYMMDD>-<NNN>.yaml`  
   这是使用 idev 的中间文件，不进 idev 内核，不准 `.scratch/`。
3. **导体自身会话**（当前目录就是 idev 内核、且没有 `IDEV_PRODUCT_REPO`）：才落 `~/.cursor/skills/idev/state/traces/`。

```bash
# 校验并落盘，同时打出短表
bash ~/.cursor/skills/idev/scripts/trace.sh append < trace.yaml

# 看最近一条 / 列表
bash ~/.cursor/skills/idev/scripts/trace.sh last
bash ~/.cursor/skills/idev/scripts/trace.sh list
```

契约示例：[trace.example.yaml](trace.example.yaml)。

## schema_version

| 版本 | 何时用 |
|------|--------|
| `1` | 旧痕迹只读兼容；**新写入禁止** |
| `2` | **当前必写**：在 v1 字段上增加 `invoke` / `thinking` / `calls` |

## 必写（v2）

| 字段 | 约束 |
|------|------|
| `schema_version` | `2` |
| `at` | ISO-8601 |
| `intent` | 本轮用户原话压缩成一句 |
| `route.module` | `conventions` \| `deliver` \| `verify` \| `ops` \| `handoff` |
| `route.scenario` | `S1`…`S8`（**必写**；缺省当 S1） |
| `route.why` | 为何选这个、不选其它（一句） |
| `invoke.trigger` | 本轮如何进入口：用户原话关键片段 / `@idev` / 旧名别名 / 隐式续作 |
| `invoke.matched` | 命中了哪条路由信号（表格行语义，一句） |
| `thinking.summary` | 路由前的思考压缩（2～4 句：信号 → 排除 → 选定） |

## 建议写（有就填；优化时越全越好）

| 字段 | 含义 |
|------|------|
| `feature` | 当前 slug；未知 `-`。周审计把产品仓的 `-` 记为未绑票；内核 `state/traces/` 是导体自己的会话，不建票，不计 |
| `route.convention_class` | `evidence` \| `coding` \| `java` \| `identity` \| `config` \| `frontend` \| `landing` \| `docs` \| `specials` |
| `route.stage` | 阶段机或 `verify-plan` |
| `route.risk_tier` | `P0` \| `P1` \| `P2` |
| `rejected[]` | 没走的模块 + 原因 |
| `decisions[]` | `kind` + `chose` + `why` |
| `invoke.alias` | 若用户用了该产品的旧名，记原名 |
| `invoke.skill_path` | 实际打开的入口路径，通常 `~/.cursor/skills/idev/SKILL.md` |
| `invoke.how` | 技能怎么被调起：`explicit`（`/idev` 或 `@idev`）· `alias`（配方别名或产品旧名）· `implicit`（没点名，描述命中）· `continuation`（同一票上的「继续」） |
| `invoke.skills[]` | 本轮真正加载的技能，按顺序：`name` + 可选 `path` / `why`。同伴技能（grilling、docs）也写在这里 |
| `thinking.signals[]` | 观察到的信号（各一句，如「有 deliver.yaml.stage=code」「用户说现象」） |
| `thinking.excluded[]` | 排除项 + 一句原因（可比 `rejected` 更细，含非模块选项） |
| `thinking.uncertainty` | 仍不确定什么；没有则空 |
| `thinking.steps[]` | 有序思考步骤：`n` + `do`（做了什么判断）+ `so`（因此怎样） |
| `calls[]` | 本轮已发生的调用：`kind` + `name` + 可选 `args` / `result` |
| `opened[]` | 本轮深读的规约/模块页或关键仓文件（短路径） |
| `extensions` | 本轮 `session-context.py` 打出的 `OPEN` 路径。产品仓 `.idev/traces/` 且该仓 `marker: idev` 时必须有这个字段，没有页就写 `extensions: []`；缺字段周审计记 HARD。内核 `state/traces/` 是导体自己的会话，不要求这个字段。有列表时每一项必须出现在 `opened` |
| `stop` | 等人的点；没有则空 |
| `next` | 下一手 |
| `check_feature` | `PASS` \| `FAIL` \| `skipped` |

`decisions[].kind` 只许：`route` \| `gate` \| `stop` \| `refuse` \| `handoff` \| `call` \| `open` \| `delegate` \| `model`。

`delegate` 的 `chose` 只许五个执行者名，或 `none`（导体自己做，与 `DELEGATE none` 同一个词）。`model` 的 `chose` 是模型名或 `inherit`。

`calls[].kind` 只许：`script` \| `module` \| `skill` \| `repo` \| `tool` \| `agent` \| `model`。

| kind | 例子 |
|------|------|
| `script` | `check-feature.sh`、`trace.sh`、`promote.sh` |
| `module` | `deliver/SKILL.md`、`verify/SKILL.md` |
| `skill` | 交出口 Skill 名，取当前产品 `.idev/handoff.yaml` |
| `repo` | `<票目录>/deliver.yaml`（`doc_home.py --key deliver`） |
| `tool` | 外部 runner / Playwright / gh，以及 ReAct 关节选中的已登记工具。`from` 写 `react:<step>`，`to` 写 `tool:<id>` |
| `agent` | 五个执行者之一。`target` 写 agent 名。不要记成 `module` |
| `model` | 这一跳调用的模型。`name` 是模型名或 `inherit` |

一条 call 上还可以写这些观察字段。都可选；写了就必须是完整的：

| 字段 | 含义 |
|------|------|
| `from` / `to` | 组件跳的两端，必须同时有。写法：`user` · `conductor` · `skill:<name>` · `agent:<name>` · `module:<name>` · `script:<name>` · `repo:<name>` |
| `model` | 这一跳用的模型，通常 `inherit` |
| `thinking` | 这一跳的思考，**一行**。过程放 `thinking.steps`，不要把整段推理贴进来 |
| `duration_s` | 秒，非负数字。没有计时就空着，不要填 0 充数 |
| `why` | 为什么有这一跳。ReAct 关节里这是 Thought |
| `result` | 这一跳的结果。ReAct 关节里这是 Observation。本轮 trace 写 `react: <循环文件>` 时，`append` 把文件里还没出现的跳抄进 `calls`，并把登记的命令抄进 `args` |
| `target` | `kind: agent` 时写 agent 名 |

### 四层观察写在哪

| 想看的 | 写在 | 路径视图 |
|--------|------|----------|
| 技能调起 | `invoke.how` + `invoke.skills[]`。这一下要出现在跳转里，再加一条 `kind: skill` 的 call（`from: user`，`to: skill:<name>`） | `skills` |
| agent 决策 | `decisions` 一条 `kind: delegate` 写为什么派。派了谁、哪一步、第几次、是不是复核，由 `append` 从留痕生成 `delegations`，不用手记 | `choices` 与 `delegated` |
| 模型与思考 | `decisions` 一条 `kind: model`，以及 `kind: model` 的 call。`thinking` 只留一行 | `choices` 与 `hops` 上的 `model=` / 「」 |
| 组件交互 | 每一跳的 `from` / `to`。ReAct 的 Thought 写 `why`，Observation 写 `result` | `hops` 一行，另有「追踪」逐跳 |

缺了这四层**不算失败**，周审计只计数、不报警。不准编造没发生的技能、委派或模型调用。

## 对话短表

落盘始终全量 v2。给人看的表：

| `route.scenario` | 对话输出 |
|------------------|----------|
| S2 / S3 / S5 / S8 | 只打 `trigger` / `route` / `stop` / `next`（S8 的 route 含 workflow id / step） |
| S1 / S4 / S6 / S7 或缺省 | 全表：另含 intent、feature、matched、why、rejected、thinking、calls、opened、conventions、decisions、check |

`render` 全表会多展示：`trigger`、`matched`、`skills`、`thinking`、`calls`、`hops`、`opened`（有则显示，空则 `—`）。

短表不展开这四层。运行路径始终多三行：`skills`（技能调起）、`choices`（委派 / 模型决定）、`hops`（组件跳）。空着写 `(none)`，用来看见哪一轮没记。


| `signoff` | **本轮若写入** `sealed` / `accepted` / `aligned` / `resolved`，或记了 `chose: chat-confirm-signoff`，**则必填**；否则写 `status: none` 或整段省略 |

### `append` 生成的三段

导体只写意图、理由和思考。下面三段由 `append` 从记录生成，手写的同名段会被覆盖：

| 段 | 来源 |
|----|------|
| `round` | 本轮窗口：`since` 是上一条 trace 的 `round.until`（旧 trace 用 `at`），`until` 是落盘时刻。一份留痕只进一条 trace |
| `delegations[]` | 窗口里落下的委派留痕，每份一条：`agent` / `feature` / `step` / `attempt` / `role`（`writer` 或复核的 `verifier`）/ `status` / `record`。平铺副本和 run 目录里的同一份只算一次。条数就是留痕份数 |
| `recorded[]` | 窗口里 `run.yaml` 记下的步：`feature` / `step` / `kind` / `status` / `by`（签字人，否则执行者，否则 `conductor`）/ `run`。人签门 PASS 另带 `mark`（`accepted_req` / `accepted_arch` / `accepted_plan` 记 `accepted`；`aligned`、`resolved` 记同名标记） |

`recorded` 里有带 `mark` 的门、而 trace 没写 `signoff` 或写的是 `status: none` 时，`append` 按门补上 `signoff`：`status: recorded`、`marks`、`by` 是签字人、`evidence` 是 `<run.yaml>#<step>.signoff`。不在产品仓里跑（内核会话）时不生成这三段。

### `signoff` 块（v2 增补）

```yaml
signoff:
  status: none        # none | pending | recorded
  marks: []           # sealed | accepted | aligned | resolved
  by: ""              # 人名；禁止 agent / ai / idev
  evidence: ""        # 确认原话摘要，或仓内 YAML 路径#字段
```

规则：

1. 对话确认代写签收字段前，必须先有本轮确认用语（见 [chat-confirm-signoff.md](chat-confirm-signoff.md)）。记了 `chose: chat-confirm-signoff` 就要有这一块：`by` 是确认的人，`evidence` 是原话；最后没写任何字段就 `status: none`、`marks: []`。
2. `decisions` 里若出现「不写 sealed/aligned」等拒绝项，**不要**填 `marks`；`status: none`。
3. 仅复述「他票仍 sealed」或读回 `aligned=true` 不算本轮写入，`status: none`。
4. 算「本轮写了」的只有三处：`signoff.marks` 非空、`repo` 调用的 `result` 写明写入（`写入 sealed`、`set aligned` 这类）、`recorded` 里带 `mark` 的门。这时 `status` 必须是 `recorded` 或 `pending`。检查只看这些字段，trace 别处出现「禁止」「不写」之类的词不会放行，也不会触发。
5. `trace.py append` 与 `trace.py check` 按上面拦；`bash scripts/audit-traces.sh` 用同一个判断计硬报警。



## 不要

- 写「全面对齐」、用 LLM 自评当门禁
- 把观测当签字；`sealed` / `accepted` / `aligned` / `resolved` 仍须人授权（改 YAML 或确认用语，见 [chat-confirm-signoff.md](chat-confirm-signoff.md)）
- 为写 trace 再开 Skill 或第二套 eval
- deliver / ops 调用 verify 时为导体进化另停一次（本文件也不另停）
- 把长篇推理全文塞进 `thinking.summary` 或 `calls.thinking`（过程用 `steps`，一跳只用一行）
- 伪造未发生的 `calls` / `opened` / 技能 / 委派 / 模型
- 因为没写 `how`、`skills`、`delegate`、`from`/`to` 就再停一轮补记

## 运行路径视图

把一条 trace 展成实际执行路径（便于优化 shortcut / 减负），**不是**打分：

```bash
bash ~/.cursor/skills/idev/scripts/path-view.sh              # 最近一条
bash ~/.cursor/skills/idev/scripts/trace.sh path <file.yaml>
bash ~/.cursor/skills/idev/scripts/path-view.sh paths 20
bash ~/.cursor/skills/idev/scripts/path-view.sh stats 50
```

字段来源：`invoke.trigger` → `invoke.how` / `skills` → `route.scenario/module/stage` → `decisions` 里的 `delegate` / `model` → `thinking.steps` → `calls[]`（`from`→`to`、`why` 或一行 `thinking`、`result`、耗时）→ `opened[]` → `next`。顶层 `react:` 指向这一轮的循环文件。`path` 在 hops 一行下面按跳列出「追踪」。
S8 配方：`workflows/path-view.yaml`。

控制台详情把同一条链从上到下画出来（Thought / Observation / 耗时）。时间线另列 `kind: tool` 或 `from` 以 `react:` 开头的跳。仍不打分，不为观测另停。

同一份账也可以摊成页。`python3 scripts/console.py` 只绑 `127.0.0.1`，看各 agent、耗时、skill 调起和详情，并把最近窗口的场景、耗时、观察覆盖、回报、技能和假设摊成件数。点某一格可以把那一件数当作依据，写下改关口、改这一步、补观测或质疑基线。页面上的任务和对话写在 console 目录的 `thread.yaml`（导体自身会话是 `state/console/`，产品会话是 `<repo>/.idev/console/`），不是 verify inbox。导体下一轮用 `console.py pending` 读取，用 `reply --text` 写回。派工前 `live --add`，`record` 后 `live --clear`。控制台不签字、不派 agent，也不打分。

## 票据结果指标（事实，不打分）

```bash
bash ~/.cursor/skills/idev/scripts/ticket-metrics.sh                 # 票据仓取 state/outbound-config.json 的 product_root
bash ~/.cursor/skills/idev/scripts/ticket-metrics.sh --repo <仓根>   # 显式指定含 <票目录>/deliver.yaml 的仓
```

输出 markdown 表，每票：首次/最近 trace 日期与跨度、S2 推进次数（trace 中 `route.scenario: S2` 条数）、reopen 次数（`deliver.yaml` 的 `revisions[]` 备注含「解除密封/reopen」与 `baseline_revision-1` 取大）、签字后被推翻次数（`revisions[]` 备注含「作废/推翻/回退/rewind」；仅有 `last_rewind` 时记 1，为**下界**）。
得不到（未绑票 `-`、无对应 `deliver.yaml`、未配置票据仓）一律写 `n/a`，不推测。**只陈列事实，不给分、不设阈值**；周审计时与 `audit-traces.sh 50` 一起看。feature 字段若含多票（逗号串）按原样成一行。
