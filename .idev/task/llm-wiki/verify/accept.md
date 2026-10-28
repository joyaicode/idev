# 验收索引

feature: llm-wiki
baseline_revision: 1
runner: python3 scripts/test_claims.py
result: 9 tests OK

| item | case | 证据 |
|------|------|------|
| B1 | ops-exist | ingest、query、calibrate 可执行，退出码不是 2 |
| B2 | no-extra | 脚本 import 不含 lessons、realign、check-feature、requests；check-feature.py 字节不变 |
| B3 | source-required | 来源缺失时摄取退出码 1，不写 claims.yaml；查询输出含 baseline.yaml |
| B4 | ticket-only | claims.yaml 只出现在票目录 |
| B5 | claim-from-artifact | 票外句子不进索引；工件里的主张行会进 |
| B6 | conflict-nonzero | 同一主题两条装不下的句子，校准退出码 1，输出含来源路径 |
| B7 | ledgers-stay | lessons.py 与 realign.py 字节不变，脚本不 import 它们 |
| B8 | guard-doc | 校准非 0 时 design.md 与 req.yaml 字节不变 |
| B9 | guard-code | 点名文件校准非 0 且字节不变；未点名文件退出码 0 |
