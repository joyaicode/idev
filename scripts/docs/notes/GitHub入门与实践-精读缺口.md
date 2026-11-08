# 《GitHub 入门与实践》精读缺口报告

> 源文本：`scripts/docs/notes/GitHub入门与实践-全文.txt`（大塚弘记《GitHub 入门与实践》中译，支鹏浩 / 刘斌译，286 页带文本层，经 macOS PDFKit 逐页提取）。本报告为第 61 本精读，对照 `conventions/canon.md`、`conventions/coding-tables.md` 裁定真缺口。
>
> 边界：编号真源仍只认 `canon.md` 的 T/A/F 与 `coding-tables.md` 的 P/C/R；本书「第 N 章」序号只作溯源，不建第二套编号。GitHub 平台功能（Pull Request / Issue / Wiki / Fork / Watch / Star、Travis CI 集成）与 Git 命令是工具知识，不进产品仓真源；可迁移到工程上的「代码审查 / 主干 + 特性分支 / 小步提交 / 持续集成」原则落阶段页，不改 T/C/P/R 计数。

## 一、精读范围

全书 9 章 + 附录读完，主区间如下（行号指 `GitHub入门与实践-全文.txt`）：

- **第 1–2 章 欢迎来到 GitHub / Git 的导入**：社会化编程、Git 与 GitHub 关系、Git 基础（init / clone / add / commit / push / pull）。
- **第 3 章 使用 GitHub 的前期准备**：账户、SSH、配置。
- **第 4 章 通过实际操作学习 Git**：分支操作（branch / merge / 回溯 / 特性分支 / 主干分支）、推送与获取。
- **第 5–7 章 使用 GitHub 的功能 / 尝试 Pull Request / 接收 Pull Request**：Issue / Wiki / Fork / Watch / Star、Pull Request 的发起与接收、代码审查。
- **第 8–9 章 与 GitHub 相互协作的工具及服务 / 使用 GitHub 的开发流程**：Travis CI 持续集成、GitHub Flow / Git Flow。

重点复核段落：Pull Request 代码审查 L1500–L2300；GitHub Flow / Git Flow 开发流程 L2800–L3400；分支操作（特性分支 / 主干分支）L1300–L1600。

## 二、对照结论

### 1. 主体原则已被真源覆盖

| 书中主题 | idev 承载 | 结论 |
|---|---|---|
| 代码审查：Pull Request 让他人审阅、指正、改善 | `code-review` / `requesting-code-review` / `receiving-code-review` 技能；`review.md` 审查者记账 | 承载 |
| 主干 + 特性分支：feature 分支独立开发，合并回主干 | `finishing-a-development-branch` 技能；`git-workflow-and-versioning` 技能 | 承载 |
| 小步提交、每次提交一个逻辑变更 | T6（小步可逆）；R3（两顶帽子不混戴）；R4（小步且步步绿） | 承载 |
| 回溯 / 撤销：回到创建分支前、撤销合并 | R7（会停会退）；A3（回退路径）；`resolving-merge-conflicts` 技能 | 承载 |
| 持续集成：Travis CI 自动构建与测试 | `ci-cd-and-automation` 技能；`verify/SKILL.md` 自测门 | 承载 |
| 知识共享 / 协作：让代码被看见、互相学习 | `agents.md` 角色协作；`review.md` 记账；`docs/SKILL.md` 文档内建 | 承载 |
| 审查效率：只审查 diff、聚焦变更 | `code-review` 技能「review the changes since a fixed point」；T6 触及面 | 承载 |

### 2. 平台功能与命令不落

GitHub 平台功能（Pull Request / Issue / Wiki / Fork / Watch / Star、Travis CI 配置、SSH 配置）与 Git 命令（branch / merge / push / pull / fetch）是工具知识，不进产品仓真源。

## 三、真缺口

**无。** 本书是 GitHub 平台入门，其可推广的工程原则（代码审查、主干 + 特性分支、小步提交、可逆回退、持续集成、知识共享）已全部被 `T6`、`A3`、`R3/R4/R7` 与 `code-review` / `requesting-code-review` / `finishing-a-development-branch` / `ci-cd-and-automation` 技能承载。无新增真缺口。

## 四、重点候选裁定（防后人重复发现）

1. **「Pull Request 代码审查」不另立。** `code-review` 技能与 `review.md` 审查者记账已承载；PR 是 GitHub 平台的审查载体，不是通用规范。
2. **「GitHub Flow / Git Flow」不另立。** `finishing-a-development-branch` 与 `git-workflow-and-versioning` 技能已承载分支收口；具体工作流选型是团队决策。
3. **「Travis CI 持续集成」不另立。** `ci-cd-and-automation` 技能已承载 CI/CD 搭建；具体平台选型不进规范。
4. **「社会化编程 / 知识共享」不另立。** `agents.md` 角色协作与 `review.md` 记账已承载协作与共享；「让代码被看见」是文化，不是可执行规范。
5. **「Issue / Wiki / Fork」不另立。** 平台功能，与代码质量规范无关。

## 五、不建议落的内容

- GitHub 平台操作手册（Pull Request / Issue / Wiki / Fork / Watch / Star / SSH 配置）：工具知识，不进真源。
- Git 命令参考（branch / merge / push / pull / fetch / reset）：命令知识，不进真源。
- Travis CI 配置与集成：CI 平台事实，不进真源。
- GitHub Flow / Git Flow 具体步骤：团队工作流选型，不进规范。
- 附录（Pull Request 详解）：平台功能参考，不进真源。
