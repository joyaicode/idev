# idev 交出口（handoff）契约

idev **不内置**任一产品的登录/接入、集群事故、脚手架、前端登录态排障正文。  
这些能力通过**当前产品**的交出口 Skill 执行；缺 Skill 时 **停在 handoff**，禁止另写平行 runbook。

S1 拷问依赖 companion `grilling`，落盘依赖 companion `setup-agents-docs`。交付时打开 idev 的 `docs/SKILL.md`。grilling 真源有且只有 `~/.cursor/skills/grilling`（实目录）。`setup-agents-docs` 在 `~/.cursor/skills/setup-agents-docs`，可以是指向它自己真源的软链。`~/.agents` / `~/.joycode` 对两者软引用。缺则：

```bash
bash ~/.cursor/skills/idev/scripts/link-companion-skills.sh
```

## 当前产品的交出口

登记在该仓 `.idev/handoff.yaml`，由 idev 在交付中识别到交出口后写入。同目录的 `marker.yaml` 也由 idev 写下（`marker: idev`），后续会话靠它加载这份名单。内核需要续上的状态放在同一个 `.idev/`。idev 内核 `handoffs/registry.yaml` 的 `packs` 为空，不写产品名、路径或 Skill 名。

缺 Skill 时停在 handoff。安装记录 `state/outbound-config.json` 不是当前产品。`--install` 只按该记录指向的产品仓去读它的 `handoff.yaml`。

```bash
bash ~/.cursor/skills/idev/scripts/bootstrap-outbound.sh --pack <id> [产品仓根]
```

## idev 何时写入

产线用 idev 做交付时，idev 认出产线侧的交出口、类页、流水线或其它需要留存的特性，在要保存状态时写入该工程 `.idev/`：

- `marker.yaml`：`marker: idev`，`id` 取该产线自己的名字；纳入自进化时 `evolve: pilot`
- `handoff.yaml`：当时识别到的接入 / 事故 Skill 目录名
- `pack/`、`workflows/`、`workflow-defaults.yaml`：当时识别到的类页和流水线
- `traces/`、`proposals/`、`reviews/`、`inbox/`：本轮需要续上的状态

下一次会话先读这些文件。内核 `handoffs/registry.yaml` 的 `packs` 保持为空。

## 负例隔离

selfcheck 负例使用 `IDEV_OUTBOUND_NO_HOME=1` 且 `--repo <fixture>`。要测必填时，在该 fixture 里同时写 `.idev/marker.yaml`（`marker: idev`）和 `.idev/handoff.yaml`。
