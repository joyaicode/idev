# idev

人机共驾的 AI 端到端交付生命周期导体 —— **一个 skill 当导体，五个 agent 当执行者**。

真源是这个 git checkout；`~/.cursor/skills/idev` 是指向它的 symlink，别名
`~/.agents/skills/idev`、`~/.joycode/skills/idev` 再指向那里。只有一份内容。

## skill 与 agent：为什么要两种机制

| | **skill**（`/idev`） | **agent**（`/idev-coder` 等五个） |
|---|---|---|
| 身份 | 导体，注入主会话 | 执行者，独立上下文 |
| 做 | 认票 · 路由 · 组委派包 · 验收回报 · 记账 | 在落点页里干活 · 产出工件 · 给证据 |
| 独占 | **签字权** · 与人交互 · 写 trace | 上下文隔离 |
| 不能 | 亲自执行已委派的 step | 签字 · 问人 · 写 trace |

**不是选择，是约束：** `scripts/lib/workflow_spec.py` 的 `is_human()` 黑名单正是
`{agent, ai, cursor, assistant}`——**agent 签字在代码层就被拒**；subagent 看不到对话历史，
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
| `scripts/delegation.py` | 委派留痕：write / check / replay / timeline / eval |
| `scripts/agent-metrics.py` · `agent-review.sh` | 跨票指标 · 定期复盘（只起草不 land） |
| `scripts/failure_signature.py` · `hypothesis.py` | 提效：失败签名归一化 · 假设台账 |
| `references/agents*.md` · `boost.md` · `failure-modes.md` | 委派契约 · 自进化 · 提效细则 · 失败模式清单 |
| `state/` | 仅导体自身会话的中间产物；产品会话写到该仓 `.idev/` |

产线流水线不写进本仓。当前试点产线配方在：

`~/go/src/coding.jd.com/joypaas/.idev/workflows/`

其它产品仓只留 `marker.yaml` + `extension_root: ../joypaas`（或等价相对路径）。

## 装 agent

```bash
bash scripts/link-agents.sh      # agents/*.md -> ~/.claude/agents/（Cursor 兼容读同一处）
```

`/idev` 不需要安装——idev 本身就是 skill。待办与验证状态见
[references/agents-todo.md](references/agents-todo.md)。

## 本机自检

**按顺序跑，前一道过不了后面的结论就不成立：**

```bash
cd ~/.cursor/skills/idev
bash scripts/syntax-check.sh       # 1 纯解析全部脚本，零副作用
python3 scripts/agents-check.py    # 2 agent 定义 + 回报格式 + 登记表同步
bash scripts/workflow-check.sh     # 3 配方与 run 契约
bash scripts/refs-check.sh         # 4 文档交叉引用
bash scripts/selfcheck.sh          # 5 内核锁
bash scripts/agent-smoke.sh        # 6 委派层端到端 143 条
bash scripts/healthcheck.sh        # 7 环境与拓扑
```

全部期望 `PASS`。`syntax-check` 必须第一个跑——**smoke 抓不到 smoke 自己的语法错**，
不能解析的脚本一条断言都不会执行。详见
[references/failure-modes.md](references/failure-modes.md) 第十一条。

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

要票配方加 `--feature <票名>`。停问步（`human.gate`）记 PASS 必须带人的 `--by` 与确认用语 `--quote`（确认 / 全签 / 同意 / LGTM）。

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
