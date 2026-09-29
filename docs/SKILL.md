---
module: docs
parent: idev
---

# 产线文档

由 `idev` 在交付里归类和落盘产线文档时调起。本目录不是独立 Skill。它不另定目录，也不另写问法。

| 认什么 | 打开 |
|---|---|
| 目录 | `~/.cursor/skills/setup-agents-docs/SKILL.md` 的 Rule 4（feature slug）和 Rule 10（`docs/` 目录表） |
| 问句 | `~/.cursor/skills/grilling/SKILL.md` |

两份都打不开时，先跑 `bash ~/.cursor/skills/idev/scripts/link-companion-skills.sh`。仍打不开就停，不要临场发明一套 `docs/` 布局。

`setup-agents-docs` 的一次性安装（explore、确认、写 `AGENTS.md`）不是每张票的步骤。只有人明确要给还没有这套文档的仓库做初始化时，才按那份技能的 How to run 执行。

## 何时与交付一起打开

- S1 落票，以及写需求、规格、测试设计、票目录之前。与 `deliver/SKILL.md`、grilling 同一轮打开。
- S5 契约或经验回填。
- 本轮要新建或移动产线文档。

执行模块仍只开一个。本技能和 grilling 一样，是交付时额外打开的同伴技能。

## 落点

```bash
python3 ~/.cursor/skills/idev/scripts/lib/doc_home.py --repo <仓根> --feature <feature> --key task
```

`--key` 还可以是 `prd`、`spec`、`test-case`、`patrol`、`deliver`、`plan`。

仓库已经同时有 Matt Pocock 的 feature slug 和 grilling 时，新文档归进规范目录。同一文件也在 `.idev/` 时，读规范目录里的那份，副本留在磁盘上，不覆盖规范正文。

还没有这套文档时，不在仓库根新建 `docs/`。阶段状态写 `.idev/task/<feature>/`，人读稿写 `.idev/docs/` 下同名相对路径。问句仍按 grilling 写。票只存在于一边时，留在那边。

## 规范里的同一 feature

一个需求一个 kebab-case `<feature>`。下面四条是 setup-agents-docs Rule 4，不是 idev 自定的：

| 角色 | 已有规范时 | 还没有这套文档时 |
|---|---|---|
| 需求 | `docs/prd/<feature>.md` | `.idev/docs/prd/<feature>.md` |
| 人读规格 | `docs/spec/<feature>.md`（仓声明 `docs/specs/` 时用复数） | `.idev/docs/spec/<feature>.md` |
| 测试设计 | `docs/test-case/<feature>.md` | `.idev/docs/test-case/<feature>.md` |
| 本地 issue 与 idev 机读票 | `docs/task/<feature>/` | `.idev/task/<feature>/` |

Rule 10 里其余目录（`docs/adr/`、`docs/convention/`、`docs/agents/`、`docs/prototype/` 等）有内容才建，不预铺空目录。不使用 `.scratch/`。

产线 `AGENTS.md` 或 `docs/agents/issue-tracker.md` 写了 `docs/specs/` 时，规格目录就是复数 `docs/specs/`，不要改名成 `docs/spec/`。没写时用上表的 `docs/spec/`。`.idev/docs/` 下一律用 `spec/`。另一种拼法下只有一份时仍读那份。两份同时在时，以规格目录那份为准：把另一份里还没有的正文并入，然后删除另一份。巡检包是同一测试设计目录下的 `<feature>-patrol.yaml`。

idev 的阶段文件都放在票目录里，文件名以各模块契约为准：交付看 `deliver/references/deliver-schema.md`（`baseline.yaml`、`req.yaml`、`deliver.yaml` 等），验证看 `verify/references/plan-schema.md`（`verify/plan.yaml`、`unproven.md`），排障看 `ops/references/ops-schema.md`（`ops.yaml`），配方看 `references/workflow-schema.md`（`workflow/run.yaml`、`lessons/`）。另有本页的 `grill.md` 和编码评审 `review.md`。契约里没有的文件名不要临场新建。规范目录里还可以有 setup-agents-docs 的 `issues/`。

三处 review 不是同一份：

| 路径 | 是什么 |
|---|---|
| `<票目录>/review.md` | idev 编码评审，code 阶段对照基线 |
| `<票目录>/reviews/` | checklist 记录，有真实 checklist 才建 |
| `.idev/reviews/` | 执行残留。`execution-clean` 只删这里 |

## 问句

未决问句只写在该 feature 的 `grill.md`。下面三行各自单独成行：

```
convention: grilling
frontier: empty
shared_understanding: true
```

正文用 grilling 的问句行（`❓ **Q1** - **主题**:`）和推荐答案行（`➡️`）。`frontier` 只许 `empty` 或 `open`，且各只出现一次。基线 `sealed: true` 时这份文件必须在，且 `frontier: empty`、`shared_understanding: true`。

`baseline.yaml` 里若还有 `status: open` 或未清空的 `objections`，关闭的 `grill.md` 盖不过去。新的未决问题写进 `grill.md`，不要在 YAML 里再开一份问句。grilling 接着问时读同一票目录的 `baseline.yaml` 和规格文件。

## 冲突

已有的规范文档优先于 `.idev` 里的同名副本。人读规格与密封基线不一致时，改规格，不改基线（除非人 reopen）。

已经写在 `.idev/task/` 或 `.idev/docs/` 的票不是执行残留，清理不删。产品仓用 `.idev/*` 忽略残留时，若还有这类票，保留 `!.idev/task/`、`!.idev/task/**`、`!.idev/docs/`、`!.idev/docs/**`。

密封 `baseline.yaml` 的 item 不因后确认改写。后确认进 `docs/adr/` 或 `docs/convention/`。规格已落地则规格文件只留指针。验收报告写明「密封原文 vs 现行代码」，禁止为了绿测去改基线。
