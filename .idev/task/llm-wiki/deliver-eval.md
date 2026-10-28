# deliver-eval

feature: llm-wiki
stage: done
risk_tier: P1
check_feature: PASS（check-feature.sh llm-wiki test，0 FAIL；随后 aligned=true，stage=done。check-feature 没有 done 档）

| 计数 | 值 |
|------|----|
| baseline_items | 9 |
| slices | 9 |
| case_intents | 9 |
| plan_cases | 9 |
| plan_pass / fail / unproven | 9 / 0 / 0 |
| open_questions | 0 |
| baseline_conflict | 0 |

冲突已合上：2026-10-28 人定方案和用例继续收录，只作对照；和审过的需求或规格冲突就停。这是 B5 加 B6 的现行为：同一主题两句互相装不下，或句子不在来源里，校准退出码非 0。不另开规格文件，不改基线，不写 `reopen_baseline`。审过的需求和规格人机同一份，是权威。其它阶段文档不是权威知识库。文档体例已写上权威、先校准再生成，以及整理时拆过时人读产物再重做。本轮未删文件。
