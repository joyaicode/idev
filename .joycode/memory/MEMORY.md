- [隐形字符文件的编辑与验证方式](feedback_editing_invisible_chars.md) — 本仓库编辑含转义/隐形字符的文件（如 cases.yaml）时必须用终端+Python heredoc，且码点分析只能靠 Python，不能信终端渲染

- [Go 迁移 golden 安全网机制](project_go_migration_golden.md) — Python→Go 迁移期间，cases.yaml 双端共享 + 50 个 golden 快照 + record.sh PYTHONUNBUFFERED 确定性锁定的验证机制（2026-10-19 全链验证通过）

- [idev 设计文档 v3 位置与验收提案结构](reference_design_doc_v3.md) — 重构设计文档已入仓 design/idev-refactor-design-v3.md（提交 b96b6c9，2026-10-19）；验收提案 state/proposals/ 下 20261016（A/B/C/D 四组）与 20261019（签字按信号，切片 1–3 已落）
