# agent 层的可调试与自进化

接进 idev 现有的自进化回路,**不另造一套**:执行 → trace / feedback → nudge(有信号)→ 提案草稿 → grill → 人确认 → land → curator 归档。权威契约仍是
[verify/references/evolve.md](../../idev/verify/references/evolve.md) 与
[references/self-evolution.md](../../idev/references/self-evolution.md)。

本页只补**委派这一跳**的可观测与改进入口。委派契约本身见 [agents.md](agents.md)。

沿用内核的三条底线,一条不松:

- **不打分。** 只计件数,不做总分、评级、LLM-as-judge 门禁
- **不自动 land。** 提案必须 grill + 人确认用语;AI 不得把提案标 `landed`
- **证据优先。** agent 说过不算证据(`conventions/evidence.md:4`),回报必须给路径

## 一、可调试:委派留痕

**问题:** 委派出去的 subagent 看不到对话历史,回来只有一段回报。它为什么做错 ——
是委派包没给够,还是它自己的定义含糊?不留痕就查不出来,只能重试碰运气。

**所以每次委派落一份留痕**,落点与 `run.yaml` 同目录:

```
<票目录>/workflow/delegations/<step-id>-<attempt>.yaml
```

`<票目录>` 只认 `doc_home.py --key task`。该目录在 `docs/task/` 或 `.idev/task/` 下,
`execution-clean` 不碰票目录,所以留痕不会被清理脚本删掉。

格式(照 `delegation.example.yaml`):

```yaml
schema_version: 1
feature: example-change
step: report
kind: review.report
agent: idev-reviewer
at: 2026-10-12T22:30:00+08:00
attempt: 1
started_at: 2026-10-12T22:26:55+08:00   # 导体委派前记
finished_at: 2026-10-12T22:30:00+08:00  # 收到回报后记
duration_s: 185                          # 由脚本从两端算出,不手填
brief:                 # 委派包原文 —— 重放的依据,必须完整
  ticket_home: docs/task/example-change
  repo: /path/to/product
  stage: code
  risk_tier: P1
  must_read: conventions/coding.md
  idev_root: ~/.cursor/skills/idev   # coder/verifier/ops 必填($IDEV)
  with: {}
  prior_failure: ""    # attempt > 1 时写上一次的失败原因
report:                # agent 回报原文,不要摘要
  status: PASS
  evidence: docs/task/example-change/review.md
  raw: |
    STATUS: PASS
    EVIDENCE: ...
metrics:               # 产出计量,扁平 map,只许数字或短字符串
  findings: 3
  blocking: 1
checks:                # 五项可机检(见第二节),由脚本写回
  evidence-present: PASS
  no-signoff-write: PASS
  brief-complete: PASS
  report-parsed: PASS
outcome: recorded      # recorded | rejected | retried
suggest: ""            # agent 提的改进建议,只记不执行
```

**时序是可选的,但缺了就没有耗时视图。** 导体委派前记 `started_at`、收到回报后记
`finished_at`,`duration_s` 由 `delegation.py` 算出写回。不设为必填是故意的:**可观测性不该
变成门禁** —— 少一个时间戳不该挡住一次正常的委派。但 `timeline` 和 `agent-eval` 会明说有多少
次委派没有计时,免得你以为耗时数据是全的。

**`metrics` 是扁平的件数 map**,字段名各 agent 自定(reviewer 记 `findings`,coder 记
`files_changed`,verifier 记 `cases_run`),由导体从回报里摘。嵌套结构会被 `metrics-shape`
拒掉 —— 一旦能嵌套,它就会长成第二套 eval,而内核禁止第二套账。

**`brief` 必须存原文,不存摘要** —— 留痕的全部价值在于能照原样再派一次:

```bash
python3 scripts/delegation.py replay --feature <f> --step <step>   # 打印可直接重发的委派包
```

重放打印委派包,**不自动重派**:派不派、派给谁仍是导体的决定。

`attempt > 1` 时 `brief.prior_failure` 必填。agent 定义里有一条硬规则要求它先读这一项,
不要重犯同一个错 —— 这是把"重试"变成"带着上次教训重试"。

## 二、五项可机检的诚实性检查

对齐 `verify/references/evolve.md` 的四条(`no-pass-without-evidence` 等)形态:**可机检、
失败就写进留痕、不得粉饰**。

| 检查 | 失败条件 | 责任方 |
|------|----------|--------|
| `evidence-present` | 回报 `PASS` 却没有证据路径(路径给了但不存在 → `WARN`) | agent |
| `no-signoff-write` | 回报声称写了、或留痕显示碰了 `sealed`/`accepted`/`aligned`/`resolved`/`reopen_baseline`/`semantic_gate.*` | agent(**严重**) |
| `brief-complete` | `brief` 缺 `ticket_home`/`repo`/`stage`/`must_read`,或派给 coder/verifier/ops 却缺 `idev_root` | **导体** |
| `report-parsed` | 回报没有可机读的 `STATUS:` 行 | agent |
| `metrics-shape` | `metrics` 不是扁平 map,或某个值是嵌套结构 / 超长字符串 | 导体 |

`write` 时 `metrics-shape` 直接拒收(退出码 2),不落盘 —— 形状错了的计量落下去就会污染
`agent-eval` 的求和。其余四项写回留痕,`no-signoff-write` 同样退出码 2。

**另有一组只对 `idev-coder` 生效的检查** —— `s0-declared` / `canon-walked` /
`struct-gated` / `hit-applied`,查的是 `coding.md` §0 的三项交代有没有真做。契约在
[boost.md](boost.md) 第一节。它们由同一个 `delegation.py` 算并写回同一个 `checks` 块,
但**其它 agent 的留痕里不会出现**:per-agent 的契约跟着那个 agent 走,不摊给所有人。

```bash
python3 scripts/delegation.py check --feature <f>          # 查这张票的全部留痕
python3 scripts/delegation.py check --feature <f> --step report
```

`no-signoff-write` 失败是**硬信号**,等级同内核周审计的 `seal-write-without-signoff`:
它意味着有 agent 试图越过人签字。命中就停,不要继续推进 run。

`brief-complete` 失败指向**导体**而不是 agent —— 这个区分是本层可调试性的关键:
它把"agent 不好用"和"你没给够上下文"分开,否则只会反复改 agent 定义而治不了病。

## 三、agent-eval(件数,不打分)

每次 run 结束,在 `<票目录>/workflow/report.md` 追加 `## agent-eval` 段,**只计件数**:

| 计数 | 从哪来 |
|------|--------|
| `delegated` | delegations 文件数 |
| `by_agent` | 每个 agent 各几次 |
| `conductor_kept` | run.yaml 里 `DELEGATE none` 的步骤数(委派比例的分母) |
| `blocked` | 回报 `BLOCKED` 的次数,按 `brief` / `env` / `logic` 分列 |
| `retried` | `attempt > 1` 的次数 |
| `rejected` | 导体打回(`outcome: rejected`)的次数 |
| `check_fail` | 五项检查各失败几次 |
| `suggest` | agent 提出建议的条数 |
| `duration_s` | 有计时的次数 n / 总计 / p50 / max |
| `produced` | `metrics` 按字段名求和(findings、files_changed、cases_run…) |

```bash
python3 scripts/delegation.py eval     --feature <f>   # 打印 agent-eval 段
python3 scripts/delegation.py timeline --feature <f>   # 全链路视图,见第四节
```

结构好不好由人在拷问里评,**不当机器门禁**。这一条跟内核 `evolve.md:38` 同义。
`duration_s` 和 `produced` 同理:它们是**量**,不是快慢好坏的判定 —— 一个慢的
`verify.run` 可能只是用例多。

## 四、timeline(全链路视图)

把内核 `run.yaml` 的步骤顺序与委派留痕 join 起来,一屏看完一次 run 谁做了什么、多久、
结果、证据:

```bash
python3 scripts/delegation.py timeline --feature <f>
```

```
步骤              kind                  执行者          状态              耗时  证据
preflight         preflight.inputs      导体            PASS                 -  -
report            review.report         idev-reviewer   PASS             3m05s  .../review.md
gate-report       human.gate            导体(签字)      PASS                 -  -
plan              verify.plan           idev-verifier   PASS             1m42s  .../plan.yaml
run               verify.run            idev-verifier   FAIL!            8m31s  .../report.md
                                                        ↳ check_fail: evidence-present
run #2            verify.run            idev-verifier   PASS             2m10s  .../report.md
```

这是**只读 join,不是第二份账** —— 它不写任何文件,数据仍只有 `run.yaml` 和留痕两处。
内核禁止第二套 eval 和一轮多条账,所以凡是"看"的需求都用聚合视图满足,不另记一份。

状态后的 `!` 表示该次留痕有检查失败;`↳` 行列出是哪几项,以及 agent 提的 `suggest`。
导体自己做的步骤显示为「导体」,`human.gate` 显示为「导体(签字)」。

没有 `run.yaml` 时它退化成按 step 排序的留痕列表,仍可用。

## 五、feedback tag(登记表,加标签 = 改本表)

verify 层已有 8 个 tag(`missed-impact` / `false-green` / … / `ok`),管的是红绿质量。
委派这一跳另有一张表,管的是**执行者**质量。两张表不要混用。

落点:`<票目录>/workflow/agent-feedback.yaml`,格式同 verify 的 `feedback.yaml`
(`schema_version` / `feature` / `status` / `tags` / `by` / `note`)。

| tag | 含义 | 下一刀通常改 |
|-----|------|--------------|
| `brief-incomplete` | 委派包缺项导致 agent BLOCKED | `agents.md` 的委派包格式 / 导体回路 |
| `brief-too-heavy` | 委派包塞了无关上下文,干扰了判断 | 委派包格式 |
| `prompt-unclear` | agent 定义里步骤含糊,导致做错 | 该 agent 的 `agents/*.md` |
| `agent-overstep` | agent 越界:改了不该改的、或试图写签字字段 | 该 agent 的硬规则 + 工具收紧 |
| `agent-no-evidence` | 回报 PASS 但给不出证据路径 | 该 agent 的回报格式 |
| `wrong-agent` | 这个 kind 派给了不合适的执行者 | `kind_agents.py` 的登记表 |
| `handoff-lossy` | 上一步的产物没传到下一步 | 委派包 / 回报格式 |
| `ok` | 这次没有委派层问题 |  |

`status: pending` 直到人写 `tags` 或明确 `none`。Agent 可代写人口述,但 `by` 必须是人。
试运行期每轮委派结束**停问一次**(整轮一次,不是每步一次 —— 每步都停会违反内核 H5「不为观测另停」)。

## 六、nudge(并入内核现有四条)

内核 `self-evolution.md` 的 nudge 已有四条触发条件。本层再加两条,**话术一样:一句话问要不要
写提案,人说要才写**:

5. 同一 agent 的 `check_fail` 累计 ≥ 2,且尚无对应提案
6. 同一 kind 连续 2 次 `retried` 或 `rejected`

**不算 nudge:** 单次 BLOCKED、单次重派、已 landed 的重复话题、纯 banter。

硬信号口径与内核一致 —— 只有上面两条、或 `no-signoff-write` 命中,才算信号。
单看留痕里的软提示**不单独抬 signal**。

```bash
python3 scripts/agent-metrics.py --signal    # 打印 signal=yes|no 与命中的条目
```

**定期复盘**(镜像内核 `evolve-review.sh`,但不改内核):

```bash
bash scripts/agent-review.sh --repo <产品仓> --days 7            # 写收据,有信号才起草
bash scripts/agent-review.sh --repo <产品仓> --dry-run           # 先看不写
```

它只读(留痕 + 指标 + 已有提案),产出:

| 产物 | 内容 |
|---|---|
| `state/reviews/agent-review-latest.md` | 信号 + 指标快照 |
| `state/reviews/agent-review-status.env` | `signal=yes|no`,供定时任务判断要不要出声 |
| `state/proposals/<NN>-agent-<日期>.md` | **仅在有硬信号时**,一份 `status: draft` 的草稿 |

草稿里「要改什么 / 不改什么 / 依据哪些留痕 / 是否动登记表」**全部留空给人填** ——
脚本提供证据和骨架,**不决定改什么**。那是人和 grill 的事。

超龄未 grill 的 draft 也算硬信号(和内核一样):永远不被拷问的提案本身就是个问题。

**它不改定义、不改登记表、不改 ledger,也不 land 任何提案。** `conductor_revision + 1`
与把提案标 `landed` 都只能由人做。

## 七、长期打磨:改哪里由数据说

跨票聚合,排出最该改的那一项。这是"长期打磨"的依据 —— 不靠感觉,靠计数。

```bash
python3 scripts/agent-metrics.py --repo <产品仓>              # 当前仓所有票
python3 scripts/agent-metrics.py --repo <仓> --days 30
python3 scripts/agent-metrics.py --repo <仓> --by kind        # 按 kind 而非 agent 排
python3 scripts/agent-metrics.py --repo <仓> --trend          # 按周看密度是否在降
python3 scripts/agent-metrics.py --repo <仓> --unused         # 登记表里从未跑过的行
```

输出按「问题密度」降序:`(blocked + retried + rejected + check_fail) / delegated`,
并带每行的耗时中位数与单次最长。

`--unused` 要单独看一眼:从未跑过的 agent 或 kind 意味着**它从未被真实验证过** —— 第一次
用上时才发现定义有问题,那是代价最高的时刻;或者那一行本来就多余,登记表该精简。
**不要因为「没出问题」就当它是好的:没跑过的路径不算验证过。**

| 读到什么 | 下一刀 |
|---|---|
| 某 agent 的 `blocked_brief` 高 | 改**委派包格式**,不是改那个 agent |
| 某 agent 的 `blocked_env` 高 | 产品仓缺东西(`workflow-defaults` 键 / 巡检包),改产线 `.idev/` |
| 某 agent 的 `retried` 高且 `prompt-unclear` | 改该 agent 定义的步骤表述 |
| 某 kind 的 `wrong-agent` 反复出现 | 改 `kind_agents.py` 的登记表一行 |
| 某 agent 的 `agent-overstep` 出现 | 先收紧 `tools`,再在硬规则里重述边界 |
| `no-signoff-write` 任何一次 | 立刻停,按硬信号走提案,不要只改一行 prompt |

**优先级原则:** 先改委派包(一处改动影响全部 agent),再改登记表(一行),最后才改 agent
定义(五份里的一份)。改动面从小到大,与内核「扩展 = 登记表加行」同一思路。

## 八、提案路径(沿用内核,不新开目录)

| 范围 | 目录 |
|------|------|
| 某个产品上的委派层草稿 | 该工程 `.idev/proposals/`(须已有 `marker: idev`) |
| 改 agent 层自己、且没有当前产品 | 本仓 `state/proposals/<NN>-<slug>.md` |

提案必须写:要改什么 / 不改什么 / 依据哪些 delegation 留痕 id(或 agent-feedback id) /
是否动 `kind_agents.py` 登记表。

只许改:登记表加行、agent 定义的硬规则或步骤澄清、委派包格式、文档指针。
**不许**在提案里顺手改内核。

land 后在入口台账 `state/ledger.yaml` 把 `conductor_revision + 1`,提案标 `landed`(合并进 idev 后不另开 agent 层的 revision —— 台账只有入口这一份)
—— 由**人**标,不是 AI。

## 九、禁止

- 用 LLM 给 agent 回报打分,或拿分数当是否 record 的门禁
- 把一次失败直接写成 agent 定义的新硬规则(先留痕 → 够 2 次 → 提案 → grill)
- agent 自己改自己的定义文件(定义是人 + 提案流程的产物)
- 每步委派都停问 feedback(违反内核 H5;整轮一次)
- 留痕里存摘要而非 `brief` / `report` 原文(存了摘要就没法重放,留痕白做)
- 为了让 `check_fail` 归零去放宽五项检查
- 把 `brief-complete` 的失败算在 agent 头上(那是导体的锅)
