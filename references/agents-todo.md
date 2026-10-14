# agent 层：待办与验证状态

已知但未做的事。**不是提案** —— 提案要走 `state/proposals/` 加 grill 加人确认才能 land
（见 [agents-evolve.md](agents-evolve.md) 第八节）。这页只记"知道要做、还没做"，
以及每项**卡在什么上**。

状态：`阻塞` 需要先有别的东西 · `待验` 做完了但没跑过 · `待议` 要先有决定 · `可做` 随时可动手

---

## 验证状态

agent 层已合并进 idev，六道自检的结果：

| 自检 | 结果 |
|---|---|
| `scripts/syntax-check.sh` | **PASS** — 12 个脚本可解析 |
| `scripts/agents-check.py` | **PASS** — 5 agents / 29 kinds（24 委派 / 5 导体保留） |
| `scripts/workflow-check.sh` | **PASS** — 配方与 run 契约 |
| `scripts/selfcheck.sh` | **PASS** — 内核 61 条锁 |
| `scripts/agent-smoke.sh` | **PASS** — 143 条断言，0 失败 |
| `scripts/healthcheck.sh` | **4 个 FAIL，与本层无关** — 它要求 `~/.cursor/skills/idev` 是真目录，而当前拓扑是「git 仓是真源、那里是 symlink」 |

**按顺序跑，前一道过不了后面的结论就不成立：**

```bash
bash scripts/syntax-check.sh     # 纯解析，零副作用
python3 scripts/agents-check.py  # 定义 + 回报格式 + 登记表
bash scripts/agent-smoke.sh      # 端到端 143 条
```

`syntax-check` 必须第一个跑 —— **smoke 抓不到 smoke 自己的语法错**。详见
[failure-modes.md](failure-modes.md) 第十一条。

失败签名归一化已实测（同错签名相同、不同错签名不同），**但只验过 Java 风格的断言失败与
NPE** —— 换语言或日志格式仍需自己验一次，见 P0 第 6 项。

---

## P0 装上去，然后用真任务验

自动测试到此为止，**剩下的全部需要真运行时或真票**。

| # | 待办 | 状态 | 完成判据 |
|---|---|---|---|
| 1 | 装五个 agent：`bash scripts/link-agents.sh` | **可做** | `~/.claude/agents/` 与 `~/.cursor/agents/` 各 5 个链接；`--check` 核对 |
| 2 | 提交合并的改动 | **可做** | `git status` 干净 |
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

## P2 自进化回路：脚本有了，触发还靠手

| # | 待办 | 状态 | 说明 |
|---|---|---|---|
| 9 | 给 `agent-review.sh` 装定时任务 | 可做 | 参考 `install-weekly-evolve.sh` 的 LaunchAgent 写法，排在内核那条之后 |
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

## 维护这页

做完一项就删掉它，不要留"已完成"的历史 —— 那是 [changelog.md](changelog.md) 的事。
删项之后**检查编号引用**：P1/P2 的"卡在 #N"会指错。

新增项写清**卡在什么上**，否则三周后没人记得为什么没做。

发现的问题如果已经有了修法，直接修，不要先记在这里。这页只放"要先有决定"或"要先有别的
东西"的事。改本层代码之前先扫 [failure-modes.md](failure-modes.md)。
