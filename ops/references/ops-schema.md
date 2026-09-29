# 运维排障契约（schema_version 1）

不另起测试框架。红绿字段仍在 verify 模块的 `plan.yaml`。本文件只登记**分类与回退指针**。

| 产物 | 路径 | 家 |
|------|------|-----|
| 排障单 | `<票目录>/ops.yaml` | 本契约 |
| 红绿 | `<票目录>/verify/plan.yaml` | verify 模块 |
| 回退指针 | `<票目录>/deliver.yaml` | deliver 模块 |
| 巡检包 | `doc_home.py --key patrol` | verify `promote` |

扩展加本表。不兼容升 `schema_version` + 本机 ADR。未知字段忽略。

## `ops.yaml`

| 字段 | 约束 |
|------|------|
| `schema_version` | 整数，当前 `1` |
| `feature` | 与 `<票目录>/` 同名 |
| `kind` | `onboard` \| `runtime` \| `feature` \| `patrol` \| `unknown` |
| `status` | `open` \| `classified` \| `reproducing` \| `root-caused` \| `rewound` \| `handed-off` \| `resolved` |
| `phenomenon` / `env` / `artifact` / `observable` | 现场四件；缺则不准离开 `open` |
| `baseline_revision` | `kind=feature` 时必须等于密封基线 revision |
| `suspect_item_ids` | 基线 `items[].id` 子集；无对应 item 则空并考虑 `baseline-conflict` |
| `defect_origin` | 空，或人确认后的 `req` \| `arch` \| `code` |
| `handoff` | `kind=onboard` / `runtime` 填当前产品 `.idev/handoff.yaml` 里的 Skill 名；`feature` / `patrol` / `unknown` 空 |
| `resolved` | 人改 `true` |
| `by` | 签字人；AI 不得填 |

`status=handed-off`：本 Skill 停，后续不写 feature 根因。  
`status=rewound`：`deliver.yaml.stage` 已回到 origin。  
`status=resolved`：须同时有人填的 `by:`。

## 与阶段机

- 当前 `deliver.yaml.stage == done`：可把 stage 写成 `ops`。
- 当前在 `req-review`…`test`：就地 debug，**不准**把 stage 跳成 `ops`。
- 回退后按 deliver 正向重走；关闭且无回退则 stage 回 `done`。
