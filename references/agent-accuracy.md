# 准确率:从 Cursor / Claude Code 借来的机械护栏

这两个 agent 在编码、测试、根因上准,主要**不是**因为 prompt 写得好,而是因为**工具边界上有
硬约束**:

| 它们的护栏 | 挡住了什么 |
|---|---|
| `Edit` **拒绝**编辑本轮没 `Read` 过的文件 | 盲改 —— 凭印象改一个没看过的地方 |
| `Edit` 要求**唯一精确字符串**,匹配不上就失败 | 改错位置而不自知(静默改坏) |
| plan mode:**先定方案再动手**,人点头才做 | 做完才发现方向错,整轮白费 |
| checkpoint / rewind:每次改动**可撤销** | 搞乱了无法回退,只能手工补救 |
| 独立工具调用**一条消息里并发** | 五次顺序 grep 的等待 |

这些都是**机械的**:不依赖 agent 自觉,不依赖它记得某条规矩。

我们这一层的对应杠杆是**回报契约 + `delegation.py` 的机检**。所以下面把那几条护栏翻译成
「声明 + 机检」,而不是翻译成「请你注意」。

**代价要说清:** 回报字段变多了。但替代方案是 agent 静默做错事,然后你花十倍时间找原因。
每个字段都是一行,而且都能被机器判 —— 不是写给人看的仪式。

---

## 编码:四条护栏

### 1. 先定范围,再动手(`SCOPE` ↔ `CHANGED`)

plan mode 的本质不是「加一步确认」,是**让方案在动手前就是显式的**。

`idev-coder` 动手前写 `SCOPE:`(这轮打算改哪些 file:symbol),完事写 `CHANGED:`。
机检 `scope-held` 比较两者:**`CHANGED` 里有 `SCOPE` 之外的文件就 FAIL**。

这挡的是**范围蔓延** —— 编码 agent 最常见的失效:本来改一处,顺手又"优化"了三处,
其中一处破坏了别人的假设。`conventions/coding.md` 的「只改 `include: true`」是同一个意思,
但那是 prompt 级的;这一条是机器判的。

### 2. 读了才改(`READ` ↔ `CHANGED`)

Claude 的 `Edit` 在工具层强制这件事。我们在回报层:`READ:` 列出改之前读过的
`file:symbol`,机检 `read-before-change` 要求 **`CHANGED` ⊆ `READ`**。

改一个没读过的地方,十次有九次是按文件名或函数名猜它在干什么 —— 而
[boost.md](boost.md) 第零节的全部要点就是:**名字和文档都不可信**。

### 3. 报锚点,不只报文件(`file:symbol`)

`Edit` 要求唯一字符串的用意是**失败要响**:匹配不上就报错,绝不改到相邻的相似位置。

所以 `SCOPE` / `READ` / `CHANGED` 都写 `路径:符号`,不要只写路径。
「改了 `service.py`」没有信息量,「改了 `service.py:resolve_token`」才让导体能核对。

### 4. 每次委派可撤销(`REVERT`)

checkpoint 是 Claude Code 和 Cursor 都有的东西,我们**原来什么都没有** —— agent 把代码改乱了,
你只能手工找回来。

改代码的委派必须给 `REVERT:`:动手前的 base commit,或 `git stash` 的 ref。
机检 `revert-anchor`:**`CHANGED` 非空却没有 `REVERT` 就 FAIL**。

```bash
git rev-parse HEAD          # 动手前记下来,这就是 REVERT 的值
```

这一行让「这个 agent 干的事全部撤掉」变成一条命令,而不是一次考古。

---

## 测试:先红后修

`conventions/evidence.md` 第 4 步原文就要求「先设计用例,再编码」,第 5 步要求根因
「能用用例红/绿切换」。但它以前只在散文里。

`review.fix` 这类**修复**步骤的回报必须有 `RED_FIRST:`:修之前那条用例红过,以及它的日志路径。
机检 `red-first`。

**为什么只对修复类要求:** 实现新功能时没有"原现象"可红。但修一个 bug 而没见它红过,
你其实不知道自己修的是不是它 —— 这是 `evidence.md` 整页在反复说的那件事。

另外两条已有的不重复:维度表先铺满骨架(`verify.plan`)、失败签名归一化 + 有界修复红线
(`failure_signature.py`)。

---

## 根因:二分 + 把猜测浮出来

### 二分定位

Cursor / Claude Code 的 agent 在"这问题哪来的"上强,很大程度靠**二分**而不是通读。

**本次会话的真实例子:** `smoke.sh` 报 `line 867: unexpected EOF`,而真正的错在 530 行附近。
我扫引号配对、查段结构、看文件末尾,全都「看起来对」。换成二分立刻定位:

```bash
for n in 150 350 445 560 605; do
  head -n $n scripts/smoke.sh | bash -n 2>&1 | grep -q matching && echo "$n 有错"
done
```

两轮就把范围缩到 15 行。可用的二分维度:

| 维度 | 怎么二分 |
|---|---|
| 哪次提交引入的 | `git bisect start <坏> <好>` |
| 文件哪一段有问题 | `head -n N` + 复跑(语法/加载类问题) |
| 哪个配置项导致的 | 砍掉一半配置再试 |
| 哪条 case 污染了状态 | 只跑前一半 |
| 哪个依赖的版本 | 锁一半版本再试 |

**判据:当「通读找原因」超过两轮没有收敛,换二分。** 通读的成本随代码量线性涨,
二分是对数的。

### 把猜测浮出来(`ASSUMED`)

这是 Claude 的一个实质优势:**它会说「我不确定」**,而不是把猜测写成结论。

`ASSUMED:` 列出这轮做了什么假设(没验、但结论依赖它)。写「无」也算交代。
机检 `assumption-declared`。

效率上这是**净赚**:导体只需核那一条假设,而不是把整份回报重验一遍。
它也防住一类隐蔽错误 —— agent 推理每一步都对,只是最开头的前提是猜的。

---

## 效率:批量只读探测

Claude Code 的做法:**独立的工具调用放在一条消息里并发**。五次顺序 `Read`/`Grep` 是五倍等待。

| 不要 | 要 |
|---|---|
| grep 一次 → 看结果 → grep 下一次 | 一条消息里发完所有独立的 grep/read |
| `codegraph_search` → `node` → `callers` → `callees` 四连 | **一次 `codegraph_context`** 就返回入口 + 相关符号 + 关键代码 |
| 读完一个文件再决定读下一个 | 能一起定的路径一起读 |

codegraph 的 MCP 说明里原话就是:`codegraph_context` 是 PRIMARY,一次调用顶四次链式调用。

**这不违反「不并行」。** 内核 `canon.md:181` 反对的是**多开 agent**(合并成本高于省下的时间),
不是反对一次读多个文件。工具调用并发没有合并成本。

---

## 这几条分别落在哪

| 护栏 | 字段 | 机检 | 谁 |
|---|---|---|---|
| 先定范围 | `SCOPE` | `scope-declared` · `scope-held` | coder |
| 读了才改 | `READ` | `read-before-change` | coder |
| 可撤销 | `REVERT` | `revert-anchor` | coder |
| 先红后修 | `RED_FIRST` | `red-first`(仅 `review.fix`) | coder |
| 浮出猜测 | `ASSUMED` | `assumption-declared` | coder · ops · reviewer · verifier |
| 二分 | — | 无(是方法,不是字段) | ops |
| 批量探测 | — | 无(是效率,不该做成门禁) | 全部 |

后两条刻意**不做机检**:二分是该用时用的方法,批量是习惯。把它们做成门禁只会产生凑数的
声明,而不是真的用了 —— 那正是 [failure-modes.md](failure-modes.md) 反复警告的那种假绿。

---

## 没借的,以及为什么

| 它们有的 | 为什么不借 |
|---|---|
| 并行 agent / worktree 隔离 | `canon.md:181` 的反模式;串行委派是本层的既定选择,见 [agents-todo.md](agents-todo.md) P3 |
| 自动 apply diff(Cursor 的 apply 模型) | 我们不插在编辑器里;agent 直接用 `Write`/`Edit` |
| 浏览器看 UI | 产品专有,属 `ui.lifecycle_run` 的 e2e;真要看页面是产线的事 |
| LLM 评分 / rubric | `evolve.md:4` 明文禁止,见 [external-tools.md](external-tools.md) |
| 嵌入式语义检索 | codegraph 已覆盖;再加一套索引是第二套真源 |
