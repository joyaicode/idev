# 待办与验证状态

agent 层已知但未做的事在下面 P0–P3，编号 #1–#24（做完即删，编号不复用，缺口是有意的）。架构演进（2026-10-19 评审）在文末，编号 E，不占用这些号。

**不是提案** —— 提案要走 `state/proposals/` 加 grill 加人确认才能 land
（见 [agents-evolve.md](agents-evolve.md) 第八节）。这页只记"知道要做、还没做"，
以及每项**卡在什么上**。

状态：`阻塞` 需要先有别的东西 · `待验` 做完了但没跑过 · `待议` 要先有决定 · `可做` 随时可动手

---

## 验证状态

agent 层已合并进 idev，自检链的结果（2026-10-19 全量重跑）：

| 自检 | 结果 |
|---|---|
| `scripts/syntax-check.sh` | **PASS** — 92 个脚本可解析 |
| `scripts/agents-check.py` | **PASS** — 5 agents / 29 kinds（24 委派 / 5 导体保留） |
| `scripts/workflow-check.sh` | **PASS** — 配方与 run 契约 |
| `scripts/refs-check.sh` | **PASS** — 文档交叉引用 |
| `scripts/selfcheck.sh` | **PASS** — 内核 26 道锁 |
| `scripts/agent-smoke.sh` | **PASS** — 481 条断言，0 失败 |
| `scripts/healthcheck.sh` | **PASS** — warns=0 |
| `scripts/test_signoff.py` | **PASS** — 165 条共享签字用例（confirm 105 / reject 7 / human 53） |
| `scripts/test_concurrency.py` | **PASS** — 三条写盘路径并发不丢失 |
| `scripts/test_signals.py` | **PASS** — SIGNAL 停跑与答复规则 6 组用例 |

**按顺序跑，前一道过不了后面的结论就不成立：**

```bash
bash scripts/syntax-check.sh     # 纯解析，零副作用
python3 scripts/agents-check.py  # 定义 + 回报格式 + 登记表
bash scripts/agent-smoke.sh      # 端到端 481 条
```

`syntax-check` 必须第一个跑 —— **smoke 抓不到 smoke 自己的语法错**。详见
[failure-modes.md](failure-modes.md) 第十一条。

失败签名归一化已实测（同错签名相同、不同错签名不同），**但只验过 Java 风格的断言失败与
NPE** —— 换语言或日志格式仍需自己验一次，见 P0 第 6 项。

---

## P0 用真任务验

自动测试到此为止，**剩下的全部需要真运行时或真票**。

| # | 待办 | 状态 | 完成判据 |
|---|---|---|---|
| 3 | Claude Code：`/idev` 唤起导体，5 个 agent 可见 | **待验** | `claude --debug` 无 skip 记录；`/doctor` 不报重名 |
| 4 | Cursor：`/idev-coder` 能否唤起，且它怎么处理 `tools` 字段 | **待验** | 装完在 Cursor 里敲 `/idev-` 看补全；`tools` 若不被识别，`readonly: true` 仍在 |
| 5 | 自动唤起：不打 `/idev`，直接说交付类诉求 | **待验** | 两边都能按 description 命中 |
| 6 | 签名归一化在**你自己的栈**上 | **待验** | 同错签名相同、不同错签名不同 |

**第 4 项是唯一没有文档依据的。** 安装已不再依赖「Cursor 兼容读 `~/.claude/agents/`」这个
未实测的假设 —— 两处都装，多一条 symlink 换掉一个赌注。剩下待验的是 Cursor 怎么处理
Claude 专有的 `tools` 字段。Claude Code 侧官方明示会静默忽略未识别字段；Cursor 侧
无文档，也没实测过。如果那边 agent 加载异常，先只留一个最小文件试，别五个一起铺。

**第 6 项最该当心。** 归一化是启发式：**过度归一化会把两个不同的 bug 合成同一签名，
误触「同签名 3 次」红线，把正常排查打断**。拿你真实的失败日志各试两份。

---

## P1 装好之后

| # | 待办 | 状态 | 卡在什么上 |
|---|---|---|---|
| 7 | 端到端一轮：真票跑 `code-review` 全程 | 阻塞 | 要 #3 或 #4 之一能唤起 |
| 8 | agent prompt 的真任务有效性 | 阻塞 | 要 #7；头几轮大概率要按 `SUGGEST` 回报改措辞 |

---

## P2 自进化回路

| # | 待办 | 状态 | 说明 |
|---|---|---|---|
| 10 | `agent-feedback.yaml` 的停问时机没有强制 | 待议 | 契约说"整轮一次"，但没有脚本会提醒。做硬了会违反 H5「不为观测另停」 |
| 11 | 本层 `state/proposals/` 还是空的 | 阻塞 | 等 #8 产出第一批 `SUGGEST`，够两次再由 `agent-review.sh` 起草 |

第 10 项触及一个张力：**可观测性要数据，内核禁止为观测另停**。现在靠导体自觉，这是有意的
保守 —— 但也意味着导体偷懒时这层数据就是空的，`agent-metrics` 会显示"还没有委派留痕"。

---

## P3 明确排除的（要做需先推翻理由）

这些不是遗漏，是**当前有意不做**。写在这里是为了下次有人提起时不用重新论证一遍。

| # | 东西 | 为什么不做 | 要做的话先解决 |
|---|---|---|---|
| 12 | 并行 fan-out | `conventions/canon.md:181` 把「多开几个 Agent 就快了」列为反模式；`references/hitl-risk-tiers.md:33` 不内置并行阶段机 | 重做 `current_step()` 单指针与 `find_run()` 拒多活跃 run；重新定义周审计 `multi-exec-calls` 口径 |
| 13 | step 级 `agent:` 字段覆盖 | 走 kind 默认表够用，且不动配方语法 | 同时改 `STEP_FIELDS` + `workflow-check` + `workflow-schema.md` 三处 |
| 14 | 继续细分 agent（回到八个或更多） | 一个阶段里的动作同进同退；切碎只会让导体多组委派包，每组一次多一次 `brief-complete` 出错机会 | 先有数据证明某个 agent 职责确实冲突（`agent-metrics` 里它的密度明显高于其它） |
| 15 | 把导体也做成 agent | subagent 看不到对话历史、`is_human()` 黑名单含 `agent/ai/cursor/assistant`、Cursor 的嵌套限制 | 无 —— 这会把「人机共驾」降级成「无人值守」 |
| 16 | `readonly: true` | 没有一个步骤是纯读的（reviewer 要写 `review.md`，coder 要跑 `git commit`） | 无 —— `agents-check.py` 按 `READONLY_BREAKS` 逐个硬检查 |
| 17 | LLM 给回报打分 | 内核明令禁止分数门禁与 LLM 自评盖章 | 无 —— 这条不打算改 |
| 18 | 建 `skills/` 目录放第二个顶层 Skill | `cohesion.md` 明文禁止；skill 只有 `/idev` 一个 | 正面论证为什么需要第二个入口 |

---

## P3 覆盖缺口（知道测不到）

| # | 测不到什么 | 为什么 |
|---|---|---|
| 19 | 真实的 agent 委派（Agent 工具 / `/name` 调用） | 需要 Claude Code 或 Cursor 运行时，smoke 是纯脚本 |
| 20 | agent 定义**正文的语义质量** | smoke 只能测结构（字段齐不齐、禁用工具在不在）。prompt 写得好不好只能靠 #8 的真任务 |
| 21 | 「零命中却新增抽象层」 | 要读 diff 并判断「是否过早」，机器判不了。交 `idev-reviewer` 扫 §1 + 导体验收，见 `boost.md` |
| 22 | `idev-coder` 的「只跑命令不借机改代码」 | 它同时拥有 `code` 阶段和 `git.commit_push`，必须有 `Write`/`Edit`，工具级拦不住。只剩硬规则 12–15 + 导体验收 |
| 23 | `agents-check` 对 `>-` 折叠 description 的内容提取 | 只检查存在性，够用；真要提取得引 YAML 依赖 |
| 24 | `--days` 对 `at` 无法解析的留痕总是包含 | 有意：宁可多算不漏算。不是 bug，是已知行为 |

---

## 架构演进（2026-10-19）

活路径是 `workflow.py` 写 `run.yaml`。Go 的 `runsvc` 在进程内 e2e 里成立，`record` 不进入它。SQLite 可写的是 gate、lease、audit；run 的 `Create`/`Save`、delegation、baseline 仍返回未接线。先让一笔状态迁移落在一个事务里，再暴露 MCP。

阶段 1 不接 passkey。`AllowLowForHigh` 保持开着，降级继续进审计。有意不做、不必列入下面表格的：第二个顶层 Skill、分数门禁、并行 fan-out、把导体做成 subagent、B 类另开 decision gate、现在改用 sqlc。

### E1 签字通道

| 项 | 待办 | 状态 | 卡在 | 完成判据 |
|---|---|---|---|---|
| E1.1 | go 引擎强制 A 类字段带 `approval_id` | 待议 | 人已定 deliver 阶段先不强制；gate 通道 record 已写 `signoff.approval_id` | `check-feature` 对 `sealed` / `arch.accepted` / `aligned` / `resolved` / `reopen` 缺 `approval_id` 即 FAIL；python 引擎维持现状并打印引擎名 |
| E1.2 | 生命周期签字补专用 gate 类型 | 待议 | 通道已接：`workflow.py ask` 走 `idev gate request`，类型由 `gate_type` 或 will_write 推导（只产 `accepted_plan` / `step_confirm`）；`sealed` / `defect_origin` / `reopen_baseline` 在 Go 侧（`signoff/confirm.go` 关键字闸）。剩余部分与 2026-10-19 提案切片 3「保留推导」冲突，要先增补提案 | 密封、架构、提测、P0 的 plan 与 resolved、回退、promote 各有一次 `idev gate request`，摘要绑定提案 3.1 的文件 |
| E1.3 | python 回退改成显式破窗文件 | 待议 | 2026-10-19 提案已确认 env-var 回退（`IDEV_ENGINE=python`），做这项要先推翻它 | PATH 上有 `idev` 时，只设 `IDEV_ENGINE=python` 被拒；破窗文件写明原因和到期日 |
| E1.4 | 降级批准按周计数 | 可做 | — | audit 里 `assurance_downgraded` 可按周汇总（`cmd/idev` 审计链已记该字段，差一个查询命令） |

### E2 单写者

| 项 | 待办 | 状态 | 卡在 | 完成判据 |
|---|---|---|---|---|
| E2.1 | `record` 进入 `runsvc.Apply`，`run.yaml` 改为导出 | 阻塞 | E1.3 | 一次 PASS 在同一事务里改 run、写审计；事务失败不留下半笔租约。python 引擎仍写 YAML |
| E2.2 | 接上 `RunRepo` 的 Create/Save，去掉 `external` 投影 | 阻塞 | E2.1 | sqlite `runRepo` 不再返回 `errNotWired`；版本冲突得到 `ConflictStaleVersion` |
| E2.3 | 租约、状态、审计包进同一个事务 | 阻塞 | E2.2 | storetest 有一条中途失败用例：lease 与 run 同时不留 |
| E2.4 | fencing 从领租约走到回报 | 阻塞 | E2.3 | 旧 fencing 的迟到回报被拒，且零审计残留 |
| E2.5 | e2e 改走 CLI，python golden 另开车道 | 阻塞 | E2.4 | lite-change 七步经默认引擎跑完；既有 txtar 字节不动 |

### E3 独立验证

| 项 | 待办 | 状态 | 卡在 | 完成判据 |
|---|---|---|---|---|
| E3.1 | 对齐 verify 租约的发放时机 | 阻塞 | E2.5 | `kinds.yaml` 与 `leasesvc` 对「何时发 verify」是同一句，注释与代码一起改 |
| E3.2 | `verify: independent` 的 PASS 要验证者租约 | 阻塞 | E3.1 | `verifier == writer` 或没有 verify 租约时 `record PASS` 为 BLOCKED；单独的 `--verified-by` 不够 |
| E3.3 | `DelegationRepo` 由服务端分配 attempt | 阻塞 | E2.2 | 重复 `(run, step, attempt)` 得到 `ConflictAttemptExists`；客户端文件名不再是主键 |
| E3.4 | 回报先过 `delegation-return` schema | 阻塞 | E3.3 | 正则只把 `STATUS` / `ASSUMED` 收成对象；schema 失败即 FAIL |

### E4 内容指纹

| 项 | 待办 | 状态 | 卡在 | 完成判据 |
|---|---|---|---|---|
| E4.1 | 接上 `BaselineRepo` | 阻塞 | E2.2 | 第二次 `Seal` 返回 `ConflictSealedBaseline`；baseline 不再 `errNotWired` |
| E4.2 | 密封写入 `manifest_root`，后续阶段重算 | 阻塞 | E4.1 | 摘要不一致则 run blocked，原因 `baseline-drift`；重算失败不自动解封 |
| E4.3 | YAML 的 `sealed` 变成行的投影 | 阻塞 | E4.2 | 库中无密封行时，手改 `sealed: true`，`check-feature` FAIL |

### E5 服务面

| 项 | 待办 | 状态 | 卡在 | 完成判据 |
|---|---|---|---|---|
| E5.1 | `idevd` 只暴露 stdio MCP | 阻塞 | E4.3 | 工具面覆盖 run、step、delegation、lease、baseline；契约测试读 `api/schemas` |
| E5.2 | MCP 面没有 `gate approve` | 阻塞 | E5.1 | `tools/list` 不含批准；agent 令牌调用批准被拒绝并留下审计 |
| E5.3 | SKILL 收到路由，agent 不再复述签字文法 | 阻塞 | E5.1 | 五个 agent 的签字字段改成指向 [chat-confirm-signoff.md](chat-confirm-signoff.md) 的一行；`agents-check` 仍绿 |
| E5.4 | 审计 span 由服务写入 | 阻塞 | E5.1 | run→step→delegation 在审计链上有序列；`trace.sh append` 变为导出，漏写不影响事务提交 |
| E5.5 | workspace 适配器做哈希和票定位 | 阻塞 | E5.1 | 与 Python 对同一票目录输出同一 digest |

### E6 后置

要做须先有阶段 5 的服务面，并人决定启动。E6.5 只在 E2.5 的 go 车道与 python golden 对不上、而且解释不了时才开。

| 项 | 待办 | 状态 | 卡在 | 完成判据 |
|---|---|---|---|---|
| E6.1 | passkey 之后，P0 闸关掉 `AllowLowForHigh` | 待议 | E5.2，且人决定启动 | P0 闸在低保证下被拒；既有降级记录仍可验证 |
| E6.2 | Postgres 跑同一套 storetest | 待议 | E5.1，且人决定启动 | sqlite 与 postgres 的 storetest 同一份断言全绿 |
| E6.3 | 质量门 qodana / e2e | 待议 | E5.1，且人决定启动 | 判定由服务端按退出码和原始报告复算；MCP 上没有放行工具 |
| E6.4 | OIDC 多用户 | 待议 | E6.1，且人决定启动 | 远程 principal 与本地 `people.yaml` 走同一 `Authorizer`；本地令牌通道保留 |
| E6.5 | shadow 双写比对 | 待议 | E2.5 对不上且解释不了 | 只读比对，不写第二份状态 |

---

## 维护这页

做完一项就删掉它，不要留"已完成"的历史 —— 那是 [changelog.md](changelog.md) 的事。
删项之后**检查编号引用**：P1/P2 的"卡在 #N"、架构表的"卡在 E…"会指错。

新增项写清**卡在什么上**，否则三周后没人记得为什么没做。

发现的问题如果已经有了修法，直接修，不要先记在这里。这页只放"要先有决定"或"要先有别的
东西"的事。改本层代码之前先扫 [failure-modes.md](failure-modes.md)。
