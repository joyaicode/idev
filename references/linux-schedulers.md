# Linux 调度模板（可移植补充）

> macOS 用 `scripts/install-weekly-audit.sh` / `install-weekly-evolve.sh`（LaunchAgent）。  
> 本页给 **systemd user units** 等价物；装到第二台 Linux 后请实测并回填 portability-checklist。

## 周审计（对齐周六 10:00）

`~/.config/systemd/user/idev-weekly-trace-audit.service`:

```ini
[Unit]
Description=idev weekly trace audit

[Service]
Type=oneshot
ExecStart=/bin/bash %h/.cursor/skills/idev/scripts/audit-traces.sh 50
```

`~/.config/systemd/user/idev-weekly-trace-audit.timer`:

```ini
[Unit]
Description=idev weekly trace audit timer

[Timer]
OnCalendar=Sat *-*-* 10:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

## 自进化复盘（对齐周六 10:15）

`idev-weekly-evolve-review.service`：`ExecStart=.../scripts/evolve-review.sh`  
`idev-weekly-evolve-review.timer`：`OnCalendar=Sat *-*-* 10:15:00`

启用：

```bash
systemctl --user daemon-reload
systemctl --user enable --now idev-weekly-trace-audit.timer idev-weekly-evolve-review.timer
```

## cron 备选

```cron
0 10 * * 6  $HOME/.cursor/skills/idev/scripts/audit-traces.sh 50 >>$HOME/.idev-audit.log 2>&1
15 10 * * 6 $HOME/.cursor/skills/idev/scripts/evolve-review.sh >>$HOME/.idev-evolve.log 2>&1
```

## 验收

第二机：`bash ~/.cursor/skills/idev/scripts/healthcheck.sh`（LaunchAgent 项在 Linux 上应为 WARN 或跳过，不应拖垮 core PASS）。  
generic 第二产线：`bash ~/.cursor/skills/idev/scripts/second-product-smoke.sh`。
