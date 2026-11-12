# rootcause-gvisor

本页复述密封基线。实现细节不在这里。

goal: 根因阶段 --step rootcause 的探针经 gVisor 的 runsc 执行,该探针在宿主仓库新建的文件数等于 0。

| id | must |
|---|---|
| B1 | 当 --step 等于 rootcause 时,repl.py 的 cmd_run 经 runsc 执行片段,宿主仓库内该片段新建的文件数等于 0。 |
| B2 | 当 --step 等于 rootcause 且 runsc 不在 PATH 时,cmd_run 退出码不等于 0,且该片段要新建的路径在宿主上的个数等于 0。 |
| B3 | 当 evidence 指向的 repl transcript 没有 runsc 回执时,hypothesis.py 的 check 退出码不等于 0。 |
| B4 | 当 --step 不等于 rootcause 时,repl.py 的 cmd_run 仍用宿主 Python 执行片段,并在票目录写下 1 个 transcript 文件。 |

non_goal: 不把 Cursor 模型进程放进 runsc。不把 codegraph 查询、假设台账写入和文件只读放进 runsc。不在本票安装虚拟机,也不把 runsc 二进制提交进仓库。不给编码、提测和巡检包套沙箱。不打开网络,不挂载家目录凭证、docker.sock 和 kubeconfig。不把 guard() 的静态扫描当成隔离。
