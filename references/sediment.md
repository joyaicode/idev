# 知识沉淀

可重跑的做法先记成程序候选。两条内容不同的结果，并且由人确认之后，才留下。程序只指向仓库里已经存在的脚本。

事实不进这本账，走 `lessons.py add`。决策步的 prefix 也在那边。要看语境的判断不进这本账，写成提案的最小 diff。学习信号够不够、该写到哪里，先看 [self-evolution.md](self-evolution.md)「学习信号写到哪里」。证据、知识和索引分三层，见同一页「跨会话留下什么」。

本命令不调用模型，不生成代码，不执行脚本，不改提示词。外部内容直接拒绝。

```bash
python3 scripts/sediment.py schema
python3 scripts/sediment.py add --feature <f> --form program --trust reviewed \
  --scope "<范围>" --claim "<做什么>" --not-when "<何时不适用>" \
  --evidence <结果文件> --script <已有的.py或.sh>
python3 scripts/sediment.py transform --feature <f> --id S1 --by <人> --repro <复现文件> \
  [--evidence <另一份结果>]
python3 scripts/sediment.py recall --feature <f> --scope "<范围>"
python3 scripts/sediment.py gc --feature <f>
python3 scripts/sediment.py retire --feature <f> --id S1 --why "<为什么过时>"
python3 scripts/sediment.py check --feature <f>
```

`--form fact` 和 `--form instruction` 拒绝，并指出该去的账。不带 `--feature` 时用内核 `state/sediment.yaml`。带了就要有这张票的目录，否则拒绝。

退出码：0 记下、留下、召回或台账没有硬错；`gc` 在没有条目可指时也是 0。1 是台账硬错，或 `gc` 指出了条目。2 是拒绝，含票目录不存在、路径越出仓库、事实或判断走错账、外部内容要写成程序。0 只说明没撞上已知的硬错，不说明这条做法是对的。

## 留下

同时满足才从 `candidate` 到 `kept`：

- `--form program` 且 `--trust reviewed`
- 至少两份结果文件，路径不同，内容也不同。把同一份日志复制两份不算
- 脚本路径本身不算结果
- `--by` 是人。模型确认自己的结论不叫确认
- `--repro` 是仓库里一份非空文件，路径和内容都不在起草证据里。起草用过的那一份不能再当复现。写这条的时候不打开这份复现
- 脚本当时还在，并且是 `.py` 或 `.sh`，不是 `SKILL.md` 这类提示词文件
- 留下时把脚本、每份结果和复现的 sha256 写进 `bound`
- 结果写出任务的最终状态。脚本退出码 0，或每一步都执行过，不算办成。浏览器回执的办成认 [browser-program.md](browser-program.md) 的 `business_ok`
- 复现从独立的初始状态重跑，不是接着起草那次的现场看
- 主张写稳定步骤和参数名，不把某一次的字面量写成步骤
- 回放对不上（目标没有了、状态检查失败、接口变了、最终状态错了）就 `retire`，再探索。不在原来的记录上改主张

证据、复现和脚本都必须落在 `--repo` 里面。符号链接指到仓库外、路径里带 `..`、空文件，都拒绝。

手改 `status: kept` 绕不过 `check`：人、复现、两条不同结果、信任、复现是否起草用过、字节有没有钉住，都会再验一遍。脚本、结果或复现和 `bound` 对不上时，`check` 失败，召回写明不要当成现行能力。脚本变了还拿原来的结果去 `transform`，会拒绝。要重新留下，得再给一份内容不同的结果。没有 `bound` 的已留下条目不能在原地补钉。

## 垃圾回收

`gc` 只打印，不改文件：

| 行 | 含义 |
|---|---|
| `GC duplicate` | 同一范围、同一句话 |
| `GC overlap` | 同一范围里，一句短的含在另一句里 |
| `GC stale` | 记下的文件已经不在 |
| `GC drift` | 脚本、结果或复现已经不是留下时的字节。`check` 因此失败 |
| `GC single` | 候选只有一条结果。一次成功还不是能力 |

`GC drift` 以外的这些行，`check` 打成 `WARN`，不因此失败。确认过时后再 `retire --why`。新条件下失效时收窄 `not_when`。同一条件下被反证再 `retire`。全文在 [self-evolution.md](self-evolution.md)「学习信号写到哪里」。
