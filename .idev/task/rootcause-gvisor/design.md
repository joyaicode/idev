# 方案：根因探针经 runsc 执行

## 前置

影响面是 `scripts/repl.py` 的 `cmd_run`、`scripts/hypothesis.py` 的 `check`，以及新的 `scripts/lib/runsc_probe.py`。这三处都读过。没有重大缺陷。`cmd_run` 在非 rootcause 步骤仍由宿主 Python 执行，这是 B4 要保住的行为，不是待修缺陷。

本需求要新增或改写的是 runsc 启动、`--step rootcause` 分支、回执检查和 ops 说明，合计 203 行（`runsc_probe.py` 143，`hypothesis.py` 新增 18，`repl.py` 执行分支约 40，`agents/idev-ops.md` 2）。既有问题 0 条、0 行。0 × 5 < 203，小于 1/5，且没有和本次改动分不开的缺陷。`scope_debt.decision=mark`。

## 目标

根因阶段 --step rootcause 的探针经 gVisor 的 runsc 执行,该探针在宿主仓库新建的文件数等于 0。

非目标仍是基线那句：不把 Cursor 模型进程放进 runsc，不把 codegraph、台账写入和文件只读放进 runsc，不安装虚拟机，不提交 runsc 二进制，不给编码、提测和巡检包套沙箱，不打开网络，不挂载家目录凭证，不把 `guard()` 当成隔离。本方案覆盖 B1、B2、B3、B4，不另加义务。

## 方案

`--step rootcause` 时，`cmd_run` 把片段交给 `runsc_probe.execute`。它查找 PATH 上的 `runsc`，写成 OCI bundle 后执行 `runsc --root=<state> --network=none run --bundle <bundle> <id>`。非 root 再加 `--rootless`。仓库以只读绑定挂到 `/repo`，解释器所在的 `/usr`、`/lib`、`/bin` 等前缀只读挂载，scratch 在仓库外可写。家目录本身不挂。片段在沙箱里的 `REPO` 是 `/repo`。`runsc` 缺失或片段不在仓库内时退出码 127，不调用宿主解释器（B2）。启动成功才写同名 `.receipt`，内容含 `runtime: runsc`（B1）。

`check` 看到父目录名为 `repl`、后缀 `.out` 的证据时，要求旁边有含 `runtime: runsc` 的回执，否则退出码不等于 0（B3）。`code` 等其它证据不走这条。`--step` 不是 `rootcause` 时仍走原来的宿主 `subprocess`（B4）。

`runsc do` 被拒绝：它把整个宿主文件系统以只读加 tmpfs 叠层挂进去，家目录凭证会进沙箱。回退是让 `--step` 不再取 `rootcause`，`cmd_run` 回到宿主分支；没有迁移，没有第二套开关。

## 架构范式（canon）

- 本轮类型: behavior
- 已扫: §2 信号 / §4 念头 / §6 失败模式
- 命中: T4 跨信任域。根因片段不再继承宿主写权限和家目录；bundle 只挂仓库只读和解释器前缀，不挂家目录，`--network=none`。T8 失败不回落：没有 runsc 就退出 127，不在宿主执行。T11 外部调用有超时 120 秒，与 repl 原超时相同。T12 同一轮改了 `agents/idev-ops.md`。
- 零命中的其余信号: 已扫，无命中。不新增 interface、依赖、配置项、缓存、队列。
- A1: 本质问题是根因探针的写操作不能留在宿主。砍掉了「把 Cursor 进程放进 runsc」和「用正则当隔离」。重点在 `execute`：找不到 runsc 就返回，找到就只 exec runsc。
- A2: `cmd_run → runsc_probe.execute → runsc`。业务判断不依赖 Web 框架。词表：探针、回执、runsc。沙箱内主体不是宿主用户的家目录权限；非 root 使用 `--rootless`，不把宿主管理员当成沙箱里的额外特权。
- A3: 被拒方案是 `runsc do`（整盘只读挂载，凭证进沙箱）和 macOS sandbox-exec（不是 gVisor，Linux 上没有同一边界）。回退是停止使用 `--step rootcause`。
- A4: 真相在宿主上的 `.py`、`.out`、`.receipt`。沙箱内写入不是真相，仓库只读所以落不回宿主。失败语义是退出码 127 或 runsc 的退出码，调用方看到非 0 就知道没有宿主执行。没有消息队列，没有跨系统事务。丢失窗口是这一次探针的 stdout；回执记下退出码。一致性是单次调用。
- A5: 最薄链路是假 runsc 记录 argv、片段要求新建仓库文件、断言该路径个数等于 0 且回执含 `runtime: runsc`。顺序：先拒绝缺失 runsc，再接假 runsc，最后才是一台有真 runsc 的 Linux。
- A6: 护栏是 `scripts/test_runsc_probe.py` 五条断言，对应 B1–B4。失效域是单次 `runsc` 进程，爆炸半径是 scratch 和只读仓库视图，写不到宿主仓库。这不是线上服务。用户视角的数是基线那条：宿主新建文件数等于 0。错误预算、四黄金信号、容量峰值：UNPROVEN。补证据的动作是，若这段运行器被放进共享 CI，由 wangwei794 补一次并发 1 的耗时记录。当前不编造这些数字。回滚是不再传 `--step rootcause`。没有灰度开关。
- A7: 沿用 `repl.py` 的 transcript 和 `hypothesis.py` 的 `check`。新文件 `runsc_probe.py` 只有 `cmd_run` 一个调用方，不抽接口。上手路径：本页、`agents/idev-ops.md` 里 `--step rootcause` 那一段、`python3 scripts/test_runsc_probe.py`。
- A8: 不做虚拟机、不做编码/提测沙箱、不开网络。若要让线上取证出网，重新设计挂载和网络，不在本方案上加一个默认开关。
- 未决权衡: 无。Q1–Q4 已在 req 轮按 drive-auto 采纳。

## 契约

没有新的对外 HTTP 或事件。根因探针的入口仍是 `repl.py run --step rootcause`。回执文件与 transcript 同目录，文件名把 `.out` 换成 `.receipt`，正文含 `runtime: runsc`。`check` 只对父目录名为 `repl` 且后缀为 `.out` 的证据要求这份回执。

## 影响面

- hop 0：`scripts/lib/runsc_probe.py`、`scripts/repl.py`、`scripts/hypothesis.py`（include）。行为改在这三处。
- hop 1：`agents/idev-ops.md`、`scripts/test_runsc_probe.py`（include）。说明和锁住 B1–B4 的断言。

`arch.yaml` 的 `impact_candidates` 与这里同一份。

## 回退

根因探针不再使用 `--step rootcause`，`cmd_run` 走宿主分支。不删除已写下的 transcript。没有数据迁移。

## 用例

- C1（B1，sandbox-rootcause-probe）：假 runsc 下 1 次写文件片段，宿主目标路径个数等于 0，回执 runtime 等于 runsc。
- C2（B2，refuse-without-runsc）：PATH 无 runsc 时退出码不等于 0，目标路径个数等于 0。
- C3（B3，reject-unsandboxed-evidence）：1 条无回执 transcript 使 check 失败次数等于 1；一条 `file:line` 证据不因此失败。
- C4（B4，keep-host-repl）：1 次 `--step arch` 写下 1 个 transcript，记录不含 runtime=runsc。
