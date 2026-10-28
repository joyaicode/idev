# idev

人机共驾的 AI 端到端交付生命周期导体 —— **一个 skill 当导体，五个 agent 当执行者**。

真源是这个 git checkout；`~/.cursor/skills/idev` 是指向它的 symlink，别名
`~/.claude/skills/idev`、`~/.agents/skills/idev`、`~/.joycode/skills/idev` 再指向那里。只有一份内容。

## skill 与 agent：为什么要两种机制

| | **skill**（`/idev`） | **agent**（`/idev-coder` 等五个） |
|---|---|---|
| 身份 | 导体，注入主会话 | 执行者，独立上下文 |
| 做 | 认票 · 路由 · 组委派包 · 验收回报 · 记账 | 在落点页里干活 · 产出工件 · 给证据 |
| 独占 | **签字权** · 与人交互 · 写 trace | 上下文隔离 |
| 不能 | 亲自执行已委派的 step | 签字 · 问人 · 写 trace |

**不是选择，是约束：** `scripts/lib/workflow_spec.py` 的 `is_human()` 按词表拒绝 agent / 模型 / 角色名，存在
`config/people.yaml` 时还须在白名单里——**agent 名字签字在代码层就被拒**；subagent 看不到对话历史，
无法与人往复确认；Cursor 的「subagent 启动的 subagent 不能再启动」也要求导体在主会话。
把导体也做成 agent，等于把「人机共驾」降级成「无人值守」。

两者之间只有三样接口：**委派包**（skill→agent）、**回报**（agent→skill）、
**留痕**（双向存原文，可重放）。职责分离全文见 [references/agents.md](references/agents.md)。

## 目录

| 路径 | 作用 |
|------|------|
| `SKILL.md` | 唯一入口：导体 · 场景路由 S1–S8 · skill↔agent 分工 · 提效三板斧 |
| `agents/` | 五个执行者：deliver（需求/架构/文档）· coder（编码/构建/提交）· reviewer（审查）· verifier（红绿/环境）· ops（排障/论证） |
| `workflows/` | 内核编排配方（任何产线都能用） |
| `deliver/` `verify/` `ops/` `docs/` `conventions/` | 阶段模块与规约 |
| `scripts/workflow.py` | 按配方驱动 `run.yaml`，`next` 打印 `OPEN` 落点页 + `DELEGATE` 派给谁 |
| `scripts/lib/kind_agents.py` | `kind → agent` 登记表（29 kinds / 5 agents，24 委派 / 5 导体保留） |
| `references/feedback-loop.md` | 双向反馈环：下游质疑上游 · 订正后全线对准 · 交付后跟进 |
| `scripts/lessons.py` | 经验台账：六问必答 · 候选→人确认+复现→权威 · 召回只给建议 |
| `references/rootcause-guards.md` | 根因六条强约束：来源/时间窗/穿透/双证据/快照/排除举证 |
| `scripts/artifact-match.py` | 运维:产物与源码是否同源（MATCH/AHEAD/UNKNOWN） |
| `scripts/realign.py` | 需求订正后查七类漂移，给出向前的重做顺序 |
| `scripts/ui-evolve.py` | 编写阶段查剧本状态冲突，提 branch / reorder 方案（不改文件） |
| `scripts/ui-playbook.py` | UI 剧本生命周期：create→read→change→restore→cleanup，实体打标 |
| `scripts/req-ground.py` | 密封前把需求落到既有代码：落点/影响面/冲突/边界/方向 + 竞品对比 |
| `scripts/ui-spec.py` | 需求细到交互层：校验 `ui` 规则，生成 json-render spec + 零依赖预览 |
| `scripts/stage-gate.py` | 七视角把关：experts.md 拒过清单里可机检的那一半（`--list`） |
| `scripts/delegation.py` | 委派留痕：write / check / replay / timeline / eval |
| `scripts/agent-metrics.py` · `agent-review.sh` | 跨票指标 · 定期复盘（只起草不 land） |
| `scripts/failure_signature.py` · `hypothesis.py` · `turn-budget.py` | 提效：失败签名归一化 · 假设台账 · 首句前的无正文回合 |
| `references/agents.md` · `agents-playbook.md` | 委派契约（是什么）· 唤起与配合最佳实践（怎么用） |
| `references/boost.md` | 提效：**本地事实优先**（文档会过时）· §0 交代 · 签名归一化 · 假设台账 |
| `references/code-agent.md` · `scripts/repl.py` | 用代码表达推理：计算的源码与输出落成证据 |
| `references/agent-accuracy.md` | 准确率护栏：借 Cursor/Claude Code 的机械约束（6 条机检） |
| `references/external-tools.md` | Langfuse 导出 · promptfoo 回归断言 · 为什么不装 DSPy |
| `scripts/langfuse-export.py` · `promptfoo-gen.py` | 离线导出观测 · 生成格式与边界断言（0 评分） |
| `references/agents-evolve.md` · `failure-modes.md` · `agents-todo.md` | 可调试与自进化 · 失败模式清单 · 待办 |
| `state/` | 仅导体自身会话的中间产物；产品会话写到该仓 `.idev/` |

产线流水线不写进本仓。当前试点产线配方在：

`~/go/src/coding.jd.com/joypaas/.idev/workflows/`

其它产品仓只留 `marker.yaml` + `extension_root: ../joypaas`（或等价相对路径）。

## 装 agent

```bash
bash scripts/link-agents.sh          # 装到 ~/.claude/agents 与 ~/.cursor/agents
bash scripts/link-agents.sh --check  # 核对两处是否齐全      # agents/*.md -> ~/.claude/agents/（Cursor 兼容读同一处）
```

`/idev` 的 skill 别名由 `bash scripts/link-idev-aliases.sh` 安装——Claude Code
只从 `~/.claude/skills` 读用户级 skill，该别名必需（2026-10-19 实测验证）。
待办与验证状态见 [references/agents-todo.md](references/agents-todo.md)。

## 本机自检

**按顺序跑，前一道过不了后面的结论就不成立：**

```bash
cd ~/.cursor/skills/idev
bash scripts/syntax-check.sh       # 1 纯解析全部脚本，零副作用
python3 scripts/agents-check.py    # 2 agent 定义 + 回报格式 + 登记表同步
bash scripts/workflow-check.sh     # 3 配方与 run 契约
bash scripts/refs-check.sh         # 4 文档交叉引用
bash scripts/selfcheck.sh          # 5 内核锁 26 道
bash scripts/agent-smoke.sh        # 6 委派层端到端 481 条
bash scripts/healthcheck.sh        # 7 环境与拓扑
```

全部期望 `PASS`。`syntax-check` 必须第一个跑——**smoke 抓不到 smoke 自己的语法错**，
不能解析的脚本一条断言都不会执行。详见
[references/failure-modes.md](references/failure-modes.md) 第十一条。

单测与快照核对另跑，不进上面这条链（都不依赖内核拓扑）：

```bash
python3 scripts/test_signoff.py      # 签字文法与身份，165 条共享用例
python3 scripts/test_concurrency.py  # 三条写盘路径的并发不丢失
python3 scripts/test_signals.py      # SIGNAL / 决策答复规则
bash test/golden/record.sh --verify  # 50 个 golden 场景（46 + fixed 4）：CLI 输出快照（Go 迁移安全网）
python3 scripts/gen-kinds.py --check # kind 表的五份生成物是否最新
```

**两本引擎账，改 CLI 或改 `workflow.py` 时两本都要绿：**

| 车道 | 引擎 | 覆盖 |
|---|---|---|
| `test/golden/record.sh --verify`（50 个 txtar，含 `fixed/` 4 个） | 钉死 `IDEV_ENGINE=python` | Python 驱动自己的行为（含签字文法），字节级快照 |
| `scripts/selfcheck.sh` 驱动段 | 钉死 `IDEV_ENGINE=python` | run 状态机、AUTO、独立验证等语义锁 |
| `test/gate-channel.sh`（14 例）/ `test/lease-channel.sh`（17 例） | 默认 go（自建 `bin/idev` + `IDEV_BIN`/`IDEV_DATA`） | gate/lease 通道：短码、TTY、白名单、写租约与 verify 租约围栏 |
| `go test ./...` | Go 进程内 | runsvc / gatesvc / leasesvc / sqlite store、e2e 七步 |

## Go 核心（迁移中）

设计全文在 [design/idev-refactor-design-v3.md](design/idev-refactor-design-v3.md)
（SHA-256 `7db523d4…974fcbde`）。两套引擎各管各的账：

- **Python `scripts/workflow.py` 拥有 `run.yaml`**：配方驱动、委派留痕、票 YAML
  仍是它写。`IDEV_ENGINE=python` 是回退开关（golden 与 selfcheck 驱动段钉死用它）。
- **Go CLI `cmd/idev` 拥有 gate、lease、审计**：A 类签字走终端短码
  （`idev gate request/approve`），写租约走 `idev lease acquire/release`，
  降级批准（`assurance.downgraded`）按周计数走 `idev audit downgrades`，
  审计链复算走 `idev audit verify`（`--from 1` 从创世算起，断链报出第一条坏的
  seq 并退出 1），数据落在 `~/.idev`（`IDEV_DATA`）。默认引擎是 go——`workflow.py` 的
  `record <gate> PASS` 与 `delegate` 会调 CLI（找 `bin/idev`，其次 PATH，或
  `IDEV_BIN` 直指）；没有二进制时 A 类签字报错并给出两个出路
  （`go build -o bin/idev ./cmd/idev`，或 `IDEV_ENGINE=python` 回退）。

```bash
go build -o bin/idev ./cmd/idev   # workflow.py 默认找 bin/idev
go test -race ./...               # domain 零 IO；app 与 sqlite 同测，domain 覆盖率门槛 90%
golangci-lint run ./...           # depguard 守住 domain 零 IO
python3 scripts/gen-kinds.py      # 改 registry/kinds.yaml 后重新生成五份副本
```

- `registry/kinds.yaml` 是 **kind 表的唯一真源**。加一个 kind 只改这个文件，再跑
  生成器；`selfcheck` 会检查生成物是否最新。
- `api/schemas/` 是契约真源（JSON Schema Draft 2020-12，10 份）。`recipe.schema.json`
  与 Python 的 `workflow_spec.check_recipe` 对同一批配方给出相同判断，有测试守着。
- `internal/domain/` 零 IO：状态机与策略都是纯函数。这条约束由 `.golangci.yml` 的
  depguard 规则强制，CI 里有一个探针确认它真的会拦。
- `pkg/canonical` 与 `pkg/schemas` 可被仓外 import：离线核验一份密封或一条批准记录
  不需要跑 idevd。

## 驱动一次配方（产品仓内）

```bash
W=~/.cursor/skills/idev/scripts/workflow.py
cd ~/go/src/coding.jd.com/kafka-project   # 任意带 marker 的产品仓

$W resolve localdev-start                # 经 extension_root 找到 joypaas 配方
$W start localdev-start --param product=kafka
$W next
$W record <step> PASS --evidence …
$W status
```

要票配方加 `--feature <票名>`。停问步（`human.gate`）等人在聊天里回确认用语，再 `record PASS --by <人名> --quote "确认"`。这句话就是签字；门还开着时，同一句原话把它批准。

## 推到 GitHub（以后）

仓库已在本目录初始化。授权后再推：

```bash
brew install gh          # 若未装
gh auth login --web --scopes repo
cd ~/.cursor/skills/idev
gh repo create idev --private --source=. --remote=origin --push
```

或把远端地址换成你账号下已有空仓：

```bash
git remote add origin git@github.com:<你的账号>/idev.git
git push -u origin main
```

## 提交点

| commit | 说明 |
|--------|------|
| `912c836` | workflow 三件套快照（语法 / 校验 / 驱动 + 14 份内核配方） |
| （本说明之后） | 补齐 `will_write` 校验说明 + 本 README |

变更细节见 [references/changelog.md](references/changelog.md)。使用说明见 [references/guide.md](references/guide.md)。
