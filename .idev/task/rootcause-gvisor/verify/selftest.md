# selftest

feature: rootcause-gvisor
command: python3 scripts/test_runsc_probe.py
result: 8 tests OK
evidence: verify/evidence/selftest-rerun.log

复跑在 I1–I5 落地之后。`Ran 8 tests`，`OK`，进程退出码 0。

本机是 darwin/arm64，PATH 上没有真 runsc。用例用假 runsc 锁住调用参数：rootcause 不在宿主执行片段，缺 runsc 时不落宿主，其它 step 仍在宿主。
