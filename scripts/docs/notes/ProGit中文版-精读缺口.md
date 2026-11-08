# 《Pro Git（中文版）》精读缺口报告

> 源文本：`scripts/docs/notes/ProGit中文版-全文.txt`（Scott Chacon《Pro Git》中译，236 页带文本层，经 macOS PDFKit 逐页提取）。本报告为第 60 本精读，对照 `conventions/canon.md`、`conventions/coding-tables.md` 裁定真缺口。
>
> 边界：编号真源仍只认 `canon.md` 的 T/A/F 与 `coding-tables.md` 的 P/C/R；本书「第 N 章」序号只作溯源，不建第二套编号。Git 命令 / 对象模型 / 内部实现（blob / tree / commit / tag、SHA-1、索引、引用、reflog）是工具知识，不进产品仓真源；可迁移到工程上的「可逆性 / 单一事实来源 / 小步提交 / 分支隔离」原则落阶段页，不改 T/C/P/R 计数。

## 一、精读范围

全书 9 章 + 附录读完，主区间如下（行号指 `ProGit中文版-全文.txt`）：

- **第 1 章 起步**：版本控制（本地 / 集中式 / 分布式）、Git 历史、基础要点（快照而非差异、本地执行、数据完整性、仅添加数据、三种状态）。
- **第 2 章 Git 基础**：初始化 / 克隆、记录更新、查看历史、撤销操作、远程仓库、打标签。
- **第 3 章 Git 分支**：分支与合并、冲突合并、分支管理、分支式工作流（长期分支 / 特性分支）、远程分支、衍合。
- **第 4–5 章 服务器上的 Git / 分布式 Git**：协议、托管、分布式工作流。
- **第 6–9 章 Git 工具 / 自定义 / 与其他系统 / 内部原理**：修订选择、交互式暂存、储藏、重写历史、子模块、合并策略、底层命令与对象模型。

重点复核段落：1.3 基础要点 L397–L460（快照 / 完整性 / 三种状态）；3.1–3.6 分支与衍合 L1800–L2700；2.4 撤销操作 L1250–L1450。

## 二、对照结论

### 1. 主体原则已被真源覆盖

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| 版本控制 = 可逆性：任何提交都可回退、可撤销 | `canon.md` T6（小步可逆）；A3（回退路径）；R7（会停会退）；`finishing-a-development-branch` 技能 | 承载 |
| 直接快照而非比较差异：内容可寻址、单一事实来源 | T7（DRY 是知识单一来源）；A4（数据真相之源） | 承载 |
| 数据完整性：SHA-1 校验和唯一标识内容，防篡改 | C31（凭证 / 敏感数据）；`evidence.md` 产物同源校验 | 承载 |
| 多数操作仅添加数据（append-only），不覆盖历史 | A4（派生 / 副本）；`review.md` 记账不重写 | 承载 |
| 三种状态显式化（工作区 / 暂存区 / 仓库） | `coding.md` §0 声明 CHANGE_KIND / SCOPE / READ / REVERT；T6 两顶帽子 | 承载 |
| 分支隔离：特性分支 / 长期分支，合并与衍合 | `finishing-a-development-branch` 技能；`git-workflow-and-versioning` 技能 | 承载 |
| 小步提交、每次提交一个逻辑变更 | T6；R3（两顶帽子不混戴）；R4（小步且步步绿） | 承载 |
| 撤销 / 重写历史（amend / reset / revert） | R7（会停会退）；`resolving-merge-conflicts` 技能 | 承载 |
| 冲突合并：先理解双方意图再解决 | `resolving-merge-conflicts` 技能；T2（先读后写） | 承载 |

### 2. 工具与对象模型不落

Git 命令（clone / commit / branch / merge / rebase / reset / stash / tag / submodule）、对象模型（blob / tree / commit / tag）、索引与引用、reflog、底层 plumbing 命令、服务器协议是工具与实现知识，不进产品仓真源（`coding.md` 文首「不抄目录」边界）。

## 三、真缺口

**无。** 本书是 Git 权威参考，其可推广的工程原则（可逆性、单一事实来源、数据完整性、append-only、状态显式化、分支隔离、小步提交、会停会退）已全部被 `T6/T7`、`A3/A4`、`R3/R4/R7`、`C31` 与 `finishing-a-development-branch` / `git-workflow-and-versioning` / `resolving-merge-conflicts` 技能承载。无新增真缺口。

## 四、重点候选裁定（防后人重复发现）

1. **「快照而非差异」不另立。** 内容可寻址与单一事实来源已由 T7 / A4 承载；把 Git 的对象模型抽象成通用规范会脱离产品仓语境。
2. **「SHA-1 完整性校验」不另立。** 防篡改与产物同源已由 C31 / `evidence.md` 承载；哈希算法选择是工具事实，不进真源。
3. **「append-only 历史」不另立。** `review.md` 记账与 A4 派生/副本已承载「不重写真相」；git 的 reflog / 重写历史是工具机制。
4. **「三种状态」不另立。** `coding.md` §0 的 CHANGE_KIND / SCOPE / READ / REVERT 已是工程化的状态显式化。
5. **「分支工作流（Git Flow / 特性分支）」不另立。** `finishing-a-development-branch` 与 `git-workflow-and-versioning` 技能已承载；具体工作流选型是团队决策，不进规范。
6. **「衍合 vs 合并」不另立。** 历史整理策略是工具用法；`resolving-merge-conflicts` 已承载冲突解决原则。

## 五、不建议落的内容

- Git 命令手册与对象模型（blob / tree / commit / tag / SHA-1 / 索引 / 引用 / reflog）：工具与实现知识，不进真源。
- 服务器协议与托管（SSH / HTTP / 自建服务器 / GitHub 托管）：部署与平台事实，不进真源。
- 底层 plumbing 命令与内部实现：工具知识，不进真源。
- 子模块 / 钩子 / 自定义配置：工具用法，不进真源。
- 附录（Git 命令速查）：命令参考，不进真源。
