# 有/无 idev 对照评测（阶段 2 §3）

票池起步（人确认）：

- `access-layer-unified-exception`
- `approval-template-config`

每个 case 是冻结夹具，不连真实产品仓。grader 只用确定性检查：

1. 声明的测试命令退出 0（夹具内模拟）
2. `stage-gate` 风格：0 FAIL
3. 改动路径 ⊆ `include`
4. agent 未写签字字段

```bash
python3 test/eval/ab/grade.py --case access-layer-unified-exception --mode with-idev
python3 test/eval/ab/grade.py --all --runs 3
```

`--all` 对每个 case × `{with-idev,without-idev}` 各跑 `--runs` 次，打印通过件数与差值。
