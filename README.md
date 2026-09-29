# idev（本地快照）

人机共驾的端到端交付生命周期导体。真源路径：`~/.cursor/skills/idev/`。

本仓库是 **2026-09-30 workflow 重构完成后的本地暂存**：已 `git init` 在 `main`，尚未推到 GitHub（本机 `gh` / SSH 当时未授权）。日常使用仍直接读这个目录；别名链到 `~/.agents/skills/idev`、`~/.joycode/skills/idev`。

## 目录

| 路径 | 作用 |
|------|------|
| `SKILL.md` | 唯一入口与场景路由（S1–S8） |
| `workflows/` | 内核编排配方（任何产线都能用） |
| `scripts/workflow.py` | 按配方驱动 `run.yaml`（不替 Agent 执行步骤） |
| `scripts/workflow-check.py` | 校验配方与 run |
| `scripts/lib/workflow_spec.py` | 编排语法的代码形态（kind / 顶栏 / 策略） |
| `scripts/lib/workflow_defaults.py` | 读扩展根 `.idev/workflow-defaults.yaml` |
| `scripts/s8-preflight.sh` | S8 前置探针 |
| `references/workflow-schema.md` | 编排语法（给人看） |
| `deliver/` `verify/` `ops/` `docs/` `conventions/` | 阶段模块与规约 |
| `state/` | 仅导体自身会话的中间产物；产品会话写到该仓 `.idev/` |

产线流水线不写进本仓。当前试点产线配方在：

`~/go/src/coding.jd.com/joypaas/.idev/workflows/`

其它产品仓只留 `marker.yaml` + `extension_root: ../joypaas`（或等价相对路径）。

## 本机自检

```bash
cd ~/.cursor/skills/idev
bash scripts/workflow-check.sh
bash scripts/selfcheck.sh
bash scripts/healthcheck.sh
```

期望：`PASS` / `selfcheck PASS` / `healthcheck PASS`。

## 驱动一次配方（产品仓内）

```bash
W=~/.cursor/skills/idev/scripts/workflow.py
cd ~/go/src/coding.jd.com/kafka-project   # 任意带 marker 的产品仓

$W resolve localdev-start                # 经 extension_root 找到 joypaas 配方
$W start localdev-start --param product=kafka
$W next
$W record <step> PASS --evidence …
$W status
```

要票配方加 `--feature <票名>`。停问步（`human.gate`）记 PASS 必须带人的 `--by` 与确认用语 `--quote`（确认 / 全签 / 同意 / LGTM）。

## 推到 GitHub（以后）

仓库已在本目录初始化。授权后再推：

```bash
brew install gh          # 若未装
gh auth login --web --scopes repo
cd ~/.cursor/skills/idev
gh repo create idev --private --source=. --remote=origin --push
```

或把远端地址换成你账号下已有空仓：

```bash
git remote add origin git@github.com:<你的账号>/idev.git
git push -u origin main
```

## 提交点

| commit | 说明 |
|--------|------|
| `912c836` | workflow 三件套快照（语法 / 校验 / 驱动 + 14 份内核配方） |
| （本说明之后） | 补齐 `will_write` 校验说明 + 本 README |

变更细节见 [references/changelog.md](references/changelog.md)。使用说明见 [references/guide.md](references/guide.md)。
