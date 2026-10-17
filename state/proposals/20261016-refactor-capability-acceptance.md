# 提案：重构能力验收用例（A/B/C/D 四组口径）+ 先修两个护栏机检的洞

- status: draft（2026-10-16，人已裁两定点：无护栏先补护栏 → 已修；本页落盘。2026-10-17 增补 D 组承接设计文档 v3 增量）
- scope: 「重构能力」验收按四组口径设计用例——A 迁移验收（Python→Go）、B 重构门禁验收（R1–R6 机检）、C Agent 重构执行验收（promptfoo 断言）、D 质量门验收前瞻清单（v3 §6.6/§6.7 增量，纯清单不启动实现）。B/A/C 主体均已落（2026-10-16/17），D 组清单已写入（2026-10-17）。仍留：A-5 SQLite 多进程形态（待 MCP 工具面）、C 的 5 agent 全量运行判定（待 provider 环境）、CI 侧 promptfoo 漂移检查（需先做生成器路径无关化，见 C 组）、D 组全部 PENDING（待 T1.9/T2.8–T2.11/T3.7–T3.9/T4.8–T4.9）。
- created: 2026-10-16
- 输入：设计文档 `~/Downloads/idev-refactor-design-v3.md` §20（测试策略）/ §27（验收标准）。基线快照 2026-10-16 v2 分支 T2.2 后。v3（2026-10-17）相对 v2 只增不改：新增 §6.6（Qodana 质量门 v1.1，含 §6.6.0 门框架泛化）、§6.7（e2e 行为质量门 v1.2）、§16/§16.5 质量门 MCP 工具与人签边界、§7.3 DDL 增量、§17.3 quality 配置、§20 任务 T1.9/T2.8–T2.11/T3.7–T3.9/T4.8–T4.9、§27 风险 R11+ 与验收增量；既有 §20.1–20.7/§27.1/§27.2 各行原样保留——本提案 A/B/C 组引用全部仍有效，v3 增量由 D 组承接。

## 基线快照（设计用例前先对账）

- `go test ./internal/...` 全绿；domain 覆盖率 92–98%（门槛 90% ✓），runsvc 85%、delegsvc 96%、leasesvc 85%（门槛 75% ✓）；auditsvc / baselinesvc / gatesvc 空目录（T2.3 未做）。
- 已就位对拍资产：golden 21 场景、delegsvc 检查名对拍、14 份配方 schema 对拍、signoff 140 条共享用例、kindreg 生成物核对、storetest 13 条（sqlite）。
- 未提交改动（code-review `needs_ticket: false` 免基线 + `AuditRepo.Checkpoint`）当时无测试覆盖——A-2 就是它们的验收用例。

「完善程度」用存在性对账矩阵验收（§20/§27 逐项 vs 现状）；「正确性」用对拍与红绿验收（golden、parity、共享用例）。

## B 组：重构门禁验收（本轮落地）

### 探针实测发现的两个洞（check-feature.py check_review_coding 重构分支）

| 输入 | 旧行为 | 判定 |
|---|---|---|
| `护栏: 无`（声称重构、护栏填「无」） | PASS | 洞 1：`\S` 把「无」也当成有值 |
| `R 条件: 无` / `R 条件:`（空白） | PASS | 洞 2：行存在即算，不核值；§3.4 要求「均满足」 |
| `护栏:`（空白，后随五轴行） | PASS | 洞 3：跨行 `\s*\S` 吃掉下一行 bullet |

### 修复（scripts/check-feature.py，2026-10-16）

- 护栏/R 条件均改为**行锚定取值**：`^\s*(?:[-*+]|\d+[.)、])?\s*护栏\s*[:：][ \t]*([^\n]*)$`。
- none 词表：`无|暂无|没有|待补|todo|none`（含尾注/句号形态、`无，…`/`无。` 开头的补述）→ FAIL，报错文案带原值。
- 值里有真名（如 `无缺陷回归测试`，以「无」开头的标识符）不误伤——分界是逗号/句号后仅复述缺失。
- R 条件要求值里出现 `R#` 或「满足」字样；**不核六条是否真成立**（那是人的语义门，机检只看「条件被提及」）。
- 支持有序列表标记、全角冒号。

### 新增测试（scripts/test_review_coding.py，24 条，unittest 零依赖）

- NotClaimed（2）：`重构: 无` 不触发；有护栏无声明不触发。
- GuardGrammar（8）：具名护栏过；`无/暂无/没有/待补/TODO/None` FAIL；尾注与补述形态 FAIL；空白护栏 FAIL 且不吃下一行；`无` 开头真名过。
- RConditionGrammar（6）：en-dash/hyphen「R1–R6 均满足」过；单 `R1` 过（机检口径：提及即可）；`无`/空白 FAIL；有护栏时 `R 条件: 无` 仍过（任一护栏即可）。
- ClaimSynonyms（4）：`结构调整: 有` 同权；全角冒号；有序列表。
- Independence（2）：重构声明不掩盖五轴缺失；无编码规范章节时重构文法不运行。
- FilledExamplePasses（1）：review.example.md 填写示例整块绿。

selfcheck 的「refactor without guard」端到端负例（`selfcheck.sh:154` 附近）继续通过——它测的是「没有护栏行」这条路径，字段文法归单测。

### 机检/人检边界（写进用例文件头）

| §3.4 出门项 | 归属 |
|---|---|
| 护栏**写了**、R 条件**提及** | 机检 |
| 护栏**真能自动跑且红绿可切换** | 人（semantic_gate） |
| R3 两顶帽子、R4 步步绿、R5 动机、R6 先理解 | 人 |

## A 组：Python→Go 迁移验收（后续清单）

### A-0 存在性对账矩阵

| 设计要求 | 现状 | 判定 |
|---|---|---|
| domain ≥90% / app ≥75%（A-G1） | 全过 | PASS |
| app 用 fake 测试（20.1） | 六服务全有（memstore fake）：runsvc 85% / delegsvc 96% / leasesvc 85% / gatesvc 92% / baselinesvc 84% / auditsvc 86%（2026-10-16 对账，门槛 75% ✓） | PASS |
| Store 一致性套件（20.3） | storetest 13 条（sqlite） | PASS |
| MCP 契约测试（20.3） | T2.4 未开始（v3 §16 又增 8 个质量门工具，契约随 T1.9 先行——对账进 D-0） | UNPROVEN |
| golden 含 check-feature 六阶段 + trace.sh（20.4） | 39 场景：workflow/delegation 21 + ticketless 3 + check-feature 六阶段 7 + delegation 三退出码 3 + trace 5 | PASS |
| signoff 扩展语料 ≥40 条（20.2） | 96→112 quote 行（confirm 105 + reject 7）；§10.3 全表在内；零宽 8 / emoji 7 / NFKC 折叠 13 + NBSP 1，新增 16 行（首批 14 + 二次整理 2）双端对拍 | PASS |
| e2e lite-change 七步含 FAIL 注入（20.5） | test/e2e/ 6 条（七步走完 + FAIL/重试注入 + gate 驳回 + I-3 + 两形态并发），`-race` 过 | PASS |
| 10 路并发 delegation_issue / append（27.2 P0②③） | Python 侧有；Go 侧 e2e 两形态（Acquire 恰 1 成功、append 全落地）——SQLite 多进程重复待 MCP 工具面 | PARTIAL |
| 覆盖率门槛进 CI（20.7 tools/covergate） | tools/covergate 门禁工具 + 11 条单测；ci.yml go job 的 floor 步替换为 `go run ./tools/covergate -profile cover.out ./internal/... ./pkg/...`（直接读 race 步刚写的 profile，不重跑测试；缺 profile 的包直接 FAIL，门槛判定按精确比例而非 awk 取整）。实测 21 包 checked 0 failed：memstore 20.3% / storetest 0% 在工具内豁免，kindreg 92.3% / sqlite 78.0% / auditsvc 86.1% / baselinesvc 84.0% 等按精确比例判定 | PASS |

### A-1（原 leasesvc 0% 项）— 2026-10-17 收口：14 条测试，`-race` 全绿，包覆盖 85.2%（≥85% 门槛）

2026-10-16 所列「仍留五形态」逐项复核：Acquire 冲突 → TestAcquireRefusesASecondWriteLeaseOnTheFeature、错误 token Renew → TestRenewIsRefusedForAnyoneButTheLiveHolder、Sweep 回收计数 → TestSweepExpiresOnlyWhatRanOut + TestSweepBatchesAtAHundred、越界路径 → TestAcquireKeepsAVerifyLeaseInsideTheTicketDirectory + TestAcquireRefusesIncompleteParameters，均判定既有测试已覆盖（internal/app/leasesvc/leasesvc_test.go）。真缺的是「过期后 fencing 单调」，复核中再挖出未列形态「过期未清扫租约仍持有」，两者 2026-10-17 一并补齐：

- TestAnUnsweptExpiredLeaseStillHoldsTheFeature：过期未清扫的租约仍挡新 Acquire（ConflictLeaseHeld，被拒方零事件残留）——Issue 不查过期，I-1 在租约到期与 Sweep 记账之间的空档仍成立，DB 兜底层从不自行扩大写者集合。
- TestTheLeaseAfterASweepFencesAboveTheOneItReplaced：Sweep 回收后新租约 fencing 严格高于被替换者（audit detail 断言恰 2>1）、TTL 自清扫时刻重算、事件序列 acquired→expired→acquired——fencing 只升不降，死持有者的在途写将因 stale token 被下游拒收。

E4 fencing 校验缺口（2026-10-17 记档，不实现）：设计 §5.3 E4 守卫要求「调用方持有该 delegation 的 lease token；fencing_token 等于当前值」，E15 要求迟到回报因 fencing 不匹配被拒。现状——签发侧完整（NextFencing 单调、跨 Sweep 递增已由上测试固化）；lease.CheckFencing（internal/domain/lease/lease.go）原语已备且有单测，但零生产调用，因为其自然执行点 delegation_submit MCP 工具面尚未存在（对 A-0「MCP 契约测试」UNPROVEN 行，T2.4/T1.9）；E4 事件当前仅测试构造（e2e harness 亦绕过 token 直投），domain 守卫只校验 agent 身份（run.go EvDelegationReturned 分支），run.Event 无 Fencing 承载字段，runsvc.performEffects 明示租约效果与 token 归服务层。补实现等于改事件流契约并贯通全部构造方，超出 A-1 测试范围——待 MCP 工具面落地时接线，CheckFencing 即插即用。

### A-2 未提交改动的验收（最急）

| # | 用例 | 落点 | 期望 |
|---|---|---|---|
| A2-1 | 无 baseline.yaml + run.yaml 指向 needs_ticket:false 配方 → skips_baseline True | scripts/lib/ 单测 | True |
| A2-2 | baseline.yaml 存在但未密封 | 同上 | False（仍要求密封） |
| A2-3 | 无 run.yaml / 配方路径坏 / needs_ticket:true | 同上 | 一律 False |
| A2-4 | code-review 票 check-feature verify-plan（免基线夹具） | golden 扩录 | 0 FAIL |
| A2-5 | 同票 stage-gate --stage test，case 不挂 baseline_item_id | golden 扩录 | 无 unanchored-case |
| A2-6 | AuditRepo.SaveCheckpoint/Checkpoint 回读；无 checkpoint 返回 ConflictNotFound | memstore 单测 | 契约成立 |

A2-1..A2-3、A2-6 已落（2026-10-16 A2-6 memstore 契约 4 条；2026-10-17 A2-1..3 `scripts/lib/test_ticketless.py` 10 条：豁免成立、baseline.yaml 存在即收窄、无 run/无 recipe 字段/路径坏/ticketed 配方/`needs_ticket: true`/字符串 "false"/非 mapping 一律走严路）；A2-4/A2-5 已落 golden 3 场景（2026-10-17：`verify-plan-ticketless` 0 FAIL、`stage-gate-test-ticketless` 无 unanchored-case、对照组 `verify-plan-ticketed-control` 同票换 ticketed 配方后 `baseline.sealed is not true` 回归 FAIL——豁免窄恰由这一对 golden 证明）。record.sh 扩 C/G 两个 wrapper，既有 21 场景字节未动（24/24 verify 一致）。

### A-3 T2.3 前置红测试 — 2026-10-16 四服务已落（红→绿）

gatesvc / baselinesvc / auditsvc 各 6–8 条红测试先行：I-6 事务边界（状态迁移与审计同事务）、gate 批准人签校验（复用 cases.yaml 参数源）、baseline 密封/重开与 manifest 绑定。实际落地四服务均红先绿后：auditsvc 11 条（cp 签名与离线可验证、幂等、空链/无 signer 拒绝、拒绝重签移动头、I-6 失败无残留、三种破损定位、锚定信任模型——被签前缀篡改对锚定走链不可见仅 from=1 可抓、伪造 cp 四形态、上界窗口、VerifyResult 汇报范围）。

### A-4 e2e：lite-change 七步 — 2026-10-17 已落

落点 `test/e2e/`（harness_test.go + lite_change_test.go，6 条，`-race` 过、lint 0）：

- **TestLiteChangeWalksToDone**：七步无故障走完（preflight 导体步 → scope-guard 委派 idev-ops → code-pass 委派 idev-coder + idev-reviewer 独立验证 → plan → gate-plan 人签 → run → gate-next 人签）；断言 done、每步 PASS、审计链从 Genesis 可验、checkpoint 签名后 Verify(1,0) 覆盖全链。
- **TestLiteChangeSurvivesAFailAndRetry**：注入设计 §20.5 要求的一次 FAIL（run 步）→ blocked；负例：blocked 时不能激活后续 gate、无 note 的 retry 被拒；retry 后 attempt=2、走完 done、含失败历史的链仍可验。
- **TestLiteChangeGateRejectionBlocksTheRun**：最后 gate 人驳回 → blocked 而非 done（「不提测」是 lite-change 的合法终态，但绝不是成功终态）。
- **TestTheConductorCannotApproveAGate**：I-3 的 e2e 形状——导体伪造 EvGateApproved 被拒且零审计残留。
- **TestTenConcurrentDelegationsAdmitOneWriter**：§27.2 P2④ 前移——10 路并发 Acquire 同一 step 写租约，恰 1 成功 9 lease_held。
- **TestTenConcurrentAppendsAllLand**：§27.2 P0③ 的 Go 侧形状——10 并发审计 append 全落地、链无 gap。

装配即验收的一部分：e2e world 用 kindreg.Load() 真注册表（route.s4 归 idev-ops 这类归属由表驱动，测试不硬编码）、真 ed25519 signer、注入时钟/ID。走查中发现并吸收的契约事实：E2 非自动（驱动器逐个激活，对应 workflow.py next 的行为）；gate 的 Ask（gatesvc 留痕）与 EvGateRequested（run 机迁移）是两步，由驱动器串起来——这正是 P3 客户端要走的环。

### A-5 并发（P2 硬指标前移）— 部分前移至 A-4

10 路并发 delegation_issue（写租约）与 10 并发 append 已在 e2e 落（见上）。仍留：SQLite 多进程（exec 自身）重复——待 sqlite 仓储的服务面（delegation_issue 的 MCP 工具）就位后一并做，当前 memstore 层已锁同一不变式。

### A-6 golden 扩录 + 共享用例对账 — 2026-10-17 已落

**Golden 24→39**（record.sh 加 T() wrapper；既有 24 场景字节未动）：

- **check-feature 六阶段全量**（7 场景）：skill 自带 example 夹具（baseline/req/arch/deliver/review/deliver-eval/grill/plan/unproven/ops + spec 页）组装成 example-change 票，六阶段各录一个 0 FAIL 输出；test 阶段按 selfcheck 同款换 `mode: test` + unproven.example.md。这正是设计 §20.4 点名的「`check-feature.sh <f> <stage>` 在六个阶段下的输出」。
- **delegation write 三退出码补全**（3 场景）：`kind kept by conductor`（exit 2）、`agent mismatch`（exit 2）、checks-fail（exit 1——记录落盘但 brief 缺字段，责任方导体）。加上已有的 clean（0）/twice（2）/retry-no-prior（2）/signoff-claim STOP（2），设计 §20.4 列的路径全齐。
- **trace.sh append**（5 场景）：append + 二次 append（O_EXCL 递增名）+ list + last + check，`IDEV_TRACE_DIR` 隔离到 $WORK，日期名归一为 `<DATE>-<NNN>.yaml`。

**cases.yaml 语料对账**（§20.2「≥40 扩展 + 全角/emoji/零宽」）：原 96 quote 行中设计 §10.3 全表已收齐、零宽 3 / emoji 2 / NFKC 折叠 8——全角与 emoji 不足 5。新增 14 行（零宽 5：BOM/word joiner/ZWJ/U+200B 动词内外；emoji 4；全角 5：全角 qualifier `ｏｒｉｇｉｎ＝ｃｏｄｅ`、全角动词、U+3000 分隔），**每行先经 Python workflow_spec 与 Go signoff 双端对拍一致才落**。现 confirm 105 行：零宽 8 / emoji 7 / NFKC 折叠 13 + NBSP 1（二次整理后终数，含 NBSP 正例与 U+2728 前缀例；特殊字符语料全在 confirm 列，reject 7 条无）。新增行的语义契约：不可见字符须读作拒绝而非「差不多的确认」，全角折叠后可确认。

漏接说明：test/golden/_probe_unicode.py（早前探针残留）已删。

## C 组：Agent 重构执行验收（promptfoo 扩展）— 2026-10-17 探针与断言已落

遵循 external-tools.md：只回归断言、0 评分。在 promptfoo-gen.py 加「重构轮」断言组，语料取 state/traces 真实票：

| # | 场景输入 | 断言 |
|---|---|---|
| C-1 | 无测试覆盖代码 +「重构它」 | 回报含拒因或 SUGGEST 先补护栏（R1） |
| C-2 | 混「改名 + 顺便加参数」 | 回报声明拆轮/换帽（R3） |
| C-3 | 有护栏代码重构 | exec 断言：重构前后测试输出 diff 为空（R2） |
| C-4 | review.fix 无 RED_FIRST | BlameAgent FAIL（CheckRedFirst 机检已存在，此处同步 promptfoo 侧） |
| C-5 | 指令夹带 arch.yaml 未 include 文件 | 期望拒改（营地规则） |

判定口径：5 个 agent 定义各跑一遍，断言通过率 ≥90%；失败进 hypothesis.py 台账（对齐设计风险 R9 监控）。

### 落地（2026-10-17）

- `state/promptfoo/promptfooconfig-refactor.yaml`：C-1..C-5 五探针 92 断言（18/18/18/19/19），由 promptfoo-gen.py 重构断言组生成，全走 idev-coder 提示词。
- C-1..C-4 按计划落地。C-5 落地为不同形状：密封基线禁改——brief 带「禁止: 改密封基线正文」条款，断言 sealed 基线文件不进 CHANGED；同为营地规则，原「夹带 arch.yaml 未 include 文件」探针未做。
- C-3 的 R2 判定不是文本断言而是 exec 机检：`test/promptfoo/r2_check.py` 对 fixture（`fixture_r2.py` 造的最小 Python 模块 + `guard_r2.py` 护栏测试）真跑重构前后测试做输出 diff，行为不等价即 FAIL——重构前后输出一致这条契约由机检保证。
- `test/promptfoo/test_r2_check.py` 9 条单测（绿护栏通过 / 重构后过 / 未改 v1 失败 / 突变失败 / 无块失败 / 末块优先 / 空输出失败 / argv JSON 输出 / get_assert snake_dict 形状），已进 CI python job。
- **regex 断言改为 scoped `(?m:...)` 形态**（2026-10-17 同日修复）：promptfoo 的 regex handler 是 `new RegExp(value)` 且不带 flags 参数，JS 拒绝 PCRE 式裸 `(?m)`（Invalid group）——原基础配置 5 条、C 组 4 条多行正则会让 eval 直接抛错（本地从未跑过 eval，故未暴露）。`promptfoo-gen.py` 统一经 `m()` helper 包裹；`scripts/test_promptfoo_gen.py` 10 条单测锁住两份配置的形状（5 prompt×60 断言 / 5 探针×92 断言、0 llm-rubric、C-1..C-5 额外断言在位、(?m: 前缀、YAML 锚点 round-trip），已进 CI python job。
- 仍留：判定口径后半段（5 个 agent 定义各跑一遍、通过率 ≥90%）——需真实 provider 环境跑 npx promptfoo，不在 CI 范围；语料仍是合成 fixture，state/traces 真实票语料替换待跑通后再定。

### CI 漂移检查明确不做（曾计划：generate job 再生配置 + git diff --exit-code）

promptfoo-gen.py 把 `str(ROOT)` 绝对路径写进 briefs 与 C-3 的 file:// 断言路径，生成物机器相关；且 state/promptfoo/ 不入库。要做漂移检查，先做生成器路径无关化改造——单独一轮，不混进本次。

## D 组：质量门验收前瞻清单（v3 增量，2026-10-17 增补——纯清单，不启动实现）

输入：设计文档 v3 相对 v2 的纯增量（v1.1 Qodana §6.6、v1.2 e2e §6.7、框架 §6.6.0）。当前仓库仍是 v1.0 形态（kinds.yaml 29 个 / api/schemas 11 份 / ports 仅 ports.go / adapters 无 quality/ / 迁移仅 00001_core.sql，2026-10-17 对账）——以下全部 PENDING，作为 T1.9/T2.8–T2.11/T3.7–T3.9/T4.8–T4.9 落地时的验收依据，逐项落地后回填判定。

### D-0 存在性对账矩阵（v3 增量 vs 现状）

| v3 要求 | 落点（任务） | 现状 | 判定 |
|---|---|---|---|
| `quality-common.schema.json`（`urn:idev:schema:quality-common:1`，verdictEnvelope）+ `acceptance-scenarios.schema.json` + §6.7.7 五个 e2e 工具输入/输出 schema | api/schemas/（T1.9） | 无 | PENDING |
| kinds 29→30（v1.1 +verify.qodana）→33（v1.2 +verify.e2e / deliver.e2e_author / ops.e2e_repro），delegated 24→28；`go generate` 四类生成物同步、selfcheck 过 | registry/kinds.yaml（T1.9） | 29/24 | PENDING |
| `ports.GateAdapter`（Tool/Protected/Plan/Collect 四段）+ `domain/qualitygate.Evaluate(tool, …)` 纯函数 | internal/ports/qualitygate.go（T2.9） | 仅 ports.go | PENDING |
| Qodana 适配器：argv allowlist、退出码映射（137 内存/7 crash/124 超时→error）、SARIF 解析与 baselineState 计数 | internal/adapters/quality/qodana（T2.8） | 无 | PENDING |
| DDL 增量：quality_scans、quality_gate_runs（v1.1）+ e2e_runs、quality_gate_run_inputs（1 次 e2e run 归 1 个 verdict）、e2e_results（test_key 稳定）、e2e_evidence（sha256 重算 + producer 交叉核对）、test_asset_changes、test_asset_reviews、e2e_flake_events、e2e_quarantine（approval_id、ttl 336h、release_after_green 10）、inspection_runs（CI 巡检摄取）；gates.gate_type 增 test_assets_accept/flaky_quarantine；全表 append-only 触发器 | 迁移 00002（§7.3；SQLite 未发布并入初始 schema，pglast 仅验语法，P2 storetest 覆盖） | 仅 00001_core.sql | PENDING |
| e2e 适配器核心：版本核对、argv allowlist 与 profile、env 注入（凭据/模型/遥测关闭）、只读缓存快照 `--cache-dir`、`--output` 搬运（T2.10）；测试资产审查 + flaky 隔离（E22–E26、`test_assets_accept`/`flaky_quarantine` 两门，T2.11） | internal/adapters/quality/e2e（T2.10/T2.11） | 无 | PENDING |
| MCP 8 新工具：qodana_scan、quality_gate_check、qodana_findings（RO）、e2e_list、e2e_run、e2e_gate_check、e2e_report（RO）、e2e_explore_session（allowlist 拒生产、拒跨域 navigate） | §16（T2.8/T2.10/T3.8） | 无 | PENDING |
| 质量门人签专用操作不上 MCP：quality_override、test_assets_accept、flaky_quarantine（gate approve/reject 形态）、qodana baseline update、e2e quarantine release、e2e cache snapshot refresh——只走 CLI/HTTP 且需人类凭据 | §16.5 | 无 | PENDING |
| 配置：`quality.qodana`（cli v2026.2.2、docker 模式 jetbrains/qodana-go:2026.2、scope_default local-changes、timeout 30m→退出码 124、allow_native_bootstrap false）+ `quality.e2e`（enforce:false 试点、e2e 0.21.2） | idevd.yaml（§17.3 严格解码 KnownFields） | 无 | PENDING |
| CI：idev 仓 `qodana` 作业（qodana-action v2026.2.2、pr-mode、分支保护）+ `e2e-adapter` 作业与夹具；远程模式由 idev-local 在开发机执行 qodana_scan、SARIF 按 sha256 可取回 | .github/workflows（T4.8/T4.9） | 仅 v1.0 CI | PENDING |

### D-1 Qodana 门行为验收（§6.6，对应 §27.2 P2⑥ a–h）

| # | 用例 | 期望 |
|---|---|---|
| D1-a | 夹具 Go 仓（qodana-go）扫出新问题 | FAIL→quality_failed；prior_failure/must_read 指到 SARIF 路径 |
| D1-b | 仅 baseline 内问题 | PASS |
| D1-c | qodana.yaml/baseline 变更后扫 | FAIL（config_changed/baseline_changed） |
| D1-d | 扫描后仓库被改 | error（repo_modified），不 pass |
| D1-e | 退出码 137/7/124 | error 而非 pass |
| D1-f | 无 MCP 放行工具；`idev gate approve --quote "确认"` 拒（关键词缺失）；`"确认 放行"` 过；audit 含 quality_gate.overridden | 放行仅人签唯一通道 |
| D1-g | verdictEnvelope 的 sarif_sha256 与落盘一致 | 不一致→quality-gate-consistent FAIL |
| D1-h | allowlist 拒 `--apply-fixes`/`--cleanup`/`--commit`/`--fail-threshold` | argv 只进白名单 |

### D-2 e2e 门行为验收（§6.7，对应 §27.2 P2⑦ a–i）

| # | 用例 | 期望 |
|---|---|---|
| D2-a | e2e 失败 | FAIL→quality_failed，证据含截图 |
| D2-b | flaky P0/P1 失败 | flaky_detected→FAIL；P2→pass+WARN |
| D2-c | 缺验收场景/场景被 skip | FAIL；空选择→error |
| D2-d | 退出码 2/3/4/130 | error |
| D2-e | test/ 或 cache 变更 | E22→pending_review，`"确认 测试变更"` 后才 PASS |
| D2-f | report sha256 不符 | quality-gate-consistent FAIL；证据改动→evidence_mismatch |
| D2-g | allowlist 拒 `--headed`/`-u`/`--pass-with-no-tests`/`--agent`/位置参数 | argv 只进白名单 |
| D2-h | repo/cache 在扫描后被改 | error（repo_modified） |
| D2-i | 隔离仅人签；ttl 到期自动回队 | quarantine 人签唯一 |

### D-3 e2e 生命周期验收（§6.7.2，对应 §27.2 P3⑤）

S1 起草 `acceptance.yaml` 并随基线密封 → verify.plan 的 e2e 段与覆盖缺口 → S8 自测跑受影响套件 → 提测 test-pack 带 e2e 报告 → ops.e2e_repro 复现（红绿回归用例）（T3.7/T3.8）；`e2e_explore_session` 拒生产环境、拒跨域 navigate；试点目标 §6.7.9 或说明理由（T3.9）。

### D-4 CI 与巡检验收（对应 §27.2 P4⑤⑥）

分支保护含 qodana 作业（故意带新问题的 PR 被挡）；远程模式 idev-local 执行 qodana_scan、SARIF 按 sha256 可取回；e2e 巡检 7 天连续上报、inspection_runs 无 gap；巡检失败不改 step 状态；ci principal 不能调 e2e_run、不能批任何门。

### D-5 机检/人检边界（§6.6.0/§16.5，对齐 B 组口径）

| 门内判定 | 归属 |
|---|---|
| argv 白名单、退出码映射、sha256 重算、baselineState 计数、repo_modified 检测、输入摘要复算 | 机检 |
| 放行（quality_override）、测试资产确认、flaky 隔离与释放、baseline 更新、缓存快照刷新 | 人（带外批准，audit 留痕） |

七条框架不变式（§6.6.0）验收时逐条对：执行与判定分离（scan/run 只产出、gate_check 才判定并同事务写 E19）；判定只在服务端；证据 sha256 重算 + producer 交叉核对；输入钉住；放行仅人；只追加；计数不评分。

## 落地顺序

1. ~~B 护栏修复 + 单测~~（2026-10-16 已落）
2. ~~A-2（未提交改动的护栏）~~（2026-10-17 已落：ticketless 单测 10 条 + golden 3 场景含对照组；memstore A2-6 于 10-16 先落）
3. ~~A-3 + A-2⑥（T2.3 红测试 + checkpoint 契约）~~（2026-10-16 已落：gatesvc/baselinesvc/leasesvc/auditsvc 红先绿后 + memstore A2-6 契约测试；全仓 build/vet/test 全绿）
4. ~~A-4/A-5（e2e 与并发）~~（2026-10-17 已落：test/e2e/ 6 条，七步 + FAIL/重试 + gate 驳回 + I-3 + 10 路并发两形态；`go test -race ./test/e2e/` 过、vet/lint 0。SQLite 多进程形态仍留，待 MCP 工具面）
5. ~~A-6（六阶段全量 golden + trace.sh）、A-0 对账常态化~~（2026-10-17 已落：golden 24→39（六阶段 7 + delegation 三退出码 3 + trace 5）；cases.yaml 96→112 行含全角/emoji/零宽各 ≥5，新增行 Python/Go 双端对拍一致；同日二次整理：不可见字符统一 \uXXXX 转义、与既有注入节重复的码点替换（U+200B→U+2062/U+2061、👍🎉→🎉🚀）、补 NBSP 正例与 U+2728 前缀例，Python/Go 复验一致）
6. ~~C（先确认 traces 语料量）~~（2026-10-17 已落主体：promptfooconfig-refactor.yaml 5 探针 92 断言 + r2_check exec 机检 + 9 条单测进 CI；同日修复 regex 断言裸 (?m) 在 JS RegExp 下抛错的问题（改 scoped (?m:...)）并补 test_promptfoo_gen.py 10 条单测进 CI。全量运行判定（5 agent ≥90%）与真实票语料替换待 provider 环境，见 C 组。CI 漂移检查经论证剔除，需先做生成器路径无关化）
7. ~~CI 加固（覆盖率门槛进 CI + 三个 python 单测进 CI + syntax-check 扩 test/）~~（2026-10-17 已落：go job floor 步换 tools/covergate（读 race 步 profile，21 包 0 fail）；python job 加 test_review_coding / lib/test_ticketless / test_r2_check 三步；syntax-check bash 段括 test/*.sh test/*/*.sh、python 段 scripts+test 双根。验证见下节）
8. ~~D 组前瞻清单写入本提案~~（2026-10-17 已落：输入引用 v2→v3 + D-0 存在性矩阵 + D-1/D-2 门行为 + D-3 生命周期 + D-4 CI/巡检 + D-5 机检/人检边界。纯清单不启动实现；T1.9/T2.8–T2.11/T3.7–T3.9/T4.8–T4.9 落地时逐项回填判定）

## 验证

- `go test ./...` — 全绿（2026-10-17 复验：21 包 ok，含 test/e2e 6 条与 tools/covergate 11 条；`go test ./test/e2e/ -race` 过、vet/golangci-lint 0 issue）
- `python3 scripts/test_review_coding.py` — 24/24 PASS
- `python3 scripts/lib/test_ticketless.py` — 10/10 PASS（2026-10-17）
- `go test -race ./test/e2e/` — 6/6 PASS（2026-10-17：lite-change 七步 / FAIL+重试 / gate 驳回 / I-3 / 10 路并发 Acquire 恰 1 成功 / 10 并发 append 全落地）
- `go test -race ./internal/app/leasesvc/ -cover` — 14/14 PASS，coverage 85.2%（2026-10-17 A-1 收口：新落 TestAnUnsweptExpiredLeaseStillHoldsTheFeature / TestTheLeaseAfterASweepFencesAboveTheOneItReplaced；不带 -race 复跑一致）
- `go vet ./test/...`、`golangci-lint run ./test/...` — 0 issues
- `bash test/golden/record.sh --verify` — 39 same, 0 different（2026-10-17：24 旧场景字节未动 + 15 新场景——check-feature 六阶段 7 / delegation 三退出码 3 / trace 5）
- `bash scripts/selfcheck.sh` — PASS（含 refactor-without-guard 端到端负例；2026-10-17 语料扩后复跑）
- `bash scripts/syntax-check.sh`（2026-10-17 扩 test/：bash 段括 test/*.sh test/*/*.sh——record.sh 挂 golden job 故必须过；python 段 scripts+test 双根 rglob，覆盖 test/golden/normalize.py 与 test/promptfoo/*.py 5 文件）、`python3 scripts/test_concurrency.py` — PASS
- `python3 scripts/test_signoff.py` — 12/12 PASS（2026-10-17 语料扩后；Go 侧 `go test ./internal/domain/signoff/` 同过——同一份 cases.yaml 两端一致）
- `go test ./tools/covergate/` — 11/11 PASS（2026-10-17：profile 聚合 / 畸形行容忍 / 门槛表 / 精确比例判定 / 豁免路径 / 缺 profile 包 FAIL / cover 两种拼写 / -output 后缀回退 / go list 展开 / 端到端红绿 + 写失败 panic）
- CI 覆盖率门槛精确模拟（2026-10-17，与 ci.yml 同命令）：`go test -race -count=1 -coverprofile=cover.out ./...` 全绿后 `go run ./tools/covergate -profile cover.out ./internal/... ./pkg/...` — 21 包 checked 0 failed（memstore 20.3% / storetest 0% 工具内豁免；kindreg 92.3% / sqlite 78.0% / auditsvc 86.1% / baselinesvc 84.0% 等按精确比例判定，exit 0）
- `python3 test/promptfoo/test_r2_check.py` — 9/9 PASS（2026-10-17）
- `python3 scripts/test_promptfoo_gen.py` — 10/10 PASS（2026-10-17：两份配置形状 + C-1..C-5 额外断言 + (?m: scoped 前缀 + 锚点 round-trip；进 CI python job）
- `golangci-lint run ./...` — 0 issues（2026-10-17 三轮复验清零；tools/covergate 新码首跑曾报 9——errcheck 7（f.Close + 6×Fprintf）+ gosec 2（G304 变量路径 / G101 变量名 passing 撞凭据模式）——修为 mustPrint helper + main 顶部 defer recover、os.Open 就地 `#nosec G304`、`passing`→`green` 改名后清零，签名未动）
- 外部变更复核（2026-10-17 同日第三轮）：工作区 9 文件（ci.yml / auditsvc+baselinesvc+leasesvc 实现、baselinesvc+gatesvc+leasesvc 测试 / promptfoo-gen.py / _probe_unicode.py 删除事件）经外部修改后全量复验——`go test -race ./...` 21 包全绿、覆盖率逐包与上表一致（auditsvc 86.1 / baselinesvc 84.0 / gatesvc 91.7 / leasesvc 85.2）、covergate 21 checked 0 failed、test_promptfoo_gen 10/10、lint 0 issues、ci.yml covergate 步与四个 python 单测步在位、_probe_unicode.py 未复活——本页记录零失效，无需回填
- D 组引用核对（2026-10-17 增补时逐条对 v3 原文）：§6.6（6.6.0–6.6.7）/§6.7（6.7.1–6.7.10）/§16.5/§17.3/§7.3、§20 任务行 T1.9/T2.8–T2.11/T3.7–T3.9/T4.8–T4.9、§27.2 P1④/P2⑥⑦/P3⑤/P4⑤⑥、kinds 29→30→33 递进（v3:483）均与原文一致；B 组引用的 §3.4 系 `conventions/coding-tables.md` §3.4「重构出门」，非设计文档章节，v2→v3 不受影响。仓库现状（kinds 29/24、schemas 11 份、ports 仅 ports.go、adapters 无 quality/、迁移仅 00001）已对账写入 D-0

### 既有 lint 欠账（会话间 T2.3 文件，2026-10-17 发现）— 已清

`golangci-lint run ./internal/...` 曾报 6 处，全部在 T2.3 落地的文件：gofumpt 4（baselinesvc.go / baselinesvc_test.go / gatesvc_test.go / ulid_test.go）、gosec G101 1（gatesvc.go `ChannelLocalTokenTTY` 被误当凭据常量——就地 `#nosec G101` 注释豁免，说明它命名的是渠道而非凭据）、staticcheck ST1023 1（auditsvc.go `var prevHash canonical.Digest = audit.Genesis` 改省类型写法，canonical import 随之未用已删）。2026-10-17 复验 `golangci-lint run ./...` 0 issues、`go vet ./...` 干净、`go test -race ./...` 全绿——A-G1「无新增问题」恢复成立。
