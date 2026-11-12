# report

feature: rootcause-gvisor
mode: test
runner: python3 scripts/test_runsc_probe.py
evidence: verify/evidence/selftest-rerun.log

| case | status | 落点 |
|------|--------|------|
| C1 | PASS | test_rootcause_invokes_runsc_and_does_not_write_the_repo |
| C2 | PASS | test_missing_runsc_does_not_run_on_the_host |
| C3 | PASS | test_check_rejects_a_transcript_without_a_receipt |
| C4 | PASS | test_other_steps_stay_on_the_host |

UNPROVEN 面：concurrency、performance、ui-prototype，见票目录 `unproven.md`。这三面不在密封基线里。

本机没有真 runsc。假 runsc 证明 cmd_run 把 rootcause 交给 runsc、缺二进制时不在宿主执行。它不证明 gVisor 拦下了系统调用。non_goal 写明本票不装虚拟机、不提交 runsc 二进制。

## conductor-eval

| 计数 | 值 |
|------|----|
| cases_pass | 4 |
| cases_fail | 0 |
| cases_unproven | 0 |
| unproven_reasons | 无。三面写在 unproven.md，不是 case |
| impact_nominated | 0 |
| impact_included | 5 |
| signoff_pending | 0 |
| feedback_status | none |

诚实性：四条 PASS 的 evidence 都是 `verify/evidence/selftest-rerun.log`。human_signoff 没有写成 ACCEPTED。本轮没有 hop > 1 的候选。
