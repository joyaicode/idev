---
audience: AI models and agents that load idev
authority: normative（治理点的登记表以本页为唯一真源；G 编号只认本页）
---

# 治理登记（governance）

三个铁律先重述，原文在各自权威页，本页不复制、不改写：

1. **不打分。** 分数门禁、LLM 给回报打分、rubric——禁令四处明文（[external-tools.md](external-tools.md)）。
2. **PASS ≠ 做对。** 每个工具的 PASS 只说明「没撞上已知的硬错」（SKILL.md「一条贯穿所有阶段的规矩」）。
3. **签字权不下放。** `is_human()` 词表在代码层拒绝 agent 名字签字（[chat-confirm-signoff.md](chat-confirm-signoff.md)）。

**登记不等于新建检查。** 本表把分散的既有治理点收拢成一份可查的清单：
「哪个环节有什么治理、以什么形式存在、权威在哪页」。新增治理（新机检、新 hook、新观测）仍走提案 → 拷问 → 人签（self-evolution.md），本表不提供任何绕路。

## 为什么需要一张表

对照 Claude Code 的 hooks/permission 模式做差距分析时，前提取决于「现在有什么」；治理点散在 prompt 规约、脚本机检、Go 强制、观测四层共几十处，没有一处能看全。答案以前靠人脑拼，拼漏的缝隙就是「知道了但没人查」的地方。

## 登记表（G 系列只认本页）

| id | 治理点 | 形式 | 落点 | 权威页 |
|---|---|---|---|---|
| G1 | 签字权不可下放（agent 名字签字代码层拒） | go强制+机检 | `workflow_spec.is_human` 词表、`signoff/identity.go`、record 侧核对 | chat-confirm-signoff.md |
| G2 | 回报诚实性机检（evidence-present / no-signoff-write / brief-complete / return-schema / metrics-shape） | 机检 | `delegation.py write` | agents-evolve.md |
| G3 | AUTO 只信自己现场跑的检查（不认事先存的文件） | 机检 | `workflow.py run_auto_check` | workflow-schema.md |
| G4 | pre_tool 四拒绝（手写 reopen_baseline / agent push / 绕 Go 引擎 / 越租约写） | best-effort hook | `hooks/pre_tool.py`；权威在 record 侧 | hitl-risk-tiers.md |
| G5 | CHANGED ⊆ modified_files（agent 自报有第三方账） | 机检 | `delegation.py` 对照 `subagent-stops.jsonl` | hooks/README.md |
| G6 | 回合预算（无正文回合 / serial_reads / claude -p 探测） | 观测（WARN 不挡） | `turn-budget.py` + `trace.sh append` 末尾 | SKILL.md「回合预算」 |
| G7 | 周审计硬报警四项（multi-exec-calls / seal-without-signoff / extensions 两项） | 观测（HARD_COUNT） | `audit_traces_lib.py` | trace.md |
| G8 | IDEA_HITS / FORECAST declared（交代必须存在，语义不判） | 机检 | `delegation.py check_idea / check_forecast` | coding.md |
| G9 | 一次性授权（drive=auto 代决 / IDEV_ALLOW_AGENT_PUSH） | 配置+观测 | `drive-mode.yaml`、`workflow.py` 代决、推翻计数进 ticket_metrics | chat-confirm-signoff.md |
| G10 | 写租约单写者 + fencing（写路径相交拒第二张） | go强制 | `internal/domain/lease/lease.go`、`leasesvc.go` | workflow-schema.md |
| G11 | 独立复核（写手 ≠ 复核者，复核留痕引用证据） | 机检 | `workflow.py record` 的 VERIFY 强制、`KIND_VERIFIER` | agents.md |
| G12 | gate assurance 矩阵（P0 要求 high，agent 满足不了） | go强制 | `internal/domain/gate/gate.go` | hitl-risk-tiers.md |
| G13 | 停靠观测统一（DOCK 行一套词汇四种循环） | 观测 | drive_run.py / fanout.py / workflow.py land | agent-loop.md |
| G14 | clean_pass 重跑计数（CLEAN attempt 行，派生不猜数） | 观测 | `workflow.py _clean_line` | agent-loop.md |
| G15 | 重放剪除可见性（上下文剪除行永远在，需要时 load） | 机检（行存在性） | `read_ledger.project` `context_pruned` | agents.md「改动邻域与重放剪除」 |
| G16 | evals 反 LLM 评分（FORBIDDEN 列表自检） | 套件自检 | `skill-up-eval.py` | external-tools.md |
| G17 | 提案 → 拷问 → 人签才改真源（含本表自身的改动） | 规约+人闸 | `state/proposals/`、self-evolve-review 配方 | self-evolution.md |
| G18 | 删除预算（迭代删除行数 ≥ 新增，只 WARN） | 观测 | `deletion-budget.py` | self-evolution.md |

新治理点 = 本表加行 + 各自落点实现，行里写清形式（prompt / 机检 / go强制 / 观测 / best-effort hook）与权威页。**形式是事实陈述不是承诺**：prompt 级行被绕不报警，写在这里让人知道哪条防线是纸面的。

## 对照 Claude hooks/permission 的差距分析

| Claude 模式 | idev 对应 | 判定 |
|---|---|---|
| 确定性策略用 hook（模型绕不过） | G1/G10/G12（go强制）、G4（record 侧权威） | 无差距；hook 明示 best-effort、权威在 record 是有意设计 |
| 拒绝时把 reason 反馈给模型 | pre_tool deny 文案、delegation FAIL 文案（带「怎么做」） | 无差距 |
| 裁量判断用小模型分类器 | **不引入** | 分类器 ≈ 语义判定，撞不打分禁令；裁量判断走人 + grilling |
| 一次性授权 mode+allowlist | G9（drive_mode auto + RECOMMEND + 环境变量门） | 已有对应物；推翻计数回灌收紧（chat-confirm「推翻多了就收紧」） |
| 校验放工具执行前、独立于模型意愿 | G1/G10/G12 代码层强制 | 无差距 |

已知缺口（只登记，升级须单独立项）：

- Cursor 忽略 `tools` 字段 → `idev-coder`「只跑命令不改代码」只剩 prompt 级约束（agents-todo #22 已记）。
- hooks 整层是 best-effort，装不上/被宿主禁用不报警——hooks/README.md 自我定位如此，属环境面。

## 维护

- 加行：提案通过后加，一行 = id / 治理点 / 形式 / 落点 / 权威页五列，不写长文。
- 改形式（如 prompt 级升机检）：改那一行的「形式」列 + 落点字段，提案另立。
- 不设生成机制：行数不到生成器收益线（对照 gen-kinds.py 的五副本场景），手工维护 + refs-check 锁链接。
