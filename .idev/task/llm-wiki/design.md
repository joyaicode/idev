# 方案：票内主张索引

给人评审的叙述。机读影响面和用例意图在 `arch.yaml`。可执行用例在架构通过之后再写。

## 前置

影响面是三个新文件：`scripts/claims.py`、`scripts/test_claims.py`、`references/claim-index.md`。没有既有文件，所以没有既有问题。既有问题 0 行。需求行数要等实现 diff，本阶段不把未落盘的估计写成已测量。0 条既有问题，建议本次不修。`scope_debt.decision` 写 `mark`。

## 目标

交付票往下走时，用不可变来源、索引和内核 schema 这三层，把基线、方案、代码、用例和经验对到同一说法。校准是对照来源标出一致或漂移。两处说法冲突就停。

非目标仍是基线那句：不装第三方引擎，不建向量库，不做健康分，不编译第二份内核文档，不收个人笔记，不改产品控制台知识库，不把耗时写成验收，不把校准加进 check-feature，不复制或替换 lessons 与 realign。本方案覆盖 B1、B2、B3、B4、B5、B6、B7、B8、B9，不另加义务。

## 方案

一个命令 `scripts/claims.py`，一份说明 `references/claim-index.md`。索引文件只写在当前票目录的 `claims.yaml`。不新开服务，不新开目录树，不改 `SKILL.md`。

三条操作（B1）：

- 摄取：只读该票的 `req.yaml`、`design.md`，以及已经存在的 `verify/plan.yaml`。聊天不读（B5）。
- 查询：打印记录和来源路径，不代替打开来源（B3）。
- 校准：来源对不上，或同一主题两条记录互相装不下，退出码非 0，并打印来源路径（B6）。

记录从两类句子来，不靠模型临场判断：

- `req.yaml` 里每条 slice 的 `must`。来源是 `baseline.yaml` 里同一条 item。主题是 `baseline_item_id`。
- 方案、拆解、用例里的显式行：`主张: <句子> | 来源: <路径>`。句子必须已经写在这些工件里。来源路径指向工件点名的基线、代码、已晋升经验或规约（B5）。

校准做两件机械的事，不做语义打分：

- 句子经空白归一后，必须出现在来源文件里。否则不能留在索引里，校准退出码非 0（B3、B6）。
- 同一 `subject` 下两条记录，谁的文本都不是另一条的子串，视为互相矛盾，退出码非 0，并打印两个来源（B6）。

`realign.py` 继续报告方案、拆解、用例相对基线的七类漂移。`lessons.py` 继续负责经验的新增、升级和召回。`claims.py` 不调用它们，不复制它们的正文，也不提供查询它们的入口（B7）。写方案、拆解或用例之前先跑校准，退出码非 0 就不写这一份（B8）。改某条记录点名的代码文件之前同样先跑；退出码非 0 就不改这个文件。没被点名的文件不在这条里（B9）。校准不进入 `check-feature`（B2）。

被拒的做法：用向量库或健康分；让模型判断两句是否矛盾；把 lessons 和 realign 抄进索引；改 `SKILL.md` 入口。入口就是 `python3 scripts/claims.py` 和 `references/claim-index.md`。

已扫架构信号：新增的是一个脚本和一份说明，不是新服务。索引是派生层，真相在来源文件，失效靠校准重跑，失败是非 0 退出，不吞成空结果。没有耗时优化。

## 契约

`claims.yaml` 放在票目录。每条记录有 `id`、`subject`、`text`、`source`。`source` 非空，`text` 必须能在该文件里找到。

`python3 scripts/claims.py ingest --feature <f>` 重写该票的 `claims.yaml`。
`python3 scripts/claims.py query --feature <f> --subject <id>` 打印匹配记录和来源路径。
`python3 scripts/claims.py calibrate --feature <f>` 一致时退出码 0，冲突时退出码非 0。
`python3 scripts/claims.py guard --feature <f> --path <file>` 只在该文件被某条记录点名时跑校准，供改代码前使用。

没有新的网络服务、表或向量索引。`lessons.py` 与 `realign.py` 的命令不变。

## 影响面

- hop 0：`scripts/claims.py`（include）。三条操作和 guard。
- hop 0：`scripts/test_claims.py`（include）。夹具锁住退出码和文件是否被改。
- hop 0：`references/claim-index.md`（include）。记录格式和何时跑。

`lessons.py`、`realign.py`、`SKILL.md`、`check-feature` 不改。`arch.yaml` 的 `impact_candidates` 与这里同一份。

## 回退

停用 `scripts/claims.py`，删除该票的 `claims.yaml`。基线、lessons、realign 不动。没有迁移，没有第二套开关。

## 用例

与 `arch.yaml` 的 `case_intents` 同一批。可执行用例在架构通过之后写进 `verify/plan.yaml`：

- `ops-exist`（B1，correctness）：ingest、query、calibrate 三个子命令都存在，并且能跑。
- `no-extra`（B2，boundary）：实现 diff 不新增依赖、不改 check-feature、不复制内核说明正文。
- `source-required`（B3，correctness）：缺来源，或句子不在来源中，摄取失败；查询输出含路径。
- `ticket-only`（B4，boundary）：索引只出现在票目录。
- `claim-from-artifact`（B5，boundary）：聊天句子不产生记录；工件里的主张行会产生记录。
- `conflict-nonzero`（B6，correctness）：来源不一致，或同一主题两条记录互相装不下时，退出码非 0 且输出含路径。
- `ledgers-stay`（B7，compat）：realign 与 lessons 的命令和正文都不被 claims 改写或转查询。
- `guard-doc`（B8，correctness）：校准非 0 时，方案、拆解、用例文件与运行前一致。
- `guard-code`（B9，correctness）：被点名的代码文件在校准非 0 时与运行前一致；未点名的文件不由这条挡住。
