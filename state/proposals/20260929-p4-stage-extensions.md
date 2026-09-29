# 提案 P4：阶段读取产线页

- status: landed (2026-09-29, 人要求按核心目标修复)
- scope: 内核识别 `.idev` 的方式；不把某一产线的页或命令写回内核
- created: 2026-09-29

## 对照使用说明之后还成立的问题

1. 有标记的产线页没有挂到生命周期阶段上。`deliver` 不点名 `.idev`，`check-feature` 只在 ops 查交出口。
2. 内核自检把 `coding_root` 和 `ui-automation-build.yaml` 当成通过条件。
3. 配方例句把 kafka / etcd / zk 写进内核。
4. kind 说明把某一种启停脚本写成所有产线的命令。
5. PIN 摘要检查把某一产线的页名和禁文写在内核。
6. 冲突顺序让产线契约盖过签字和证据。
7. 第一次写入 `.idev/` 时使用说明要求一起写 `marker`，保存中间态的脚本没有写。

## 不改的

- 不把安装账本当成这次会话的产线，也不从兄弟目录猜测扩展根。当前产线仍是这次正在交付的那个工程。
- 不造一张 `aligned` 的票去填后半段里程。那仍是 P1，要人确认。

## 落地

- `stage-extensions.py` 读 `.idev/extensions.yaml`。`check-feature` 每个阶段都跑。
- `product-checks.sh` 跑 `.idev/checks/*.sh`。
- 第一次 `--mkdir` 保存写下 `evolve: false` 的标记，已有标记不改。
- 启停 / UI / lint 的命令键是 `commands.*`，具体命令留在产线 `workflow-defaults.yaml`。
