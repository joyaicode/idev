# MOVED

退役的东西记在这里。**什么都没有被删**，每条都写明怎么取回。

---

## `scripts/rag_milvus.py` → `attic/scripts/rag_milvus.py`

- 退役日期：2026-11-03
- 提案：`state/proposals/20261103-retire-local-rag.md`
- 人的原话：和知识准确检索召回无关的向量数据库是不是可以先移除

**为什么退：零使用，不是用得少。** 163 份内核 trace 命中 6 份，6 份全是 10-30 至 11-01
开发它本身的记录，没有一份是用它查代码。产品仓 228 份 trace（joypaas 97 + kafka 110 +
rabbitmq 21）零命中。`.idev/rag/milvus.db` 10-30 建过一次，之后源码改过多轮、stamp 已
失效，`search_repo` 一律返回 `fail: 索引过期` —— 没人重建。

它也是整套依赖里唯一引入运行时的那个：pymilvus 带 grpcio/protobuf 一串重包，Milvus Lite
起本地服务进程、在仓里写 `.db` 和 lock 文件，还受 unix domain socket 的路径长度限制。
那个限制真的咬过一次：深 TMPDIR 让 socket 路径越过 macOS 的 ~104 字节上限，而
`transient()` 判它可重试、重试改不了路径长度，所以必然失败。为一个零使用的能力付了一次
真实的排查成本。

### 怎么接回来

**零使用的原因很可能就是这一步没人知道要做** —— `search_repo` 在没索引时返回 `absent`、
在索引过期时返回 `fail: 索引过期`，两种都安静降级，不会提示你该去 `index`。所以接回来
必须连这一步一起接。

1. `git mv attic/scripts/rag_milvus.py scripts/rag_milvus.py`
2. 装依赖：`python3 -m pip install --user pymilvus`，并在 `requirements.txt` 里把它从
   「已退役」改回一行可选依赖
3. `scripts/context-stage.py` 恢复四处：`import rag_milvus`；`fuse()` 的第三参
   `rag_paths`；`assemble()` 里的 `search_repo` 调用与 `("rag", rag_status)` 状态行；
   `tag_rag` / `extra_rag` / `with_rag` 三个函数与 `cmd_index` / `add_index` 子命令
4. `scripts/test_context_stage.py` 恢复 7 个 RAG 用例，并把
   `test_no_hit_is_not_a_failure` 里的 `assertNotIn("SOURCE\trag", ...)` 改回
   `assertIn("SOURCE\trag\tabsent", ...)` —— 那条反向断言就是为了让这次退役不被无声推翻
5. **socket 路径长度**：恢复 `temp_base()` / `SOCKET_CAP=104` / `PATH_TAIL=47` 与
   `TempBase` 四条锁。`selfcheck.sh` 导出的 TMPDIR 比默认深一层，不恢复这一组，7 个
   RAG 用例会在 selfcheck 里红而单独跑时绿
6. `references/context-stage.md` 恢复 RAG 段落与 `SOURCE` 表的 `rag` 行；`SKILL.md`
   恢复「本地 Milvus 只提名区间」；`agents/idev-coder.md`、`agents/idev-ops.md` 恢复
   各自那段
7. **每个要用的仓都得先跑一次** `python3 scripts/context-stage.py index --repo <仓根>`，
   并且源码变动后重跑 —— 否则它就是又一次零使用

真要接回来，先回答一个问题：这次为什么会用起来。上次没用起来不是因为它不好用，是因为它
只是 `idev-coder.md` 正文里的一句建议，而 agent 看不到对话、只读必读页。接回来之前先把
它接进委派包的必读页，否则同样的结局。

### 保留的部分

`scripts/context-stage.py` 本身**没有退役**。「preview 出薄目录 → load 加载一个区间」
是省上下文的正确机制，`codegraph` 与 `lessons` 两路照常工作、不依赖 pymilvus。退掉的只是
第三路。
