# aisel 对照与取舍记录

idev 与外部框架 **ai-software-engineering-lifecycle（aisel）** 的对照。供查阅「某 aisel 概念在 idev 里落在哪 / 为什么某些没采纳」。**本页不是执行页**，执行仍按 deliver / verify / conventions。

## 六阶段对照

| aisel Stage | idev 阶段 | 人签点 |
|-------------|-----------|--------|
| Stage 0 问题定义与范围 | `req-review` | `sealed` |
| Stage 1 需求工程 + INVEST | `req`（判据 [req-quality.md](../deliver/references/req-quality.md)） | `accepted` |
| Stage 2 领域建模与通用语言 | `arch` 透镜（[domain-modeling.md](../conventions/domain-modeling.md)） | 并入 arch |
| Stage 3 架构与模块设计 | `arch`（范式 [canon.md](../conventions/canon.md)） | `accepted` |
| Stage 4 实现与验证（TDD） | `code` + verify `logic`/`selftest` | 自测门 |
| Stage 5 发布与演进 | `test` + `done` | `aligned` |

idev 额外有 `ops`（投产后排障）——aisel 无对应，走 idev ops 模块。

## 三层角色对照

| aisel 角色 | idev 落点 |
|------------|-----------|
| Planner（规划） | deliver `req-review`/`req` + baseline 密封 |
| Generator（生成） | deliver `code` + verify `logic`/`selftest` |
| Governor（治理） | [experts.md](../deliver/references/experts.md) 拒过清单 + [gates.md](../deliver/references/gates.md) + `check-feature.sh` |

idev 不设独立"角色状态机"——职责由阶段机 + 拒过清单 + 人签字承担。

## 已采纳并融入

| aisel 元素 | 融入落点 |
|------------|----------|
| 量化代码阈值（函数≤20行 / 参数≤3 / 复杂度≤10） | [coding-tables.md](../conventions/coding-tables.md) §2.4 |
| INVEST / SMART / 验收量化 | [req-quality.md](../deliver/references/req-quality.md) |
| 有界修复终止条件（失败签名3次→升级人工） | [evidence.md](../conventions/evidence.md) 第5步 |
| 领域建模 / 通用语言 / 限界上下文 / 聚合根 | [domain-modeling.md](../conventions/domain-modeling.md) |

## 不采纳（护栏：勿再搬入）

| 不采纳 | 原因 |
|--------|------|
| 100 分制质量评分 | 与 idev 反分数内核冲突。红绿只认 `PASS`/`FAIL`/`UNPROVEN` + 人签字（verify/SKILL.md）；[lifecycle.md](lifecycle.md)「导体数字总分：禁止」 |
| 90 分绿色通道自动放行 | 放行只由人签字，不由分数阈值。分数会诱导凑分而非真验证 |
| LLM judge 当落地门禁 | verify/SKILL.md 明列「不要做」；导体评审只写发现 + 证据，不给总分 |

## 反模式为何未单列

aisel 的设计/实现反模式（浅模块、循环依赖、深嵌套、函数过长）**已被覆盖**，不重复造表：
- 编码级：[coding-tables.md](../conventions/coding-tables.md) 的 P/C/R 表（C9 嵌套 ≤2 比 aisel ≤3 更严）。
- 架构级：[canon.md](../conventions/canon.md) 的 T/A/F 表。

新增只补 idev 真缺的量化线与判据，不与既有真源重叠（守"真源唯一"）。
