# 交付生命周期

一个入口，四个内聚模块（公共规约 + 交付 + 证据 + 排障），两个交出口。尺是密封基线；红绿是 verify。执行前先对公共规约类。

```
req-review → req → arch → code → test → done ⇄ ops
    │         │      │       │      │
    └─────────┴──────┴───────┴──────┴── verify（logic / selftest / test / debug / patrol）
```

| 阶段 | 模块 | 人签 | 证据 |
|------|------|------|------|
| `req-review` + `req` | deliver | 一次：`sealed` + `accepted` | 不明确的问题一轮问完；切片覆盖 item |
| `arch` | deliver | 一次：方案整体 Review | `design.md` + `case_intent` |
| `code` | deliver | 自测完成后一次：实现审核 | 用例 + 编码 + verify `selftest` |
| `test` | deliver | 一次：`aligned` | verify `test` 的结果 |
| `done` | — | 上一行的提测结果确认 | 基线仍密封 |
| `ops` | ops | `resolved` / origin | verify `debug` / `patrol` 或 handoff |

## 交出口（不准抄进模块）

产品专属正文走该产品的 handoff Skill，缺则停在 handoff。名单在当前产品仓 `.idev/handoff.yaml`。idev 不登记产品 Skill 名。

## 回退

人确认 `defect_origin` 后：`req` / `arch` / `code`（reopen 才回 `req-review`）。  
从 origin 再正向走完才能回到 `done`。

## 缝与门（修复后）

| 缝 | 门 |
|----|----|
| 结构绿、语义漂 | `slice.must` 原文锁 + `deliver.semantic_gate` + [semantic-gate.md](../deliver/references/semantic-gate.md) 人检 |
| 提测面不够仍 aligned | [unproven-gate.md](../verify/references/unproven-gate.md)：维表六族有 case 或显式 UNPROVEN |
| ops 外送 Skill 缺失 | `check-feature ops` 内跑 `outbound-skills-check.sh`（仓内 `.cursor/skills` + 本机） |
| S8 跳过签字 | workflow-schema「签字不可跳过」 |
| Java8 仓误用现代语法 Skill | [coding-tables.md](../conventions/coding-tables.md) §3.6 边界 |

## 非目标（一等公民不做）

| 环节 | 落点 |
|------|------|
| 仓内 CI / MR 门禁 / 发布流水线 | 产品仓流水线。idev 不替代、不加主阶段 |
| 整仓代码审查 | S8 `code-review` 旁路配方，不进阶段机 |
| 提交推送 | S8 `repo-commit-push` 旁路配方 |
| 安全审查独立维 | 无 `dimension=security`；触及身份/密钥再开 `security-and-hardening` |
| 导体数字总分 | 禁止。评审只写发现 + 证据 |
| 导体自身改动的产品仓票 | 不走。验收是 chat-confirm + `state/ledger.yaml` revision；`phase: trial`，ga 须另一次人确认 |
| 把某一个产品写成 idev 本体 | 禁止。当前产品只是使用方 |
| 把未剥离的产品专有逻辑写进 idev 核心 | 禁止。先写成对所有产品成立的句子，否则只留在该产品仓 |

## 外部框架对照

aisel（ai-software-engineering-lifecycle）概念如何映射到本生命周期、哪些采纳哪些不采纳：[aisel-mapping.md](aisel-mapping.md)。
