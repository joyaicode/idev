# 提效三板斧(编码 / 测试 / 根因)

把规约里**已经要求、但以前只能靠自觉**的几件事,变成可执行、可机检、可计数的动作。

不新增门禁,不打分。每一条都落在既有规约上:`conventions/coding.md` §0 ·
`conventions/evidence.md` 闭环与有界修复红线 · `verify/SKILL.md` 硬规则 5(影响面扩一跳)。

## 零、本地事实优先:先拿事实,再推理

`conventions/evidence.md` 的可信度表是这一层的地基:

| 材料 | 可信度 | 为什么 |
|---|---|---|
| AI 反馈 | **不可信** | 只是待证命题 |
| **文档** | **不可信** | **只是线索。会过时,而且过时的时候不会告诉你** |
| 代码 | **代码逻辑可信** | 实时真相。但仍须用例证明它是用户那条现象的根因 |

**文档过时是常态,不是意外。** 一个本仓的真实例子:`README.md` 曾写「真源路径
`~/.cursor/skills/idev/`」,而实际拓扑早已变成「git checkout 是真源,那个路径是 symlink」。
`healthcheck.sh` 按文档的设定去检查,于是**恒定 FAIL** —— 一个永远红的健康检查等于没有
健康检查,真问题会被淹掉。谁读那份 README 都会被带偏,包括写代码的人自己。

所以:**深入排查、定根因、下判断之前,用工具拿第一手事实,不要拿文档当依据。**

### 本地事实工具箱(按「问什么」选)

| 你要知道 | 用什么 | 不要用 |
|---|---|---|
| 这个符号 / 流程怎么连起来 | `codegraph_context "<描述>"`(一次给入口 + 相关符号 + 关键代码) | 翻架构文档 |
| 从 A 怎么走到 B | `codegraph_trace --from A --to B`(含动态分发的跳) | 顺着文档的调用图猜 |
| 改它会波及谁 | `codegraph_impact <symbol> --depth 1` | 手工 grep 想象影响面 |
| 谁调它 / 它调谁 | `codegraph_callers` / `codegraph_callees` | 读注释里写的「被 X 调用」 |
| 这一行到底怎么执行 | 直接 `Read` 那个文件那几行 | 相信函数名或 docstring |
| 这东西真实的行为 | 跑一条命令,**看实际输出** | 相信 README 里的示例输出 |
| 这段逻辑为什么这样 | `git log -p <file>` / `git blame` | 猜,或问另一个 agent |
| 配置 / 路径现在指向哪 | `ls -la`、`readlink`、`realpath` | 相信文档写的路径 |

**codegraph 等同「代码」一档** —— 它帮你读懂实际结构,但**不替代用例证明**。
`--depth 1` 是规约不是建议:`conductor-eval` 的 `one-hop-only` 以「候选 hop > 1」为失败。
查不到(动态分发 / 反射 / 配置路由)就**明说查不到**,不要当成「没有影响面」。

### 把 codegraph 用深,而不是只用一次

`codegraph_context` 是起点,不是终点。三类问题它答不了,要换工具:

| 问题 | 工具 | 为什么不能只靠 context |
|---|---|---|
| 这个流程**怎么**走到那里 | `codegraph_trace --from A --to B` | context 给的是邻域,不是路径。trace 含动态分发的跳(回调、JSX children),grep 跟不上 |
| 改它会**波及谁** | `codegraph_impact <sym> --depth 1` | 调用方不在你改的那个文件里,读源码看不见 |
| 这组相关符号的**实际实现** | `codegraph_explore "<几个名字>"` | 比链式 `codegraph_node` 少几次往返,一次给全 |

**查不到不等于没有。** 动态分发、反射、配置路由、SPI 注册 —— 这些 codegraph 看不见。
查不到就**明说查不到**,然后换一条路证明(跑一次看日志、搜配置、读注册表),
不要当成「没有影响面」。

### 运行时制品:先确认源码就是跑着的那一份

**排障时最该先问的不是「代码怎么写的」,是「我读的代码是不是线上跑的那一份」。**

`conventions/evidence.md` 要求「先认环境/产物」,`ops` 的拒过清单第一条就是
「未确认环境/产物就写结论」。但以前只能读源码树 —— 于是「认产物」是一句声明,
不是一次核对:agent 点个 jar 的名字,然后完全基于领先三个提交的工作副本推理。

```bash
python3 scripts/artifact-match.py --artifact <线上那个 jar> --repo <源码仓>
```

它从制品自己携带的构建身份读:`git.properties`(最好,点名 commit)→
`MANIFEST.MF` 的 `Implementation-Version` / `Build-Time` → class 时间戳(下界)。

| 判定 | 含义 | 下一步 |
|---|---|---|
| `MATCH` | 制品点名的 commit 就是当前 HEAD(且工作区干净) | 读源码得到的逻辑就是运行时的逻辑 |
| `AHEAD` | 源码比制品新 —— **它会列出这期间动过的文件** | 切到那个 commit 再读,或换同源制品,或只用制品自身的可观察行为 |
| `UNKNOWN` | 制品没携带可用身份 | **不是放行**:结论限制在可观察行为内,或让构建加 `git-commit-id-plugin` |

`AHEAD` 时列出的变更文件就是排查的第一优先级 —— **现象很可能就在那几个文件的差异里**。

**`UNKNOWN` 不是 PASS。** 「应该是同一份」正是拒过清单里的假想臆断。

### 文档和代码打架时

1. **以代码为准。** `conventions/evidence.md` 原文:「和代码或现象打架时以可运行证据为准」
2. **记下这个冲突** —— 回报里写 `DOC_DRIFT:`,说明哪一页说了什么、代码实际是什么
3. **交回导体派 `docs.backfill`** 去修那一页。不记下来,下一轮会被同一份文档再骗一次

第 3 步最容易被跳过:当轮任务做完了,文档的错留在原地。但过时文档的代价是**复利的** ——
它误导之后每一个读它的人,包括三个月后的你自己。

### 回报里的两行(可机检)

根因类与编码类步骤的回报必须有:

```
FACTS: codegraph <用了什么> | 源码 <路径:行> | 命令 <输出路径> | git <commit>
DOC_DRIFT: 无 | <文档页> 说 X,代码实际 Y(建议派 docs.backfill)
```

| 检查 | 失败条件 |
|---|---|
| `facts-first` | `FACTS:` 缺失,或只写了「文档」而没有任何代码 / 命令 / codegraph 来源 |
| `drift-declared` | `DOC_DRIFT:` 缺失(写「无」也算交代了) |

**只写「文档」不算事实。** 这两项由 `delegation.py` 机检,和 §0 三项交代同一种办法:
把「应该这么做」变成「不这么做就会被抓到」。

## 一、编码:把 §0 从「读过」变成「逐项交代」

`conventions/coding.md` §0 本身就是一份可执行清单(编码 5 步 + Review 6 步 + 念头对照表)。
问题从来不是清单不好,而是**没法验证 agent 真走过**。

所以 `idev-coder` 的回报里这三项是**必填结构化字段**,不是散文:

```
CHANGE_KIND: 校验 | 换协议 | 追加行为 | 加头 | 两通道 | 纯结构 | 结构+行为
CANON_TRIGGER: 无 | 新增一层 | 拆分 | 缓存 | 队列 | 重试 | 重写 | 新依赖
TABLE_HIT: §1 <行号/名称> | 零命中
```

对应 §0 的前三步。前四项**真的会被检查**(`delegation.py` 对 `idev-coder` 的回报跑):

| 检查 | 失败条件 | 谁查 |
|---|---|---|
| `s0-declared` | 三个字段任一没写(零命中也要显式写) | 机检 |
| `canon-walked` | `CANON_TRIGGER` 非 `无`,但 `review.md` 里没有对应 `T#` | 机检 |
| `struct-gated` | `CHANGE_KIND` 含「结构」,但回报与 `review.md` 都没回答 §3「满足条件」 | 机检 |
| `hit-applied` | `TABLE_HIT` 非零命中,但 `review.md` 没写该行的「运用 / 纠正 / 已改」 | 机检 |
| 零命中却新增抽象 | `TABLE_HIT` 零命中却新增了接口 / 抽象层(§0 第 4 步:零命中写具体类型) | **人工** |

**最后一项为什么不机检:** 判断一个新接口是否「过早」要读 diff 并理解设计意图,
机器判不了。写成机检只会得到一个假的绿灯 —— 所以它明确交给 `idev-reviewer`
(它扫 §1 时「该用的没用、不该用的用了,都是拒过」)和导体验收。

**读不到 `review.md` 时** `canon-walked` 与 `hit-applied` 返回 `WARN` 而不是 `FAIL`:
路径可能是相对另一个 cwd 的,拿不到文件不等于 agent 没做。`WARN` 不计入失败,但会显示。

**零命中也要显式写零命中** —— 不填这三项的回报,导体打回重做,不 record。

## 二、影响面:用 codegraph 替代手工扩一跳

`verify/SKILL.md` 硬规则 5 原文就是「影响面:diff + 调用关系扩一跳(**有 codegraph 就用**)」。
本机装了 codegraph MCP,这条从此不用手工 grep:

| 要什么 | 工具 |
|---|---|
| 改这个符号会波及谁(= `impact_candidates` 的 hop 1) | `codegraph_impact <symbol> --depth 1` |
| 谁调用它 | `codegraph_callers <symbol>` |
| 它调用谁 | `codegraph_callees <symbol>` |
| 某流程怎么走到某处 | `codegraph_trace --from <A> --to <B>` |

**`--depth 1` 不是建议,是规约:** `conductor-eval` 的诚实性检查 `one-hop-only` 的失败条件
就是「候选 `hop` > 1」。深度 2 以上是提名泛滥,会被记 HARD。

用法边界:

- codegraph 给的是**候选**,仍须人 `include`(verify 硬规则 5:「只提名,人 include」)
- codegraph 索引滞后写入约一秒,**改完代码立刻查会读到旧图** —— 先查再改,或改完等一拍
- 查不到(动态分发 / 反射 / 配置路由)时**明说查不到**,不要当成"没有影响面"

## 三、测试:维度表驱动 + 失败签名归一化

### 用例骨架

`mode` 的维度表决定要覆盖哪些维(`mode=test` 是六族)。对每一维,要么给一条 case,要么
**显式 `UNPROVEN` 并写清缺什么基线 / 缺什么原型**。这是 `verify/SKILL.md` 的既有要求 ——
提效在于先把骨架铺满再填,而不是想到哪写到哪:

```
每一维 → case 骨架 {id, 断言目标, runner, slice_id, baseline_item_id, accepted: false}
          ↓ 填不出 runner 或无基线
        UNPROVEN + 原因(not-accepted | no-baseline | no-runner | unknown-id)
```

`UNPROVEN` 的四类原因是 `conductor-eval` 的 `unproven_reasons` 既有取值,直接复用。

票里有 `deliver.yaml` 时,每条 case 必须同时挂 `slice_id` 与 `baseline_item_id` —— 可机检,
`check-feature.sh <f> verify-plan` 会查。

### 失败签名(修复循环的刹车)

`conventions/evidence.md` 第 5 步定义了有界修复红线,但"相同失败签名连续 3 次"以前靠人数。
现在算得出来:

```bash
python3 scripts/failure_signature.py sig --log <日志>          # 打印归一化签名
python3 scripts/failure_signature.py append --feature <f> --log <日志> --delta <改动行数>
python3 scripts/failure_signature.py check --feature <f>       # 命中红线则退出码 2
```

签名 = `[异常类型] [失败用例] [归一化错误信息]`,归一化会去掉行号、时间戳、临时路径、
内存地址、UUID,这样"同一个错"才认得出来。

台账落 `<票目录>/fix-attempts.yaml`,每轮一条:
`签名 | 代码变化量 | 与上轮是否语义不同 | 决策`(这行格式是 evidence.md 原文要求的)。

**三条红线命中任一 → 强制停止叠改、升级人工**:

| 红线 | 判据 |
|---|---|
| 同签名连续 3 次 | 最近 3 条 `signature` 相同 |
| 连续 2 次无有效变化 | 最近 2 条 `delta` 为 0,或 `semantic_change: false` |
| 单根因反复超 ~15 分钟 | 最早一条到现在 > 15 分钟且仍未绿 |

命中时 agent 必须回报 `BLOCKED` 并写清是哪条,**不静默再试**。这是 evidence.md 的原文要求,
脚本只是让它可判定。

## 四、根因:假设台账 + 三条严格要求

`conventions/evidence.md` 要求「每一步先设计用例并证明」。台账让它可查,
另外三条要求让它**严格**:

### 4.1 结论要有代码逻辑级的证据,不只是一个路径

`evidence.md` 的可信度表把材料分了级,所以证据也分级:

| 级别 | 是什么 | 证明了什么 |
|---|---|---|
| `doc` | 文档 / 注释 | **什么都没证明** —— 它不可信,只是线索 |
| `log` | 日志 / 响应 / 抓包 | 现象**发生过**。不证明为什么 |
| `repro` | 可复现用例 | 能**触发**。仍没解释机制 |
| `code` | `file:line` 的代码逻辑 | **解释机制的那一层** |

**`status: proven` 必须有 `code` 级证据** —— 即至少一条 `file:line`。机检
`proven-needs-code-evidence`。

为什么卡这一条:一条日志说明「请求到了网关却没带 traceId」,这是现象。
**为什么**没带?只有那一行代码能回答。停在日志级就是把现象当成了根因,
下一次换个触发路径它又出现。

### 4.2 穷举可能原因,排除的也要留痕

「推导并论证可能引起问题的**所有**原因」—— 被排除的那些是答案的一部分。

```bash
python3 scripts/hypothesis.py add --feature <f> --claim "<可能原因>" --case "<怎么验>"
python3 scripts/hypothesis.py set --feature <f> --id H2 --status disproven \
  --note "打开 debug 日志看到这条分支根本没进,见 logs/h2.log"
python3 scripts/hypothesis.py candidates --feature <f>
```

`candidates` 分三栏列:已证成 / 待验 / 已排除,并给出每条的证据级别。

**只有一条假设且直接证成会给 WARN**(不是 FAIL —— 第一个猜想恰好对是可能的)。
但它值得问一句:别的可能性是真的考虑过并排除了,还是**从没写下来**?
`disproven` 没写排除依据也会被点出来 —— 否则下一轮会重走同一条路。

### 4.3 修复前先设计影响范围用例

`evidence.md` 第 4 步要三类用例:**正确性**(红转绿)· **影响范围**(不该变的保持原行为)·
**验收**(原现象消失)。中间那一类最常被跳过,而**它正是挡住「修一个坏三个」的那一类**。

```bash
python3 scripts/hypothesis.py blast --feature <f> --id H1 \
  --baseline <修复前的现状用例> \
  --guard <不该变的路径,修复后必须仍绿>
```

`status: proven` 却没有 `blast.guard` → 机检 `proven-needs-blast-radius` FAIL。
**根因一旦证成就要动手修了,这时候没有护栏用例,就没人知道修完有没有碰坏邻居。**

guard 用例从哪来?用 `codegraph_impact <根因符号> --depth 1` 提名调用方 ——
那些路径就是最该保持原行为的地方。



`conventions/evidence.md` 要求「每一步先设计用例并证明,通过后才决定推导的下一步」。
以前假设散在对话里,查不回去也数不清。现在落盘:

`<票目录>/hypotheses.yaml`

```yaml
schema_version: 1
feature: example-change
items:
  - id: H1
    claim: "网关把 X-Trace 头丢了,所以下游取不到 traceId"
    case: "curl 带头打网关,断言下游日志里有同一个 traceId"
    evidence:
      - docs/task/example-change/verify/logs/h1-gateway.log
    repro: yes          # pending | yes | no
    status: proven      # open | proven | disproven
    at: 2026-10-12T22:40:00+08:00
```

```bash
python3 scripts/hypothesis.py add --feature <f> --claim "..." --case "..."
python3 scripts/hypothesis.py list --feature <f>
python3 scripts/hypothesis.py check --feature <f>      # 可机检,见下
```

可机检三条(全部落在 evidence.md 的既有要求上):

| 检查 | 失败条件 | 依据 |
|---|---|---|
| `proven-needs-repro` | `status: proven` 却 `repro != yes` | 「未在用户同一现象上红过一次 → 不写根因」 |
| `proven-needs-evidence` | `status: proven` 却 `evidence` 为空 | 「分析、论证、推测都只是待证命题,必须带辅助证据」 |
| `case-before-next` | 有 `status: open` 且无 `case` 的条目,却已经新增了后续假设 | 「每一步先设计用例并证明,通过后才决定下一步」 |

**`disproven` 不删,留着。** 排除过的路径是证据链的一部分,也是下次不重走弯路的依据。

## 五、这三板斧怎么联动

```
S4 根因 ──假设台账──┐
                    ├─→ 定位到要改的符号
S6 现象 ────────────┘         ↓
                      codegraph_impact --depth 1   ← 影响面候选(人 include)
                              ↓
                      编码:§0 三项交代 + 当轮改掉命中
                              ↓
                      测试:维度表铺骨架 → 跑
                              ↓ 红
                      failure_signature append → check
                              ↓ 命中红线
                      BLOCKED 升级人工(不叠补丁)
```

三个脚本的产物都落**票目录**,跟着票走,不进 `.scratch/`,`execution-clean` 不碰票目录。

## 六、不要

- 把 codegraph 的候选当成"已验证的影响面"(它是提名,不是证据)
- `--depth` 开到 2 以上凑候选数(`one-hop-only` 会记 HARD)
- 为了让 `failure_signature check` 过,去改签名归一化规则
- 假设台账里只留证成的,删掉证否的
- 把这三样做成分数或门禁(它们是**可判定的停止条件**,不是评分)
- 跳过 §0 三项交代直接写代码,事后补填
