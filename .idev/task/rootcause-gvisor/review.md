# Review（已改）

feature: rootcause-gvisor
baseline_revision: 1
by: idev-reviewer

## 少做（基线 item 未落地）

- 无。B1：`scripts/repl.py:cmd_run` 在 `--step rootcause` 时调用 `scripts/lib/runsc_probe.py:execute`，不走宿主 `subprocess`；`bundle_spec` 把仓库挂成 `ro`。B2：`find_runsc` 找不到时返回退出码 127 且 `launched=False`，片段不在宿主执行；`cmd_run` 把非 0 收成进程退出码 1。B3：`scripts/hypothesis.py:check` 对 `repl/*.out` 缺少含 `runtime: runsc` 的回执时记入错误并返回 1；`scripts/repl.py:147` 这类代码路径不是 transcript，`repl_transcript_missing_receipt` 返回假。B4：其它 step 仍用宿主 Python，写 1 个 `.out`，不写 `.receipt`。

## 多做（基线外行为）

- 无。回执里的 `network: none` 和 `mount:` 是同一次 runsc 调用的挂载事实，没有第二套开关。

## 基线冲突

- 无。

## 编码规范（对照 `conventions/coding.md`，当轮纠正）

编号只认 `conventions/coding.md` §3.5：`P1–P19`、`C1–C40`、`R1–R7`（全表在 `coding-tables.md`）。`T#` 认 `conventions/canon.md`。

- 场景命中: 零命中。rootcause 与宿主是两条不再增加的通道，保持分叉（P16 的运用，不是漏用）。不抽策略（P5 的「还会增」不成立）。只有一种 runsc 执行器，用的是具体模块（P6）。
- 气味命中: C1（`execute` 38 行）；C8（`_bind` 用布尔切换 ro/rw）；C10（`runtime: runsc` 三处字面量）
- 纠正: `scripts/lib/runsc_probe.py:execute` 把准备目录、运行、删除拆开，并在本函数用 `finally` 释放临时目录，`delete` 加上与 `run` 相同的超时且不要丢掉失败；`scripts/lib/runsc_probe.py:_bind` 改成调用处能看见 ro/rw 的两个具名函数或模式字符串；`scripts/repl.py:cmd_run` 与 `scripts/hypothesis.py:repl_transcript_missing_receipt` 共用同一个回执标记常量
- 重构: 无
- 五轴: 正确性过；可读性命中 C1；架构过；安全过；性能过
- 栈指南: python（`code-review-skill/reference/python.md`、`common-bugs-checklist.md`；五轴见 `code-review-and-quality`；沙箱挂载对照过 `security-and-hardening` 的输入与密钥清单）
- 增强扫描: 已跑 coding-scan + 五轴 + 栈指南
- 审查者: idev-reviewer
- 文件与行数: 触及 5 个文件，新增 2，最长 594 行
- 扫描: problems 未跑（coding-scan 判定 java=0，未调用 problems-scan）。lang 全仓退出码 1。本票 python 文件的 `python_inspect` 命中见下方 I* 与已扫理由。vue-skills 无输出。无 Java 黄条。

净增说得出换来什么：`scripts/lib/runsc_probe.py`（143 行）是 B1/B2 的隔离边界；`scripts/test_runsc_probe.py`（150 行）是四条 item 的假 runsc 护栏；`scripts/repl.py`、`scripts/hypothesis.py`、`agents/idev-ops.md` 各只为入口分叉、回执检查、操作说明动过。不记 T1 / C3 / C6。`ProbeResult` 是一次运行的结果形状，不是只有 get/set 的业务类型，不记 C11。

已扫、写明理由、不列入待签收（`python_inspect` 的 file:line 都在这里）：

- `scripts/lib/runsc_probe.py:59` `bundle_spec` 32 行、5 个参数。一份 OCI 规格的必填坐标（仓库、内核、scratch、片段、解释器）。收成只有字段的请求对象是哑对象。允许。
- `scripts/lib/runsc_probe.py:93` `_argv` 4 个参数。一条 argv 的四个必填片段，没有缺省。允许。
- `scripts/repl.py:149` `cmd_run` 96 行、圈复杂度 19。两条通道必须留在这一次调用里（B1/B4）。回执依赖本次的目录、序号、bundle 和退出码，拆出去会超过 3 个必填参数。早返回是改前的入口校验。本轮不整函数重写。允许。
- `scripts/repl.py:275` `main` 26 行。本轮没改，只注册 run/list/show。允许。
- `scripts/hypothesis.py:196` `cmd_add` 31 行；`:228` `cmd_set` 42 行、圈复杂度 14；`:325` `check` 134 行、圈复杂度 44；`:461` `cmd_candidates` 39 行、圈复杂度 12；`:502` `cmd_blast` 34 行；`:542` `main` 49 行。本轮只加了 `repl_transcript_missing_receipt`（10 行）和 `check` 证据循环里的一条回执判定，不改六条强约束。拆这些存量函数是结构帽。允许。文件 594 行超过 400 行，理由同上。
- `scripts/test_runsc_probe.py:78` `test_rootcause_invokes_runsc_and_does_not_write_the_repo` 25 行。临界带：同一次假 runsc 上核对退出码、宿主文件、回执、argv 和挂载。允许。
- `agents/idev-ops.md` 446 行。一份操作说明，本轮只追加根因探针那段。允许。

### I1 已改

- 锚点: `scripts/lib/runsc_probe.py:execute`（`scripts/lib/runsc_probe.py:101`）
- 依据: C1。函数 38 行，同时准备目录、执行 runsc、删除容器。
- 纠正: 准备、运行、删除分成各自不超过 20 行的函数；释放仍留在 `execute` 的 `finally`，不要把释放推给 `cmd_run`。

### I2 已改

- 锚点: `scripts/lib/runsc_probe.py:execute`（`scripts/lib/runsc_probe.py:115` 的 `mkdtemp`）；调用方 `scripts/repl.py:cmd_run`
- 依据: C19。`tempfile.mkdtemp` 在正常返回、超时、`delete` 失败三条路径都不释放。返回值只有 `bundle`，parent、state、scratch 没有主人。`cmd_run` 把 bundle 路径写进回执后也不删。测试在 `cmd_run` 返回后还读 `config.json`，所以不能在返回前默默删掉还不把事实留在回执里。
- 纠正: 获取方释放。回执写下需要的挂载事实后删除 parent；覆盖超时和 `delete` 失败。测试改为读回执，或在删除前断言。

### I3 已改

- 锚点: `scripts/lib/runsc_probe.py:execute`（`scripts/lib/runsc_probe.py:134` 的 `delete`）
- 依据: T8、T11。canon §2：新增外部调用没有超时。`run` 有 `TIMEOUT_S`，`delete` 没有，并且 `check=False` 丢掉失败。`delete` 挂起时整个 rootcause 步骤不返回；`delete` 失败时仍按探针退出码写回执。
- 纠正: `delete` 使用与 `run` 相同的超时。失败写到 stderr，探针退出码仍可区分，但不能假装清理已经完成。

### I4 已改

- 锚点: `scripts/lib/runsc_probe.py:_bind`（`scripts/lib/runsc_probe.py:49`）
- 依据: C8。`readonly: bool` 在 `True` / `False` 之间切换 ro 与 rw 两种挂载，调用处看不出读还是写。
- 纠正: 两个具名函数，或传入 `"ro"` / `"rw"`。不要用布尔参数切换创建。

### I5 已改

- 锚点: `scripts/repl.py:cmd_run`（回执字符串，约第 217 与 228 行）；`scripts/hypothesis.py:repl_transcript_missing_receipt`（约第 322 行）
- 依据: C10。`runtime: runsc` 在回执正文、transcript 注释、`check` 三处各写一遍。写入和检查的变化原因相同，已经是第三次（T7：处理=抽成一处常量，不上框架）。
- 纠正: 标记收到一处常量。`check` 只依赖这颗字符串，不依赖 `execute` 的运行过程。

## 本轮允许改的路径

只许 `arch.yaml` 里 `include: true` 的文件。工作区其它脏文件列在下面，不要动。

- `scripts/lib/runsc_probe.py`
- `scripts/repl.py`
- `scripts/hypothesis.py`
- `agents/idev-ops.md`
- `scripts/test_runsc_probe.py`

- UNRELATED: 63
  - `.gitignore`
  - `SKILL.md`
  - `agents/idev-coder.md`
  - `agents/idev-deliver.md`
  - `deliver/SKILL.md`
  - `deliver/references/arch.example.yaml`
  - `deliver/references/deliver-schema.md`
  - `references/agent-brief.md`
  - `references/agent-feedback.example.yaml`
  - `references/agents-evolve.md`
  - `references/agents.md`
  - `references/boost.md`
  - `references/changelog.md`
  - `references/chat-confirm-signoff.md`
  - `references/extension-config.md`
  - `references/glossary.md`
  - `references/hitl-risk-tiers.md`
  - `references/invoke.md`
  - `references/operator-cheatsheet.md`
  - `references/process-eval.md`
  - `references/workflow-schema.md`
  - `scripts/audit_traces_lib.py`
  - `scripts/check-feature.py`
  - `scripts/coding-scan.sh`
  - `scripts/deep-read-audit.py`
  - `scripts/delegation.py`
  - `scripts/docs/notes/Building Secure and Reliable Systems-精读缺口.md`
  - `scripts/docs/notes/README.md`
  - `scripts/docs/notes/Site Reliability Engineering-精读缺口.md`
  - `scripts/docs/notes/Web性能权威指南-精读缺口.md`
  - `scripts/docs/notes/程序员修炼之道-精读缺口.md`
  - `scripts/docs/notes/程序员的职业素养-精读缺口.md`
  - `scripts/knowledge.py`
  - `scripts/lib/staffing.py`
  - `scripts/lib/step_packet.py`
  - `scripts/nudge.py`
  - `scripts/plugin/canon_smells.py`
  - `scripts/plugin/go_inspect.py`
  - `scripts/plugin/java_inspect.py`
  - `scripts/plugin/js_inspect.py`
  - `scripts/plugin/python_inspect.py`
  - `scripts/process-eval.py`
  - `scripts/selfcheck.sh`
  - `scripts/session-context.py`
  - `scripts/test_canon_smells.py`
  - `scripts/test_deep_read_audit.py`
  - `scripts/test_drive.py`
  - `scripts/test_knowledge.py`
  - `scripts/test_nudge.py`
  - `scripts/test_process_eval.py`
  - `scripts/test_workflow_enhance.py`
  - `scripts/ticket_metrics.py`
  - `scripts/workflow.py`
  - `verify/SKILL.md`
  - `verify/references/evolve.md`
  - `.idev/docs/prd/rootcause-gvisor.md`
  - `.idev/docs/spec/rootcause-gvisor.md`
  - `.idev/task/-/`
  - `scripts/drive-mode.py`
  - `scripts/lib/drive_mode.py`
  - `scripts/test_deep_read_gaps.py`
  - `scripts/test_delegation_idea.py`
  - `scripts/test_drive_mode.py`

## 影响面

- `codegraph_trace` 从 `cmd_run` 到 `execute` 没有静态边（属性调用 `runsc_probe.execute`）。源码 `scripts/repl.py:cmd_run` 调用了 `execute`。测试经 `cmd_run` 间接进入，不直接调用 `execute`。include 之外没有函数调用 `execute`。
- `repl_transcript_missing_receipt` 的调用方只有 `scripts/hypothesis.py:check`。`check` 的调用方是同文件的 `cmd_add`、`cmd_set`、`cmd_check`。`cmd_set` 写入后返回 `check` 的退出码，所以 evidence 挂上无回执的 repl transcript 时，`set` 也会非 0。这是 B3 收紧，不是 include 外的另一套实现。
- 仓内没有 `.ua/knowledge-graph.json`，也没有 `.understand-anything/knowledge-graph.json`。codegraph 本会话没有 impact 工具，用的是 `codegraph_trace`、`codegraph_node`、`codegraph_search`。

## 架构范式（T# / A#，见 conventions/canon.md §7）

- 本轮命中 `T#`：T8、T11（`execute` 的 `delete` 无超时且丢掉失败，见 I3）。T7 的回执标记见 I5，处理是抽成常量，不上框架。已扫 canon §2 的加层、开关、重试、队列信号，无其它命中。
- 所做动作：只记账，本步不改代码。
- `arch` 阶段 A1–A8：本步不重答。架构记录在票内 `arch.yaml`。

## 修正备注

review.fix 复核：I1–I5 已在当前工作区。本步没有改五个路径，也没有给 `cmd_run` 加「没有猜想就拒绝探针」的前置。

- I1：`_prepare`、`_run`、`_delete` 各自不超过 20 行。`execute` 在 `finally` 里 `shutil.rmtree`，释放留在获取方。
- I2：挂载事实在 `ProbeResult.mounts`，回执由 `receipt_body` 写出。`test_rootcause_invokes_runsc_and_does_not_write_the_repo` 读回执。正常返回、运行超时、delete 失败都断言 `idev-runsc-*` 已消失。超时和 delete 失败用例直接调用 `execute`。
- I3：`_delete` 使用 `TIMEOUT_S`。失败文本进入 stderr。探针 `exit_code` 仍是 run 的退出码。
- I4：`_bind` 传入 `"ro"` / `"rw"`。
- I5：`RUNTIME_MARK = "runtime: runsc"`。`repl.py` 的回执与 transcript 注释、`hypothesis.py` 的 check 都用它。check 只看这颗字符串。回执字符串未变，`agents/idev-ops.md` 未改。

护栏：`python3 scripts/test_runsc_probe.py`，8 项 OK。改前日志 `workflow/logs/review-fix-red.log` 已是绿的。复核日志 `workflow/logs/review-fix-green.log`。
