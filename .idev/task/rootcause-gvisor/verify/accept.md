# 验收索引

feature: rootcause-gvisor
baseline_revision: 1
runner: python3 scripts/test_runsc_probe.py
result: 8 tests OK
evidence: verify/evidence/selftest-rerun.log

| item | case | 证据 |
|------|------|------|
| B1 | C1 | `test_rootcause_invokes_runsc_and_does_not_write_the_repo`：假 runsc 被调用，宿主仓库没有片段要新建的文件 |
| B2 | C2 | `test_missing_runsc_does_not_run_on_the_host`：PATH 无 runsc 时进程退出码不等于 0，宿主上新建个数为 0 |
| B3 | C3 | `test_check_rejects_a_transcript_without_a_receipt`：没有 `runtime: runsc` 回执时 check 退出码不等于 0 |
| B4 | C4 | `test_other_steps_stay_on_the_host`：`--step arch` 在宿主执行，票目录只有 1 个 transcript |
