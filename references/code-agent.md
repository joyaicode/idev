# CodeAgent:用代码表达推理

散文推理不是证据。**算出来的结果 + 能重跑的脚本才是。**

这是 `conventions/evidence.md` 那条可信度表的直接推论:「分析、论证、推测都只是待证命题,
必须带辅助证据」。一段关于数据的散文推理,仍然只是散文。

和 [boost.md](boost.md) 第零节是同一条线:那边讲**事实从哪来**(别信文档),这边讲
**推理怎么做**(别靠脑补)。

---

## 什么时候该写代码而不是写句子

| 你要回答 | 散文版(不要) | 代码版 |
|---|---|---|
| 这张票还有几条 UNPROVEN | 「大部分都过了,剩几个没证」 | 读 `plan.yaml` 数出来,贴数字 |
| 哪些 slice 没挂 baseline item | 「看着都挂上了」 | 两边取集合差,贴差集 |
| 这次比上次多跑了什么 | 「比上次多一些」 | 两份 run 的 case id 做差 |
| 维表六族覆盖到哪 | 「主要维度覆盖了」 | 按维分组计数,贴每维条数 |
| 这个符号被谁调用 | 「应该是 X 调的」 | `codegraph_callers`,贴列表 |
| 配置在三个环境里一致吗 | 「应该一致」 | 读三份,diff,贴不同项 |

**判据很简单:答案是一个数字、一个集合、一份清单 → 写代码。** 口算和目测在
二十条以内看起来可靠,而人恰恰在二十条上下开始出错,还不自知。

---

## 怎么用

```bash
python3 scripts/repl.py run --feature <f> --step <step> --note "数一下 UNPROVEN" <<'PY'
import safeyaml
plan = safeyaml.mapping(TICKET / "verify" / "plan.yaml") or {}
cases = plan.get("cases") or []
from collections import Counter
print(Counter(str(c.get("status", "未跑")) for c in cases))
print("无 baseline_item_id:", [c.get("id") for c in cases if not c.get("baseline_item_id")])
PY
```

落两个文件,都在票目录里(跟着票走,`execution-clean` 不碰):

```
<票目录>/repl/<step>-<n>.py     源码原文
<票目录>/repl/<step>-<n>.out    stdout + stderr + 退出码 + 耗时
```

`.out` 的路径就是你回报里的 `EVIDENCE`。**别人能重跑同一份源码得到同一个答案** ——
这才是它算证据的原因。

preamble 已经给好 `IDEV` / `REPO` / `TICKET` 三个 `Path`,并把 idev 的 lib 放进
`sys.path`,所以 `safeyaml`、`doc_home`、`workflow_spec` 直接 import 就能用,
不要自己拼路径。

```bash
python3 scripts/repl.py list --feature <f>              # 这张票算过什么
python3 scripts/repl.py show --feature <f> --step <s>   # 回看某次
```

---

## 三条硬规则

### 1. 不写签字字段 —— 这是代码层的禁令,不是约定

`workflow_spec.is_human()` 的黑名单正是 `{agent, ai, cursor, assistant}`,**agent 签字在
代码层就被拒**。REPL **不得成为绕过它的路**。

snippet 里出现 `accepted: True`、`sealed = "true"` 这类写法,`repl.py` 在**执行之前**就拒,
一个字节都不会跑。写票 YAML 同理被拒 —— 工件用 agent 自己的 `Write`/`Edit`,台账用
`hypothesis.py` / `failure_signature.py`。

### 2. 不是第二套测试框架

verify 模块独占红绿(它的硬规则 10:不要第二套断言引擎)。snippet **算事实**,
「这条 case 过没过」仍然只有 `verify.run` 能回答。

区别在于:数一数有几条 UNPROVEN 是算事实;断言某条 case 应该绿,是红绿。

### 3. 算出来的东西要贴出来

`FACTS:` 里写 `repl <路径>`,`EVIDENCE:` 指向 `.out`。**只说"我算了一下"不算** ——
那又退回散文了。

---

## 它不是什么

**不是沙箱。** 那个签字守卫是静态扫描,是和本层其它诚实性检查同一种性质的**绊线**,
不是隔离边界。真隔离要容器;假装一个正则提供了隔离,比明说没有更糟。

所以:**snippet 只用来算你票目录里的事实**。要跑产品构建、启停服务、改代码,那是
`idev-coder` 和 `idev-verifier` 的命令步骤,不是这里。

**不是门禁。** 它不挡任何一步,只产出证据。

---

## 谁能用

`idev-ops`(论证/排障)、`idev-verifier`(红绿计数)、`idev-coder`(影响面核算)、
`idev-reviewer`(命中统计)—— 就是 `kind_agents.FACTS_AGENTS` 那四个,和必须交代
`FACTS:` 的是同一批。

`idev-deliver` 不用:它的产出是文档和票 YAML,不是算出来的事实。

---

## 不要

| 不要 | 为什么 |
|---|---|
| 用 snippet 改票 YAML 或写签字字段 | 执行前就被拒;用 agent 自己的工具 |
| 用 snippet 跑产品测试 / 构建 / 启停 | 那是命令步骤,有它们自己的 kind 和落点 |
| 算完不贴路径,只在回报里写结论 | 退回散文,`facts-first` 会抓 |
| 为了绕过守卫把字符串拼起来 | 守卫是绊线不是围墙。绕过它等于自己放弃了这层保障 |
| 把 snippet 当成 agent 的记忆 | 它是一次计算的留痕。要跨轮记住的东西写假设台账 |
