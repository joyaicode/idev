# selftest

feature: llm-wiki
command: python3 scripts/test_claims.py
result: 9 tests OK

复跑在拆开 `problems` 与 `named` 之后，结果仍是 9 tests OK。

ingest: `python3 scripts/claims.py ingest --feature llm-wiki` 退出码 0
calibrate: `python3 scripts/claims.py calibrate --feature llm-wiki` 退出码 0
