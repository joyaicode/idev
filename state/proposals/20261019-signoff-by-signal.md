# 提案：签字从「按位置停」改为「按信号停」+ 架构衔接问题清单

- status: implemented（2026-10-19，切片 1–3 已落并经人确认；遗留：验证租约时机不一致、deliver 签字强制 `approval_id`，见第六节）
- scope: 签字点收敛、决策包统一格式、执行者回报信号驱动停问、Go gate + lease 接线；顺带修 agent / skill / 工具衔接上的确定性问题
- 不改：人机共驾定位；不可逆动作必须人闸；红绿只走 verify；agent 不签字

## 一、现状证据（2026-10-19 起草时）

| 事实 | 证据 |
|---|---|
| 真正在跑的是 Python `scripts/workflow.py`；Go 内核约 17k 行（含测试）没有入口 | 全仓 `func main` 只有 `tools/covergate/main.go` |
| `registry/kinds.yaml` 的 `lease`、`verify: independent`、`verifier` 只出现在生成物里，Python 执行路径不执行 | `rg independent scripts/` 只命中 `_generated_kinds.py`、`kind_agents.py` |
| Go 的独立验证在 run 状态机里（E6 `VerificationRecorded`，拒绝写者自验），不在 gate / lease 里 | `internal/domain/run/run.go:496-517` |
| 14 个内核配方都有 `human.gate`，共 17 个；其中 3 个 `will_write: []` | `path-view`、`weekly-trace-audit`、`lite-change.gate-next`（已修，见第六节） |
| P1 票从 S1 到 done 固定停 4–5 次，配方内再叠 plan gate、gate-next | `invoke.md` 门禁停问表、`chat-confirm-signoff.md` 代写表 |
| 执行者已有不确定信号 `BLOCKED(logic)` / `ASSUMED` / `OPEN`，但 `delegation.py` 只检查 `ASSUMED` 行**存在** | `delegation.py:159-202` |
| `--by` 与 `--quote` 都由导体（也是 agent）填写；白名单拦的是编出来的名字，拦不住导体照抄真人名 | `workflow.py:353-370` |
| `check-feature verify-plan` 已查「每条 item 有用例 / slice 挂接 / 无证据 PASS」，但「correctness 有 runner」只在 `test` 阶段查 | `check-feature.py:816-868` |

## 二、架构问题（按影响排序）

1. **两套内核，声明与执行脱节。** Go 侧设计严谨但不在运行路径上；Python 在跑却不执行 `kinds.yaml` 一半字段。文档描述的独立验证只在 Go 测试里成立。
2. **签字规则散在至少 8 处并已漂移。** `SKILL.md`、`agent-brief.md`、`invoke.md`、`chat-confirm-signoff.md`、`hitl-risk-tiers.md`、`deliver/references/gates.md`、`deliver/SKILL.md`、`verify/SKILL.md`。漂移例：P2 档位两表不一致；`gates.md`「语义门 Agent 不得代勾」与 chat-confirm「代写 `semantic_gate`」冲突；黑名单与 `CALL_KINDS` 描述过时（后两项已修）。
3. **停问按位置而不是按信息。** 每阶段末尾固定停；真正的不确定信号只被检查「写没写」，不触发停问。
4. **防伪投入错位。** 词表与语料防不住导体照抄人名；真正的防线要靠终端短码 / passkey。
5. **导体每步负担过重。** 每个委派步 6–7 个动作；五个 agent 定义 160–383 行且边界规则各重述一遍。

## 三、定稿方案

### 3.1 两类停问

**A 类：签字**（固定停；`by` + `quote` + 内容摘要；终端短码 `idev gate approve`，P2 可退回对话确认）

| 闸 | 档位 | 摘要绑定 |
|---|---|---|
| `sealed`（P1/P2 并入 `req.accepted`） | 全部 | P1/P2：`baseline.yaml` + `req.yaml`；P0：`baseline.yaml` |
| `req.accepted` | 仅 P0 单独签 | `req.yaml` |
| `arch.accepted` | 全部 | `arch.yaml` |
| `plan.accepted` | 仅 P0 | `verify/plan.yaml` |
| `aligned`（提测） | 全部 | plan + report |
| ops `resolved` | 仅 P0 | `ops.yaml` + 假设台账 |
| `reopen_baseline` / `origin=` 回退 | 全部 | 带关键字 |
| `promote` / 生产写、`git push` | 全部 | 动作参数 |
| `lessons promote`（候选 → 权威） | 全部 | lesson 条目 |

**B 类：决策**（有信号才停；记 `decisions.yaml`，不走签字仪式）

| 信号 | 来源 |
|---|---|
| `BLOCKED(logic)` | 任一执行者回报 |
| `ASSUMED: [承重] …` | 回报（每条必须带 `[承重]` / `[非承重]` 前缀，或整行写「无」） |
| grill frontier 非空 / `baseline-conflict` / `objections` 非空 | `grill.md`、`baseline.yaml` |
| 方案分叉未决 | `arch.yaml` |
| 残留 `UNPROVEN` 需人接受风险 | verify `report.md` |
| 有界修复红线命中 | `hypothesis.py check` 退出码 2 |
| `check-feature` / `stage-gate` FAIL 且一次修复后仍 FAIL | 脚本退出码 |
| P1/P2 plan：有 UNPROVEN、增删用例、或非基线 1:1 派生 | `check-feature verify-plan` |
| P1/P2 resolved：根因未证可红绿切换或台账有未决项 | `hypothesis.py check` |

**自动通过**：不属于 A 类、也没有 B 类信号的点，step 记 `status: AUTO` + `evidence: <机检输出路径>`；`plan.yaml` / `ops.yaml` 写 `auto: <路径>`，不写 `by`。`check-feature` 接受「人名 `by`」或「`auto` + 可读证据文件」二者之一。

> 切片 2 修正：`semantic_gate` **不**设 `auto`。它记的 req-review / req / arch 在每个档位都是 A 类，切片 1 加的 `auto` 分支会让导体凭一个文件绕过密封的语义门，已删。ops 分类、环境/产物两个旧停问点归 B 类（`BLOCKED(logic)`、新增信号 `ARTIFACT: UNKNOWN`；`AHEAD` 有固定动作，不停）。plan 的「有 UNPROVEN」指无 runner 的用例或 `unproven_surfaces`，未跑的 `UNPROVEN` 不算；`human_signoff` 的 PENDING 项留到提测签字时给人看。`debug-repro` 的闸同时确认环境，不加 `auto_tiers`。

P1 票从 S1 到 done：固定签字 3 次（密封、arch、提测），其余按信号出现。

### 3.2 决策包（每次停问唯一格式）

```
【需要你决定】<停问点>  risk_tier=<P0|P1|P2>
触发: <A 类闸名 | B 类信号 + 出处路径>
问题:
  1. <一句话问题>  选项: a) … b) …  AI 建议: a，因为 …
证据: check-feature=<…>  stage-gate=<…>  PASS/FAIL/UNPROVEN=<n/n/n>  未决 grill=<id|无>
将代写: <字段列表>（A 类）
签字: idev gate approve <短码>（A 类；P2 可在对话里回确认用语）
```

- 一次停问合并当时所有 B 类信号；A 类闸与 B 类问题同时出现时，先答 B 类，再签 A 类。
- B 类有效回答：选项号（`1a`）或自由文本，原话照存；`继续` / `ok` 这类不针对问题的回答不算，导体重问。
- A 类有效确认：仍走 `parse_confirm` 文法（`确认 / 全签 / 同意 / LGTM` + 关键字）。

### 3.3 `decisions.yaml`

票目录下，只追加；无票 run 记 `workflow/decisions.yaml`。每条字段：`id` / `signal` / `source` / `question` / `options` / `ai_recommendation` / `answer` / `quote` / `at`。周审计统计「`[非承重]` 后被推翻」与「AUTO 后被推翻」次数，用于校准降级判据。

### 3.4 独立验证

`kinds.yaml` 标 `verify: independent` 的写代码 kind，`workflow.py record <step> PASS` 必须带 `--verified-by <agent>` 与验证回报路径，验证者不得是写者，否则 BLOCKED。语义与 Go E6 一致，Go 接管 run 时对拍。

### 3.5 Go 接线

`cmd/idev`：`gate request / approve / status`、`lease acquire / release`。gate 类型删 `step_confirm`，新增 `decision`（B 类，low assurance，无 `will_write`）与 `sealed` 的双摘要形态。A 类闸 CLI 做好即默认走 Go，`IDEV_ENGINE=python` 为回退开关；不设影子期（终端短码是新增防线，Python 无对应行为可对拍）。

## 四、拷问记录

| 轮 | 问题 | 定 |
|---|---|---|
| 0 | Go 内核接线还是冻结 | 接线 |
| 0 | P1 `arch.accepted` 是否降级 | 不降，全档位 A 类 |
| 1 | 接线范围 | 先 gate + lease CLI |
| 1 | B 类是签字还是决策 | 决策 |
| 1 | `plan.accepted` | P0 A 类；P1/P2 B 类 |
| 1 | `ASSUMED` 触发 | 执行者标承重，只承重触发 |
| 1 | 顺序 | 先修三项 bug |
| 2 | A 类签字通道 | 终端短码；P2 可对话；passkey 等 P3 |
| 2 | 决策台账 | `decisions.yaml` |
| 2 | `req.accepted` | P1/P2 并入密封；P0 单签 |
| 2 | ops `resolved` | P0 A 类；P1/P2 B 类 |
| 2 | `semantic_gate` 自动写法 | `passed` + `auto: <路径>` |
| 3 | 独立验证 | 先在 `workflow.py` 实现 |
| 3 | Go gate 默认时机 | CLI 好即默认，有回退开关，不设影子期 |
| 3 | 承重标注写法 | 行前缀 `[承重]` / `[非承重]`，JSON schema 同步加字段 |
| 3 | 实施顺序 | 切片 1 → 2 → 3 |
| 3 | `late-lifecycle-smoke` 白名单失败 | 冒烟用临时 `people.yaml`（已修） |

## 五、实施切片（每片自带测试、单独可回滚）

1. **Python 语义**：`AUTO` 状态（`workflow_spec` / `run.schema.json` / Go `run` 状态同步）；`semantic_gate.auto`（`check-feature`）；`decisions.yaml` 读写与 B 类停问插入（`workflow.py`）；`ASSUMED` 承重前缀校验（`delegation.py` + 五个 agent 回报格式 + `delegation-return.schema.json`）；独立验证校验（`workflow.py record --verified-by`）；plan 阶段 correctness runner 检查。
2. **配方与文档**：plan / resolved 按档位；req 并入密封；签字规则收敛到一页（`chat-confirm-signoff.md` 改为决策包协议），其余 7 处改一行指针；`invoke.md` 与 `hitl-risk-tiers.md` 档位表合为一张。
3. **Go 接线**：`cmd/idev` gate + lease 子命令；gate 类型调整；`workflow.py` 的 A 类闸改走 CLI；`IDEV_ENGINE` 回退。

## 六、已完成（2026-10-19）

| 项 | 改动 | 证据 |
|---|---|---|
| 跳过契约 | `workflow.py` 报错与 `workflow-schema.md`：`SKIPPED` 的 `--evidence` 可以是先前签字，或表明无可签内容的文件 | golden `gate-skip-no-evidence` 重录 |
| 空签字点 | `path-view` / `weekly-trace-audit` 删 `note`（后者改 `--strict`，有硬项 FAIL 停）；`lite-change` 删 `gate-next`（6 步）；`lite-change-smoke` 锁改为 ≥1 gate；Go e2e FAIL 注入移到 `plan`、驳回移到 `gate-plan`，新增「驳回后不能激活 run」断言 | `go test -race ./test/e2e/` 7/7；golden 39/39 |
| 过时描述 | `SKILL.md`、`README.md`、`agents.md`、`cohesion.md`、`code-agent.md`、`chat-confirm-signoff.md`、`kind_agents.py` | `gen-kinds --check`、`agents-check` PASS |
| 冒烟依赖真实名单 | `late-lifecycle-smoke.sh` 最后一步用临时 `IDEV_ROOT/config/people.yaml` | `selfcheck.sh` PASS |
| 切片 1：`AUTO` | `workflow_spec`（状态、`with.auto_tiers` 校验）、`workflow.py record`（档位在 `auto_tiers` 内 + `--evidence`，不许 `--by`）、`common.schema.json`；Go `run` 状态推迟到切片 3（Go 侧尚无产出 AUTO 的路径） | golden `gate-auto-undeclared`、`record-bad-status` |
| 切片 1：B 类停问 | `delegation.py` 回报算 `signals`（`BLOCKED(logic)`、`[承重]`）并打印 `SIGNAL`；`record PASS` 有未答信号 → BLOCKED；`workflow.py decide` 写 `decisions.yaml`，拒 `继续` / `ok`，拒留痕里没有的信号 | golden `delegation-signal` → `signal-blocks-pass` → `decide-non-answer` / `decide-wrong-signal` → `decide-ok` → `signal-answered-pass` |
| 切片 1：承重标注 | `assumption-tagged` 检查（Python + Go `delegsvc`，parity 表登记）；四个 FACTS agent 回报格式与检查表；`delegation-return.schema.json` `assumed.pattern` | `TestAssumptionsSayWhetherTheyBearLoad`、`TestPythonChecksAreEitherPortedOrListedAsDeferred` |
| 切片 1：独立验证 | `KIND_VERIFIER` 的 kind `PASS` 须 `--verified-by <登记者> --verify-evidence`，写 `step.verification`；`next` 打印 `VERIFY` | golden `code-pass-unverified`；selfcheck case 14 改为先红后绿 |
| 切片 1：机检门 | `check-feature`：`semantic_gate.<st>.auto: <证据>` 可代替人名 `by`（证据须存在，不能与 `by` 并存）；verify-plan 要求至少一条 correctness，且每条有 `runner` 或已 PASS 带 evidence | 临时票六例红绿（缺证据 / 有证据 / 并存 / agent by / 无 runner / 无 correctness）；golden `check-feature-verify-plan` |
| 切片 2：P1/P2 密封并入拆解 | `check-feature req`：P1/P2 基线未密封时照查就绪（抽成 `check_baseline_ready`）、grill 闭合、人读规格，`semantic_gate.req-review` 延到同签；P0 与 `arch` 起仍要 `sealed` | `test/check-feature-tiers.sh` 前 5 例 |
| 切片 2：plan / resolved 按档位 | 六条配方 plan 闸加 `auto_tiers: [P1, P2]`；`verify-plan` 打印 `SIGNAL`（无 runner、非 1:1）；`record AUTO` 要证据文件有 `0 FAIL`、无 `SIGNAL`；`plan.auto` / `ops.auto` 只认 P1/P2，`ops.auto` 另要账本收敛 | golden `gate-auto-p0` / `-no-evidence` / `-dirty` / `-signal`；selfcheck AUTO 正向 31–34；tiers 脚本后 10 例 |
| 切片 2：信号补全 | `signals_of` 加 `ARTIFACT UNKNOWN` | `scripts/test_signals.py` 6 例 |
| 切片 2：一页规则 | `chat-confirm-signoff.md` 改为唯一权威页（档位表、B 类信号、决策包、A 类签字、AUTO 写法）；`hitl-risk-tiers.md` 只留原因；`invoke.md`、`SKILL.md`、`agent-brief.md`、`deliver/SKILL.md`、`gates.md`、`verify/SKILL.md`、`plan-schema.md`、`ops/SKILL.md` 改为按档位的一句 + 指针；`gates.md`「Agent 不得代勾」与代写的冲突改为「人判、人确认后代写」 | `refs-check` PASS |
| 切片 3：SQLite 端口 | `store/sqlite/repos.go`：`InTx` 让 `Store` 成为 `ports.Store`；实现 gate / audit / idempotency 三个 repo，feature 和 run 按投影行插入（run 状态 `external`，不进活跃集合）；runs / leases / delegations / baselines 返回 `errNotWired`；迁移 `00002_gate_subjects` 记 gate 绑定的文件 | `TestAGateReadsBackAsItWasAsked`（不存关键词时变红，已验证） |
| 切片 3：`cmd/idev` | `gate request|approve|reject|status`、`token init`；`approve` / `reject` / `token init` 要求 stdin+stdout 是 TTY、输入编号末 4 位、凭据 0600、`people.yaml` 白名单；按当前内容重算摘要；Ed25519 签名；策略开 `AllowLowForHigh`，降级进审计链；`adapters/local` 提供签名器、授权器、凭据、时钟、ID；数据在 `~/.idev`（`IDEV_DATA`） | `cmd/idev` 11 例（无 TTY、短码错、白名单外与模型名、批准后改内容、含糊原话、驳回语、重复作答、P1 密封绑 baseline+req 并标降级、凭据发放、一步一问、审计链校验与批准不可改） |
| 切片 3：`workflow.py` 接 CLI | 新增 `ask`；Go 引擎下 `record <gate> PASS` 拒 `--by` / `--quote`，读回批准（approved、摘要一致、签名可验）后写 `signoff.approval_id`；`IDEV_ENGINE=python` 回退；`with.gate_type` / `with.subject` 校验 | `test/gate-channel.sh` 14 例；selfcheck 新锁「a gate is answered from the person's terminal」；legacy golden 与 selfcheck 驱动段固定 `IDEV_ENGINE=python` |
| 切片 3：lease | `idev lease acquire|release|check`：acquire 先把 `run.yaml` 投影进 SQLite（features / runs 状态 `external` / steps；未收口且有 `delegated.agent` 的步骤投影为 `delegated`），先 Sweep 再 `leasesvc.Acquire` 写租约；`workflow.py delegate` 按 `arch.yaml` 的 include 路径领租约；Go 引擎下 `lease: write` 的步骤无租约记 `PASS` → BLOCKED，`CHANGED` 越界 → BLOCKED；`record` 收口与 `abort` 释放；feature 标识取票目录绝对路径（两个 checkout 的同名票不相撞，gate 同用） | `TestLeasesFollowTheProjectedRunAndHoldOneWriter`（时间戳用 RFC3339Nano 时 Sweep 回收 0 条，已验证变红）；`test/lease-channel.sh` 13 例；selfcheck 锁改为「gate and lease channels」 |
| 切片 3：Go `AUTO` | `run.StepAUTO` 计入已完成；`recordable()` 让 E5 / E7 / E14 拒收 AUTO 作结果（只有驱动在机检通过后记它） | `TestNoEventSetsAUTO`（红先绿后） |
| 切片 3：时间戳 | SQLite 时间戳改定宽 `2006-01-02T15:04:05.000000000Z`：RFC3339Nano 去尾零，整秒时刻按字符串比大小会错，过期租约扫不到 | 同上 lease 单测 |
| 切片 3：与计划的偏差 | 保留 `step_confirm`（`git push`、回填确认等配方闸确认的是动作，不是字段）；不加 `decision` 类型（B 类答复已在 `decisions.yaml`，Go 侧没有使用方）；只接写租约，验证租约未接；deliver 阶段签字尚未强制 `approval_id`（用户定：先不要） | — |
| 切片 3：发现的不一致（未修） | registry 给 verify 类 kind 的 `lease: verify` 在委派时就要，`leasesvc` 只在步骤处于 `verifying` 时发验证租约，两边时机不一致；`runsvc` 的委派路径从不自己 acquire 租约（测试靠 `issueLease` 预置），租约现在只经 CLI 领 | — |
| 切片 3 全量 | — | golden 50/50、`go test ./...`、`go vet`、`selfcheck.sh`、`agent-smoke` PASS、lite-change / late-lifecycle / tiers / gate-channel / lease-channel 冒烟、`test_signoff` / `test_signals` / `test_concurrency`、agents-check、gen-kinds、refs-check、workflow-check 全 PASS |
| 切片 2 全量 | — | golden 50/50、`go test ./...`、`selfcheck.sh`（含新锁「signoffs follow the risk tier」）、`agent-smoke` 481/0、各冒烟全 PASS |
| 切片 1 全量 | — | golden 47/47、`go test ./...`、`selfcheck.sh`、`agent-smoke` 481/0、`test_signoff` 12、`test_concurrency` 6、lite-change / late-lifecycle smoke 全 PASS |
