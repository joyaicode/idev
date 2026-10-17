# 外部工具的边界:Langfuse / promptfoo / DSPy

这三样都有用,但**它们的默认用法里有一部分与内核规约正面冲突**。这页写清各自接到哪一步、
为什么停在那里。

内核的四处明文禁令(不是建议):

- `references/self-evolution.md:3` 「**不照搬** DSPy/GEPA 栈,也**不**用 LLM 打分当门禁」
- `references/self-evolution.md:94` 「v1 **不做** GEPA/DSPy 自动改写」
- `verify/references/evolve.md:4` 「禁止:Skill 根据一次聊天自行改自己、用分数当门禁、
  用 LLM 自评代替人确认」
- `references/cohesion.md` 入口 traces 一行:禁止「分数、签字、第二套 eval」

---

## 一、Langfuse —— 只做导出器

```bash
python3 scripts/langfuse-export.py --feature <f> --out /tmp/t.json
python3 scripts/langfuse-export.py --repo <仓> --days 7 --out /tmp/week.json
python3 scripts/langfuse-export.py --feature <f> --post    # 需要 env + SDK
```

映射(语义不丢):

| idev | Langfuse |
|---|---|
| 一次 run(一张票的 workflow) | trace |
| 一次委派(step + attempt) | 该 trace 下的 span |
| `checks` / `BLOCKED(类)` / `metrics` | span metadata |
| `duration_s` | span 的 start/end |
| 回报 `STATUS` | span level(DEFAULT / WARNING / ERROR) |

**为什么是离线导出而不是实时上报:** 交付路径不能长出网络依赖。如果一轮委派会因为可观测
服务挂了而失败,**可观测性就变成了门禁** —— 而这一层的规矩是它永远不是。留痕本来就先落盘,
要去别处看的时候再导。

**默认不导 `brief` 与 `report` 正文。** 委派包是这一层最敏感的产物 —— 它带产品源码路径、
票内容,有时还有近乎凭据的路径。默认把它发给第三方,是在替你做一个不该我替你做的决定。
你自己判断过了就加 `--include-bodies`。

**不导任何分数。** 只有件数与状态。

## 二、promptfoo —— 只做回归断言,不打分

```bash
python3 scripts/promptfoo-gen.py                  # 生成配置
npx promptfoo@latest eval -c state/promptfoo/promptfooconfig.yaml
npx promptfoo@latest eval -c state/promptfoo/promptfooconfig-refactor.yaml
```

生成两份配置,**0 个评分**。断言全是 `contains` / `not-contains` / `regex`,
外加**唯一一条会执行的** `python` 断言(C-3),人能逐条读懂:

- 基础矩阵:5 个 prompt(每个 agent 定义的正文)+ 60 条断言 —— 回报含
  `STATUS` / `EVIDENCE` / `CHECKS` / `SUGGEST`;`STATUS` 可机读
  (`PASS|FAIL|UNPROVEN|BLOCKED(类)`);`FACTS_AGENTS` 另含 `FACTS:` / `DOC_DRIFT:`,
  且**不许**出现 `FACTS: 看了文档`;`idev-coder` 另含 §0 三项交代;
  **任何 agent 都不许声称写了** `sealed`/`accepted`/`aligned`/`resolved`
- 重构轮(promptfooconfig-refactor.yaml,只钉 idev-coder):5 探针 92 断言 ——
  C-1 无护栏的改动被拒或被要求先补护栏(R1);C-2 一张票两件事被拆轮(R3);
  C-3 纯结构重构由 r2_check.py **真执行**:回报里的模块对 guard_r2.py 双跑,
  前后输出逐字节一致才算过(R2);C-4 review.fix 声明 RED_FIRST 且非「无」;
  C-5 密封基线不进 CHANGED(营地规则)

**为什么不用它的评分能力:** 让模型评「这份审查有没有洞见」,正是 `evolve.md:4` 禁止的
「LLM 自评代替人确认」。所以配置里没有一处 `llm-rubric`。

**它答的是「改了定义之后回报还合规吗」,不是「回报写得好不好」。** 后者只能靠真票 ——
见 [agents-todo.md](agents-todo.md) 的 P1。

两者分工:`agent-smoke.sh` 测**脚本与契约**(481 条,不需要模型);promptfoo 测
**定义改动后模型的实际输出**(需要 provider key;本机未装,eval 需联网 `npx` 装)。
生成器本身由 `scripts/test_promptfoo_gen.py`(10 条)与 `test/promptfoo/test_r2_check.py`
(9 条)零依赖锁住,不跑 eval 也能验证配置形状。

## 三、DSPy —— 不装,只借思路

DSPy 的价值是 **signature(结构化 I/O)+ optimizer(按分数自动改 prompt)**。
第二半正是内核禁的两条:自动改 Skill、分数选优。

所以不装。但它的三个有效成分,这一层已经各有落点:

| DSPy 的成分 | 这一层的对应 | 差别 |
|---|---|---|
| signature:声明输入输出的结构 | agent 定义的**回报格式** + `delegation.py` 的五项检查 + promptfoo 的 152 条断言 | 一样是「声明结构然后校验」,但校验结果是 PASS/FAIL,不是分数 |
| metric:拿一个数衡量好坏 | `agent-metrics.py` 的**问题密度** + `check_fail` 件数 | 是**件数**不是质量分;它指向「下一刀改哪里」,不决定「哪个 prompt 更好」 |
| optimizer:按 metric 自动改写 | `agent-review.sh` 起草提案 → **grill** → **人确认用语** → land | **人在回路里**,这是整条线不可替换的一环 |

**为什么不做自动改写:** 不是技术顾虑。`evolve.md` 的那条禁令针对的是一种具体的失效 ——
用分数代替理解。一个分数变好了而没人知道为什么,下次它变坏时同样没人知道为什么。
拷问这一步的产出不是「批准」,是**理解**。

要做的话,先正面改上述四处禁令,并想清楚:谁来回答「这次改好了」之外的那个问题 ——
「为什么」。

---

## 共同的判据

接一个外部工具之前问三件事:

1. **它会不会让交付路径依赖一个可能挂的服务?** → 会就改成离线
2. **它产出的是分数还是事实?** → 分数就只能当信号,不能当门禁
3. **它会不会把「人确认」替换成「某个数达标」?** → 会就不接

这三条不是对工具的偏见,是 `conventions/evidence.md` 那条可信度表的直接推论:
**AI 反馈不可信,它只是待证命题。** 一个模型给出的分数,也是 AI 反馈。
