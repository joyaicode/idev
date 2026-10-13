# 这一层的失败模式(审查清单)

连续几轮审查下来,本层找到的问题几乎全是同一类:**检查在该报警的时候保持了沉默**。

这比崩溃危险得多 —— 崩溃你会去修,沉默让你以为检查在工作。委派层的全部价值就是"能查出
agent 做错了什么",所以一个静默失效的检查不只是少了一个功能,它是在**提供虚假的保障**。

下面每条都配本仓的真实实例。改这一层之前扫一遍。

---

## 一、shell:`&&` 吞掉条件

```bash
[ "$n" -ge "$max" ] && max=$((n + 1))     # 条件为假 → 整句非 0 → set -e 杀掉脚本
```

`set -e` 下,`a && b` 作为完整语句,a 失败就让整句返回非 0。

**实例:** `agent-review.sh` 的提案编号逻辑。只要 `state/proposals/` 里有一个编号小于当前
计数的文件就触发 —— 而那在多次复盘后几乎必然发生。脚本会在"一切正常"的情况下死掉。

**防:** 用 `if` 块。`&&` 只写在 `if`/`while` 的条件位置,不要当语句用。

## 二、shell:`|| true` 吞掉错误

```bash
out="$(some-tool 2>&1 || true)"
if echo "$out" | grep -q 'signal=yes'; then ... else SIGNAL=no; fi
```

工具挂了 → 没有 `signal=yes` → 报告 `signal=no` → 读起来是"一切正常"。

**实例:** `agent-review.sh` 调 `agent-metrics.py`。**一个复盘回路最不该给的答案,就是把故障
说成一切正常。** 现在失败就 `exit 2`;连 `signal=` 行都没有(输出格式变了)也同样拒绝给结论。

**防:** 工具失败就失败。`|| true` 只用在"这一步失败确实无所谓"的地方,而且要写明为什么。

## 三、正则:未锚定导致子串误匹配

```python
NO_HIT = re.compile(r"零命中|none|^-$")     # "nonexistent" 含 "none"
```

**实例:** `TABLE_HIT: §1 nonexistent-row` 被判成"零命中",`hit-applied` 整个跳过(漏检);
反过来 `CANON_TRIGGER: 无(纯追加)` 因为锚定太死而被判成"有 trigger",要求 `review.md` 里有
`T#`(误报)。**同一个正则两个方向都错。**

**防:** 匹配"整个字段值"时锚定到两端,并显式允许常见的附注形式(括号说明)。写完各造一个
正例和一个反例当场验。

## 四、异常:只防了一半

```python
try:
    record = yaml.safe_load(text) or {}
except yaml.YAMLError:          # 防了解析失败
    skip()
record.get("agent")             # 合法 yaml 的 list 走到这里才崩
```

**实例:** `agent-metrics.py`。合法 YAML 的列表不抛异常,解析成功,然后 `.get()` 在 list 上崩。
smoke 当时只喂了语法坏的 yaml,所以这个洞测不出来。

**防:** 防护要覆盖"解析失败"**和**"解析成功但形状不对"。本层统一走
`safeyaml.mapping()`,它两样都管。

## 五、名字:硬编码导致改名后静默失效

```python
if record.get("agent") != "idev-coder":   # 改名后这里永远不匹配
    return {}                              # 四项检查静默消失,零报错
```

**实例:** `delegation.py` 的 §0 检查。coder 一旦改名,`KIND_AGENTS` 会跟着改、留痕里是新名,
而这里的比较永远为假 → 检查全部静默关闭。

**防:** 名字进 `kind_agents.py` 当真源(`S0_AGENT` / `BOOST_AGENTS` / `READONLY_BREAKS`),
`agents-check.py` 验证它们确实在 roster 上。**派生表只能点名真实存在的 agent。**

## 六、检查自己没被测

一个从不触发的检查,和没有检查没有区别 —— 但它看起来像有保障。

**实例:** `agents-check.py` 原先无法测,因为 `AGENT_DIR` 硬编码指向真实的 `agents/`,造负例
要改坏真文件。加了 `--agents-dir` 之后,smoke 现在喂进 6 种坏定义逐个断言被抓到。

**防:** 每个检查都要有**反向断言** —— 断言它该红的时候真的红。本层所有校验点都配了负例:
派错 agent、委派 `human.gate`、PASS 无证据、声称写了 `accepted`、嵌套 metrics、同签名三次、
`proven` 却没复现、省略 `tools`……

## 七、工具权限的边界会被配置静默绕过

```python
tools = tool_set(fields)
if tools is None:            # 省略 tools = 继承全部
    warns.append(...)        # 只给警告 → 禁令整个跳过
```

**实例:** 删掉 `idev-runner` 的一行 `tools`,它就继承全部工具、悄悄拿到 `Write`/`Edit`,
而检查只给个警告。现在对有 `TOOL_BANS` 的 agent,`tools` 是必填。

**防:** 「省略即放开」的字段,在有禁令时必须变成必填。

## 八、为了让测试变绿而写错断言

**实例:** 我自己犯的。新加 `expect 0 "check survives a yaml-list record"`,但票里已有故意留下的
FAIL 留痕,`check` 必然返回 1。改成 `expect 1` 后,这条断言反而更有价值:它同时验证了
**坏文件被跳过** 且 **真实 findings 仍被报告** —— 卡住了"为了不崩而把什么都放过"这个退化方向。

**防:** 断言写出来之后,问一句"它为什么应该是这个值",而不是"怎么让它过"。
测试跟着实现改,是在把实现的 bug 固化成规格。

---

## 本层特有的两条

**九、跳过不等于沉默。** 坏文件可以跳过(一条坏留痕不该让 timeline 对另外十九条失效),
但必须 `WARN` 出来。smoke 为此专门断言 `contains "WARN"`。

**十、「可观测性」不能变成门禁。** 时序字段(`started_at` / `finished_at`)是可选的 ——
少一个时间戳不该挡住一次正常委派。但 `timeline` 和 `eval` 必须**明说有多少次没计时**,
否则你会以为耗时数据是全的。缺数据和没问题是两件事。

---

## 十一、命令替换里嵌 heredoc:括号会参与配对

```bash
D="$(mkbad case foo.md <<MD
---
正文里有一个 BLOCKED( 括号
MD
)"
```

bash 为了找 `$(` 的闭合 `)`,会扫描内容并**把 heredoc 正文里的 `(` 算进配对**。于是正文里
一个孤立的左括号,就让收尾的 `)` 去闭合了它,`"` 悬空 —— 而报错位置在**几百行之后的文件尾**:

```
smoke.sh: line 867: unexpected EOF while looking for matching `"'
```

**实例:这是本层最严重的一个 bug。** `smoke.sh` 段 7 的一个 fixture 正文含 `BLOCKED(`,
导致**整个 smoke.sh 无法解析**。后果不是少测一项,而是:

> 验证入口一行都没执行过,而我连续几轮都在说「smoke 会验证这些」。

一个不能解析的脚本不会执行任何断言,而 bash 在你真去运行它之前**什么都不说**。这是
「检查自己没被测」(第六条)的最极端形式 —— 连语法都不对。

**防:**

1. **不要用 `$()` 包 heredoc。** 函数要回传路径就设全局变量,不要 `printf` 出来再捕获。
2. **改完脚本必跑语法预检**,它在 smoke 之前:
   ```bash
   bash scripts/syntax-check.sh
   ```
   `bash -n` 和 `ast.parse` 都是纯解析、零副作用 —— 没有理由不跑。
3. fixture 不要掺奇怪字符。那条 fixture 本身还自相矛盾:它声称「没有 BLOCKED 分类」,
   却在正文里写了 `BLOCKED(`,于是连它要测的东西都测不到。

**元教训:** 任何「X 会验证这些」的说法,前提是 X 真的跑过。没跑过的保证不是保证,
是愿望。本层的验证顺序因此固定为:`syntax-check` → `agents-check` → `smoke`,
前一道过不了,后面的结论一律不成立。

## 十二、把「空」和「不存在」混为一谈

```python
def read_evidence(...) -> str:
    ...
    return ""          # 找不到文件 → ""
# 调用处
if not review:         # 空文件也走这里
    out["canon-walked"] = "WARN"
```

空字符串和「文件不存在」是**两个不同的事实**,合并之后判断就错了:

- 文件不存在 → 这里判断不了 → `WARN` 合理
- 文件存在但是空的 → 明确的「`T#` 不在里面」→ 应该 `FAIL`

**实例:** `canon-walked` 对一个空 `review.md` 返回 PASS(经 WARN 路径),等于**宣称 agent
走过了 canon 协议,而证据文件里什么都没有**。这是 smoke 跑起来之后抓到的第一个真实现 bug,
也是本页第一条「只靠读代码没发现、靠运行才发现」的问题。

**防:** 返回类型写成 `str | None`,`None` 表示「取不到」,`""` 表示「取到了,是空的」。
在注释里写明两者为什么不能合并 —— 否则下一个人会"顺手简化"回去。

Python 里 `not x` 对 `None`、`""`、`[]`、`0` 一视同仁,这类合并很容易无意中发生。凡是
「拿不到」和「拿到了但是空」会导向不同结论的地方,都要分开。

---

## 元教训:只有运行才能发现的那一类

第十一条(语法错)和第十二条(空 vs 不存在)有个共同点:**读代码读不出来**。

第十一条我扫了引号配对、检查了段结构、确认了文档链接,全都"看起来对" —— 直到 `bash -n`
一跑,才发现整个文件无法解析。第十二条我写的时候推理是"读不到就 WARN",逻辑自洽,只有在
一个恰好存在且为空的 `review.md` 上才暴露。

所以:**静态审查和运行验证不能互相替代**。审查能找出设计缺陷和逻辑漏洞,但"这个分支在真实
输入上会走到哪"只有跑过才知道。smoke 第一次真跑就抓出 1 个实现 bug + 2 个测试 fixture 问题,
而在那之前它自己是坏的 —— 这两件事合起来说明了为什么验证顺序必须是
`syntax-check` → `agents-check` → `smoke`,一道都不能跳。

---

## 怎么用这页

改本层代码之前扫一遍,尤其在:加一个新检查、加一个 shell 脚本、写一个解析用的正则、
或者让一个失败的测试变绿的时候。

改完**按顺序跑三道**,不要只跑最后一道:

```bash
bash scripts/syntax-check.sh
python3 scripts/agents-check.py
bash scripts/smoke.sh
```

发现新模式就加一条,并配本仓实例 —— 没有实例的条目是教条,过两个月就没人信了。
