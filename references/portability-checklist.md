# 可移植性清单（第二个人 / 另一台机器落地）

> 状态：**仅为清单，未做过跨机验证**。当前只在一台 macOS 机器上运行过；下列步骤是按脚本行为整理的预期，落地时请逐条实测并回填。

## 已知前提（脚本里的假设）
- 真源固定为 `$HOME/.cursor/skills/idev/`（实目录）；`healthcheck.sh` 会 FAIL 于其他物理路径。
- 周审计 / 自进化用 macOS `launchctl` + `~/Library/LaunchAgents`，`healthcheck.sh` 用 `/usr/libexec/PlistBuddy`。Linux 需自行换 systemd/cron，本包**未提供**。
- 需要 `python3` + PyYAML、`rg`（`refs-check.sh`）、`bash`。

## 步骤
1. **放真源**：把 idev 目录放到 `~/.cursor/skills/idev/`（不要是 symlink）。grilling 同理放 `~/.cursor/skills/grilling/`。`setup-agents-docs` 放到 `~/.cursor/skills/setup-agents-docs/`（可以是指向它自己真源的软链）。
2. **symlink 别名**：`bash ~/.cursor/skills/idev/scripts/link-idev-aliases.sh` 与 `scripts/link-companion-skills.sh`（建立 `~/.agents/skills/*`、`~/.joycode/skills/*` → 真源；不要复制第二份）。
3. **outbound（产品交出口）**：交出口名单在产线工程 `.idev/handoff.yaml`，由 idev 在交付中识别后写入，并带上 `.idev/marker.yaml`。安装时 `bash ~/.cursor/skills/idev/scripts/bootstrap-outbound.sh --pack <id> [产品仓根]`。不写 `--pack` 且本机没有已记录的安装时，不会猜产品。`state/outbound-config.json` 是安装记录，含本机绝对路径，不要带到别的机器，也不是会话里的当前产品。需要续上的状态留在该工程 `.idev/`。
4. **LaunchAgent（macOS）**：`scripts/install-weekly-audit.sh`（周六 10:00）、`scripts/install-weekly-evolve.sh`（周六 10:15）。不装则 `healthcheck.sh` 报 WARN，不影响核心 PASS。
5. **同伴技能**：grilling 是 S1/S2 强依赖；产线文档目录认 setup-agents-docs，交付时打开 idev 的 `docs/SKILL.md`。缺则 `scripts/link-companion-skills.sh`。没有真源则 healthcheck 报 WARN，且 S1 不得请签 `sealed`、不得临场发明文档目录。
6. **机器本地与产品产线**：产品仓 `.idev/` 里的交出口、流水线、类页跟着仓走。会话残留（traces / proposals / reviews / inbox）也在 `.idev/`，不进内核。内核 `state/traces/`、`state/reviews/*latest*`、`verify/state/inbox/` 只属于导体自身会话。`state/outbound-config.json` 是本机安装记录。`state/ledger.yaml` 的 `confirmed_by` 是人签记录，换人须重新确认。
7. **自检**：`bash ~/.cursor/skills/idev/scripts/healthcheck.sh`（含 `hardcoded-path-check`）；`bash scripts/audit-traces.sh 50`。
8. **票据仓路径**：`<票目录>/` 在当前产品仓；`scripts/ticket-metrics.sh --repo <仓根>` 显式指定。

## hardcoded-path-check 说明
`healthcheck.sh` 会 grep 活文档/脚本中形如 `/Users/<name>`、`/home/<name>/` 的残留（跳过 `state/`、`verify/state/`，它们是本机记录）。OK 只表示**这台机器上扫描无残留**，不代表在别的机器上跑通。

## Linux 调度

见 [linux-schedulers.md](linux-schedulers.md)（systemd user timer / cron）。本机 `healthcheck` 在无 LaunchAgent 时对周任务报 WARN，不拖垮 core。

## 第二产线冒烟（本机可跑）

```bash
bash ~/.cursor/skills/idev/scripts/second-product-smoke.sh
```

断言：临时 generic 仓只靠 `.idev/marker.yaml` 即可 `session-context`；产物不泄漏 joypaas 字样；不改内核源码。

## 未验证 / 未覆盖
- 未在第二台机器、第二个账号、Linux 上跑过完整 healthcheck（模板已给，待实测回填）。
- `state/` 与 `verify/state/` 里历史记录仍含原机绝对路径与人名（未改写历史）。
- 某一产品的内网仓与交出口 Skill 属于该产品自己的环境，不是 idev 的依赖。
