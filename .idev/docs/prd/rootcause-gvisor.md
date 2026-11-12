# 根因探针跑在 gVisor 里

goal: 根因阶段 --step rootcause 的探针经 gVisor 的 runsc 执行,该探针在宿主仓库新建的文件数等于 0。

| id | 要达成的结果 |
|---|---|
| B1 | `--step rootcause` 时,`cmd_run` 经 runsc 执行,宿主仓库内新建文件数等于 0 |
| B2 | runsc 不在 PATH 时,该调用退出码不等于 0,宿主上目标路径个数等于 0 |
| B3 | 指向无 runsc 回执 transcript 的 evidence 使 `check` 失败次数等于 1 |
| B4 | `--step` 不是 rootcause 时,仍由宿主 Python 执行,并写下 1 个 transcript |

非目标: 不把 Cursor 模型进程放进 runsc。不把 codegraph、台账写入和文件只读放进 runsc。不安装虚拟机,不提交 runsc 二进制。不给编码、提测和巡检包套沙箱。不打开网络,不挂载凭证。不把 `guard()` 当成隔离。

指标: 宿主新建文件数 | 当前值: 探针经宿主 subprocess 执行,个数随片段而定 | 目标值: 等于 0 | 测量: 假 runsc 或真 runsc 跑 1 次写文件片段,数宿主目标路径
