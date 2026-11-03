# 两阶段读

先列出薄目录，再加载一个行区间。目录里没有函数体。

同一路径若同时出现在符号名单与经验证据路径里，用倒数排名把该路径往前排（k=60）。这只决定顺序，不是相关性分数，也不能当成答案。codegraph 仍是符号位置的来源。经验正文仍走 `lessons.py recall`。

```bash
python3 scripts/context-stage.py --schema
python3 scripts/context-stage.py preview --repo <仓根> --query "<要读的行为>" --feature <f>
python3 scripts/context-stage.py load --repo <仓根> --id <path:start:end> [--feature <f> --step <步骤>]
```

`--top` 为 1 到 20，默认 8。不带 `--feature` 时不读经验，避免把别的票排进这个仓库。

退出码：0 目录或区间，1 拒绝或所问的来源都失败，2 仓库读不了。0 只说明没撞上已知的硬错，不说明这段代码被读对了。

## 目录

| 列 | 含义 |
|---|---|
| `SOURCE codegraph` | `ok`，或 `fail:` 加原因。没有 `.codegraph`、找不到命令、命令失败，都算失败 |
| `SOURCE lessons` | `ok` / `absent` / `fail: 没有这张票` |
| `symbol` | id 是 `path:start:end`，交给 `load` |
| `lesson` | id 以 `lesson:` 开头。`load` 拒绝。正文走 `lessons.py recall`，召回仍是建议 |

一个来源失败时，另一来源的行仍在。失败写在该来源的 `SOURCE` 行上，不改成空目录。

## 加载

`load` 只接受一个 `path:start:end`。路径必须落在 `--repo` 里面。一次最多 80 行；更长就打印 `TRUNCATED` 和下一段 id。`sha256` 是整个文件的，用来发现这次读到的文件和上一次不是同一份字节。同时给出 `--feature` 和 `--step` 时，把这个区间记进该票的 `workflow/reads.yaml`。缺其中任一个，行为与原来相同。

下一次 `attempt > 1` 的委派包从这份账重放原文。哪些段放进去、哪些只留一行，见 [agents.md](agents.md)「模型看见的内容从日志重放」。

单行超过 500 字会截断该行，文件哈希仍按全文计算。

## 退役的第三路

曾有第三路本地检索（`index` 子命令 + Milvus Lite 文件库）。2026-11-03 退役：零使用 —— 163 份内核 trace 命中 6 份全是开发它本身，产品仓 228 份 trace 零命中，索引建过一次就过期无人重建。它也是整套依赖里唯一引入运行时的那个（本地服务进程、`.db` 与 lock 文件、unix socket 路径长度限制）。

代码在 `attic/scripts/rag_milvus.py`，接回来的完整步骤在 `attic/MOVED.md`，判据在 [20261103-retire-local-rag](../state/proposals/20261103-retire-local-rag.md)。两阶段读本身没有退役 —— 退的是第三路。
