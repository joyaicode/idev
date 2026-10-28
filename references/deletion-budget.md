# 内核删除预算（阶段 2 §5）

每条内核迭代里，提示词 / 规则 / 配方相关路径的**删除行数应不少于新增行数**。只计数，不设阈值门禁。

## 范围

`scripts/` `agents/` `references/` `workflows/` `hooks/` `cmd/` `internal/` `ops/` `deliver/` `verify/`

不算：golden 夹具、`state/`、生成物、产品仓。

## 怎么看

```bash
python3 scripts/deletion-budget.py --since HEAD~30
```

`ratio > 2.0` 或「窗口内零删除」只打印 WARN。

## 配套

- 每周：`bash scripts/weekly-outcome.sh <product-repo>`（含 curator 与 usage-scan）
- 过期提案：`bash scripts/evolve-curator.sh --apply`
- 零用量配方：`python3 scripts/usage-scan.py --repo <product> --days 60`（确认后再 `--apply`）
