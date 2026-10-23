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
| `tool` | 外部 runner / Playwright / gh（点到为止） |
| `agent` | 五个执行者之一。`target` 写 agent 名。不要记成 `module` |
| `model` | 这一跳调用的模型。`name` 是模型名或 `inherit` |

一条 call 上还可以写这些观察字段。都可选；写了就必须是完整的：

| 字段 | 含义 |
|------|------|
| `from` / `to` | 组件跳的两端，必须同时有。写法：`user` · `conductor` · `skill:<name>` · `agent:<name>` · `module:<name>` · `script:<name>` · `repo:<name>` |
| `model` | 这一跳用的模型，通常 `inherit` |
| `thinking` | 这一跳的思考，**一行**。过程放 `thinking.steps`，不要把整段推理贴进来 |
| `duration_s` | 秒，非负数字。没有计时就空着，不要填 0 充数 |
| `why` | 为什么有这一跳 |
| `target` | `kind: agent` 时写 agent 名 |

### 四层观察写在哪

| 想看的 | 写在 | 路径视图 |
|--------|------|----------|
| 技能调起 | `invoke.how` + `invoke.skills[]`。这一下要出现在跳转里，再加一条 `kind: skill` 的 call（`from: user`，`to: skill:<name>`） | `skills` |
| agent 决策 | `decisions` 一条 `kind: delegate`。真的派了，再加 `kind: agent` 的 call | `choices` |
| 模型与思考 | `decisions` 一条 `kind: model`，以及 `kind: model` 的 call。`thinking` 只留一行 | `choices` 与 `hops` 上的 `model=` / 「」 |
| 组件交互 | 每一跳的 `from` / `to` | `hops` |

缺了这四层**不算失败**，周审计只计数、不报警。不准编造没发生的技能、委派或模型调用。

## 对话短表

落盘始终全量 v2。给人看的表：

| `route.scenario` | 对话输出 |
|------------------|----------|
| S2 / S3 / S5 / S8 | 只打 `trigger` / `route` / `stop` / `next`（S8 的 route 含 workflow id / step） |
| S1 / S4 / S6 / S7 或缺省 | 全表：另含 intent、feature、matched、why、rejected、thinking、calls、opened、conventions、decisions、check |

`render` 全表会多展示：`trigger`、`matched`、`skills`、`thinking`、`calls`、`hops`、`opened`（有则显示，空则 `—`）。

短表不展开这四层。运行路径始终多三行：`skills`（技能调起）、`choices`（委派 / 模型决定）、`hops`（组件跳）。空着写 `(none)`，用来看见哪一轮没记。


| `signoff` | **本轮若写入** `sealed` / `accepted` / `aligned` / `resolved` **则必填**；否则写 `status: none` 或整段省略 |

### `signoff` 块（v2 增补）

```yaml
signoff:
  status: none        # none | pending | recorded
  marks: []           # sealed | accepted | aligned | resolved
  by: ""              # 人名；禁止 agent / ai / idev
  evidence: ""        # 确认原话摘要，或仓内 YAML 路径#字段
```

规则：

1. 对话确认代写签收字段前，必须先有本轮确认用语（见 [chat-confirm-signoff.md](chat-confirm-signoff.md)）。
2. `decisions` 里若出现「不写 sealed/aligned」等拒绝项，**不要**填 `marks`；`status: none`。
3. 仅复述「他票仍 sealed」不算本轮写入，`status: none`。
4. `bash scripts/audit-traces.sh` 会抽检「疑似写入签收但无 signoff」。



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

字段来源：`invoke.trigger` → `invoke.how` / `skills` → `route.scenario/module/stage` → `decisions` 里的 `delegate` / `model` → `thinking.steps` → `calls[]`（`from`→`to`、`model`、一行 `thinking`）→ `opened[]` → `next`。
S8 配方：`workflows/path-view.yaml`。

## 票据结果指标（事实，不打分）

```bash
bash ~/.cursor/skills/idev/scripts/ticket-metrics.sh                 # 票据仓取 state/outbound-config.json 的 product_root
bash ~/.cursor/skills/idev/scripts/ticket-metrics.sh --repo <仓根>   # 显式指定含 <票目录>/deliver.yaml 的仓
```

输出 markdown 表，每票：首次/最近 trace 日期与跨度、S2 推进次数（trace 中 `route.scenario: S2` 条数）、reopen 次数（`deliver.yaml` 的 `revisions[]` 备注含「解除密封/reopen」与 `baseline_revision-1` 取大）、签字后被推翻次数（`revisions[]` 备注含「作废/推翻/回退/rewind」；仅有 `last_rewind` 时记 1，为**下界**）。
得不到（未绑票 `-`、无对应 `deliver.yaml`、未配置票据仓）一律写 `n/a`，不推测。**只陈列事实，不给分、不设阈值**；周审计时与 `audit-traces.sh 50` 一起看。feature 字段若含多票（逗号串）按原样成一行。
