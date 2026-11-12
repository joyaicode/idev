convention: grilling
frontier: empty
shared_understanding: true
arch_frontier: empty
arch_shared_understanding: false

process-eval: now=CORRECT rule=drive-auto。本票没有 workflow run，`decide --all-open` 无步骤可写；采纳的答案写在下面各题的 ➡️，source=auto，quote=auto:recommend。

Q1 探针从哪进沙箱

❓ **Q1** - **探针从哪进沙箱**: 根因阶段要跑在沙箱里。今天 `scripts/repl.py` 的 `cmd_run` 用宿主 `subprocess.run` 执行片段，模块说明写明它不是沙箱。Cursor 的模型进程不在本仓库里，拦截不了。

选项: 1) 仅当 `--step rootcause` 时，`cmd_run` 经 runsc 执行；回执缺失的 repl transcript 不能当证据。模型进程、codegraph、台账写入、文件只读仍在宿主。 2) 试图把整个 Cursor 代理进程放进 runsc。

➡️ 1。source=auto quote=auto:recommend。2 做不到，写成 non_goal。

❓ **Q2** - **没有 runsc 时**: 本机是 darwin/arm64，PATH 里没有 runsc，也没有 docker。

选项: 1) 退出码不等于 0，不在宿主执行该探针。 2) 回落宿主并打警告。

➡️ 1。source=auto quote=auto:recommend。回落宿主等于继续把写操作留在宿主机上。

❓ **Q3** - **网络和凭证**: 沙箱要不要能访问网络、家目录凭证、docker.sock、kubeconfig。

选项: 1) 网络关闭，上述路径不挂载。 2) 默认为根因探针开放网络。

➡️ 1。source=auto quote=auto:recommend。需要网络的线上取证另开票，本票不把宿主网络放进沙箱。

Q4 运行时是否只认 runsc

❓ **Q4** - **运行时是否只认 runsc**: 与 runc 的 namespace、macOS sandbox-exec 相比，隔离边界是否允许替代品。

选项: 1) 只认 gVisor 的 runsc。没有 runsc 就按 Q2 拒绝。 2) 在 Darwin 上改用 sandbox-exec。

➡️ 1。source=auto quote=auto:recommend。原话点名 gVisor。runc 与宿主共享内核；sandbox-exec 不能在 Linux 上给出同一边界。
