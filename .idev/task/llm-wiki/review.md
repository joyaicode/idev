# Review（对照密封基线，不是对照心情）

feature: llm-wiki
baseline_revision: 1
by: wangwei794

## 少做（基线 item 未落地）

- item: 无
  evidence: B1–B9 都有 case，`python3 scripts/test_claims.py` 9 tests OK。摄取写入 `.idev/task/llm-wiki/claims.yaml`，校准退出码 0。

## 多做（基线外行为）

- 路径: 无
  处理: 未加向量库、健康分、模型判断、lessons/realign 入口或 check-feature 门禁。

## 基线冲突

- 无

## 编码规范（对照 `conventions/coding.md`，当轮纠正）

编号只认 `conventions/coding.md` §3.5。本轮是新脚本，不是重构。

- 场景命中: 零命中
- 气味命中: 无（已扫）
- 纠正: 无。`named` 曾有 4 个参数，`problems` 的三层循环超过 2 层，已拆成 `names`、`source_files`、`missing_sources`、`contradictions`。`slice_records` 22 行、`main` 22 行，落在 21–25：前者只校验切片主张并在第一句对不上时停，后者只分发四个子命令，不拆。
- 重构: 无
- 五轴: 正确性过；可读性过；架构过；安全过；性能过
- 栈指南: python
- 增强扫描: 已跑 coding-scan，lang 插件 convention 0
- 审查者: idev-reviewer
- 文件与行数: 触及 3 个文件，新增 3，最长 277 行
- 扫描: lang 插件 convention 0

## 本轮允许改的路径

只许 `arch.yaml` 里 `include: true` 的文件。

- include: `scripts/claims.py`、`scripts/test_claims.py`、`references/claim-index.md`
- UNRELATED: 票目录里的签字与用例记录，以及仓库里不属于这三份的既有改动。本审查不改它们。

## 架构范式（T# / A#，可选节，见 conventions/canon.md §7）

- 本轮命中 `T#`：T1 一个脚本；T10 索引是派生的，失败是非 0 退出。已扫 canon §2 信号与 §4 念头，无向量库、无健康分、无耗时优化。
- 所做动作：三份新文件，不改 lessons.py、realign.py、SKILL.md、check-feature。
- `arch` 阶段 A1–A8（canon §5）：已答。回退是停用脚本并删除该票 claims.yaml。
