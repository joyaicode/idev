- [隐形字符文件的编辑与验证方式](feedback_editing_invisible_chars.md) — 本仓库编辑含转义/隐形字符的文件（如 cases.yaml）时必须用终端+Python heredoc，且码点分析只能靠 Python，不能信终端渲染

- [Go 迁移 golden 安全网机制](project_go_migration_golden.md) — Python→Go 迁移期间，cases.yaml 双端共享 + 39 个 golden 快照 + record.sh PYTHONUNBUFFERED 确定性锁定的验证机制（2026-10-17 状态）

- [idev 设计文档 v3 位置与验收提案结构](reference_design_doc_v3.md) — 重构设计文档在仓外 ~/Downloads/idev-refactor-design-v3.md（2026-10-17 增补质量门）；验收提案 state/proposals/20261016-*.md 现为 A/B/C/D 四组
