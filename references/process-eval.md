# 流程机制评估

停下来问人之前，先判断这一步是低效、不合理，还是在替较弱的模型付代价。

当轮能按已经写明的规则改的，立刻改。要改规则，只写成提案。不打分，不看模型名字，不自动改 Skill。

本页是这套判断的权威。脚本是 `scripts/process-eval.py`。补丁登记在 [scaffolds.yaml](scaffolds.yaml)。提案怎么落地仍走 [self-evolution.md](self-evolution.md)：grill 之后人确认才改真源。

## 何时跑

停下来问人之前：

```bash
python3 scripts/process-eval.py stop --stop "<将要问的那句>"
```

人已经回了一句：

```bash
python3 scripts/process-eval.py stop --quote "<原话>" --stop "<将要记下的 stop>"
```

打开的步骤是决策闸（`with.decision: true`）时加 `--decision`。目前是提交推送和自进化落地。`next` 打出 `DECISION` 就带上，没打出不要带。

看最近的轨迹，重复出现才起草：

```bash
python3 scripts/process-eval.py scan --traces <traces 目录> [--window 50]
python3 scripts/process-eval.py scan --traces <traces 目录> --delegations <委派留痕目录>
python3 scripts/process-eval.py scan --traces <traces 目录> --except <起草时用过的文件名> --propose
```

`scan` 的结果也写进 `evolve-review.sh` 的复盘正文。`later=PROPOSE` 不抬那份复盘的 signal。要草案再加 `--propose`。

## 输出

第一行是 `PROCESS`。件数不是分数。

| 字段 | 含义 |
|------|------|
| `now=ASK` | 停下来问 |
| `now=CORRECT` | 按 `rule` 点名的既有规则做，不问 |
| `now=KEEP` | 没有要判断的停问。`scan` 的第一行不写这个 |
| `later=PROPOSE` | 可以起草。`--propose` 才写文件 |
| `later=` | 这一次不起草 |
| `unproven=` | 样本不够，不提议删除 |

`FINDING` 行上的 `now=KEEP` 是另一回事：这个补丁还在挡住失败，不准收窄。

`DO` 那一行是当轮要做的事。`rule=H1` 做还开着的事，不改密封基线的 goal / items / non_goal，不记 stop，不写 next。`rule=chat-confirm` 把这一步做完；检查没过就改到通过。

矛盾、冲突、不清楚、解封、回退、promote、生产写、`git push`、经验入库，以及 `frontier` / `BLOCKED` / `SIGNAL` / `未决` / `承重`，都是 `ASK`。这些词出现时不做 `CORRECT`。

## 三类

| kind | 是什么 | 当轮 | 重复 |
|------|--------|------|------|
| `waste` | 催办被记成了 stop 或 next | `CORRECT`，`rule=H1` | 同一 id ≥ 2 才 `PROPOSE`。不放宽 nudge 校验 |
| `unreasonable` | 停点落在下面的句子里 | `CORRECT`，`rule=chat-confirm` | 同一 id ≥ 2 才 `PROPOSE` |
| `scaffold` | [scaffolds.yaml](scaffolds.yaml) 里的补丁 | 失败还在就 `KEEP`，不删 | 代价还在付、要挡住的失败一次都没有，才 `PROPOSE` 收窄 |

不是停点的句子，脚本只认这些子串：

- 审查签收
- 实现审核
- 测试结果确认
- 文档定稿
- 要不要继续
- 是否继续
- 请确认通过
- 要不要提测
- 是否验收
- 请验收

前四条与 [chat-confirm-signoff.md](chat-confirm-signoff.md) 一致。增减句子时改本页，并改脚本里的 `NON_STOPS`。

`stop-on-nudge` 看相邻两条轨迹：上一条停在非决策问题上，下一条原话只是催办。人被多问了一轮，就是代价。催办本身又被写成了 stop，校验仍在挡住失败，这时 `KEEP`，提议去找那个写入点，不删校验。

`context-replay` 看委派留痕里 `attempt` 大于 1。`prior_failure` 写着没读、未打开、重读或忘记，补丁就还在干活，`KEEP`。重试发生了，失败原因却不是没读，才提议不要为这种重试整段重放。没给 `--delegations` 就是 `UNPROVEN`。

## 面向更强的模型

补丁是为某一种失败留下的代价。模型变强，只认下面两件同时成立：

1. 代价还在付。人仍要为这一步再花一轮，或者重试仍在重放。
2. 这条要挡住的失败，在窗口里一次都没有。

不认模型名字，不认自评分数。没有样本不能当成已经变强。

`--propose` 写下的草案带 `accept: later`。草案里点名的轨迹是起草证据，不能再拿来接受这条提案。用 `--except` 排除它们之后再扫，条件仍成立，才算另一份结果。排除之后条件不成立，脚本不写草案。

已经有一份未关闭的流程草案时，不再写第二份。

## 不做什么

- 不改 SKILL、schema、`ledger.phase`
- 不打分，不用模型自评当门禁
- 不因为换了一个更强的模型名字就删步骤
- 不把一次 `CORRECT` 写成规则变更
