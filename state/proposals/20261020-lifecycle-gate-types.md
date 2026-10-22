# 提案增补：生命周期签字补专用 gate 类型（E1.2）

- status: rejected（2026-10-21 人定：减少签字次数，聊天回复确认即认可；不把生命周期闸改成终端批准）
- scope: deliver 生命周期闸（密封 / arch / 提测 / P0 plan / P0 resolved / 回退 / promote）从「导体聊天确认后代写 YAML」改为显式 `idev gate request`，类型与摘要绑定对齐 2026-10-19 提案 3.1 的 A 类闸表
- 不改：B 类决策走 `decisions.yaml` 的既有回路；`step_confirm` 在动作类闸上的既定用途（切片 3）；agent 不签字；`IDEV_ENGINE=python` 回退开关
- 前置：本提案是 [agents-todo.md](../../references/agents-todo.md) E1.2 的增补，推翻/细化 20261019 提案切片 3 的两处偏差记录，需人确认后才可实施

## 一、现状证据（2026-10-20 起草时）

| 事实 | 证据 |
|---|---|
| Go 侧九种 gate 类型已定义（sealed / accepted_req / accepted_arch / accepted_plan / aligned / resolved / step_confirm / defect_origin / reopen_baseline），**无 promote** | `internal/domain/gate/gate.go:29-39` |
| 保证强度矩阵：sealed / reopen_baseline / aligned / defect_origin 在 P0/P1 为 high；accepted_* 与 resolved 仅 P0 high；**step_confirm 全档 low** | `gate.go` defaultAssurance |
| 推导只产两种类型：`with.gate_type` 显式优先；否则 will_write 含 plan.yaml → `accepted_plan`，其余 → `step_confirm` | `scripts/workflow.py:288-299` |
| subject 自动绑定仅一处：`accepted_plan` 且票下有 `verify/plan.yaml` | `scripts/workflow.py:300-305` |
| 27 处配方 `human.gate` 无一显式 `gate_type` / `subject`；10 个配方写 verify/plan.yaml（→ accepted_plan），repo-commit-push、code-review 首闸 → step_confirm | `workflows/` 全目录 |
| deliver-next 的 gate 步是动态 stage 签收，`will_write` 是一句自然语言（非字段列表），推导为 `step_confirm`、无 subject——**生命周期闸全经此单步** | `workflows/deliver-next.yaml:21-25` |
| deliver 各阶段的签字仍由导体在聊天里确认后代写进 YAML；`idev gate request` 能力已有但流程未接，check-feature 也不要求 approval_id | `references/chat-confirm-signoff.md`「签字怎么落笔」节 |
| promote 是不可逆注册（快照 patrol pack）：promote.sh 只查 plan.accepted=true、无 FAIL、PASS 带证据，**无任何 gate** | `verify/scripts/promote.sh:2,19-71` |
| 切片 3 已定：保留 `step_confirm`（动作类）、保留推导、deliver 签字不强制 approval_id（人定） | `state/proposals/20261019-signoff-by-signal.md` 第六节偏差记录 |

## 二、冲突点（本提案要推翻/细化的既定决定）

1. **「保留推导」 vs 专用类型 + 显式 subject。** 推导只识别「写 plan.yaml」一种机械规则；密封 / arch / 提测 / resolved 的 subject 绑定因档位而异（P1/P2 密封绑 baseline+req、P0 只绑 baseline），无法从 will_write 机械推出。扩推导表会把档位逻辑复制进 `workflow.py`，与 `check-feature` 的档位表形成第二份会漂移的真相。
2. **「step_confirm 收动作类」 vs promote 判据。** 3.1 的 A 类闸表把 promote / 生产写列为全档位 A 类、摘要绑动作参数；但 step_confirm 在矩阵里全档 low——若 promote 沿用 step_confirm，P0/P1 只能拿 low + `AllowLowForHigh` 降级审计，与 3.1 的定性不符。
3. **范围不对齐。** 3.1 表列了 `lessons promote`（候选 → 权威）为 A 类，E1.2 判据未提——需明示在不在本提案范围内。

## 三、定稿方案（建议稿，逐条待人否决）

1. **显式声明优先，推导表不扩。** 生命周期闸一律在配方 / 驱动侧显式写 `with.gate_type` + `with.subject`；`workflow.py` 现有推导保留为静态配方闸的兜底。档位差异由调用方（deliver 驱动 / 导体）按权威页决定，不进推导表。
2. **动作类收窄定义，新增 `promote` 类型。** `step_confirm` 仅保留给「确认动作已发生」的闸（git push、回填确认、report 签收）；新增 `TypePromote` 进 defaultAssurance 矩阵（P0/P1 high、P2 low），RequiredKeywords 绑动作参数。promote 前置一次 `idev gate request --type promote`（由驱动在 promote 步先 ask，或 promote.sh 前置脚本拒跑）。
3. **deliver-next 动态闸的映射放权威页 + 驱动查表。** stage →（gate_type, subject 文件）映射表写进 `chat-confirm-signoff.md`（与既有代写字段表同处，单一真相），`deliver.advance` 产出的停问点按当前 stage 查表生成显式请求；票上无该文件时 BLOCKED（不许无摘要开闸）。
4. **密封用既有双摘要形态。** Go 侧已支持 `--type sealed --revision N --subject baseline.yaml`（SubjectBaseline，`cmd/idev/app.go:221-223`），P1/P2 加绑 `req.yaml` 即可直接复用，无新开发。
5. **`lessons promote` 不纳入本提案**，在 agents-todo.md E 系列单列待议项（lessons 回路有自己的上下文，混入会扩大审阅面）。
6. **本提案不启用 E1.1 强制。** 人已定 deliver 阶段先不强制 approval_id；落地只要求「判据中的每个生命周期闸各有一次 request」进 golden / 冒烟锁定，check-feature 侧强制留给 E1.1 另议。

## 四、拷问记录（预填待答）

| 轮 | 问题 | 建议 / 待定 |
|---|---|---|
| 0 | 生命周期闸走显式声明还是扩推导表 | 建议显式（方案 1） |
| 0 | promote 新类型还是沿用 step_confirm | 建议新类型（方案 2，保证强度） |
| 0 | deliver-next 动态闸的 stage 映射放哪 | 建议权威页 + 驱动查表（方案 3） |
| 0 | lessons promote 是否纳入 | 建议不纳入、单列待议（方案 5） |
| 0 | git push 是否一并升类型 | 建议不动（切片 3 已定，保持动作类） |
| 1 | promote 的 gate 发起点：驱动 ask 还是 promote.sh 前置拒跑 | 待定（方案 2 留了两条路） |
| 1 | 票上缺 subject 文件时开闸还是 BLOCKED | 建议 BLOCKED（方案 3） |

## 五、实施切片（草案，每片自带测试、单独可回滚）

1. **Go 类型**：`TypePromote` + 矩阵（P0/P1 high）+ RequiredKeywords + `cmd/idev` 校验；Go 单测锁定新类型全路径。
2. **驱动显式化**：静态配方闸补 `with.gate_type` / `with.subject`；deliver 动态闸按 stage 查表发显式请求；golden 重录 + `test/gate-channel.sh` 增生命周期闸用例（sealed 双摘要、promote、缺 subject BLOCKED）。
3. **promote 闸与权威页**：promote 步前置 gate request（发起点按拷问记录定夺）；`chat-confirm-signoff.md` 删「由导体代写」表述、改为 gate 通道 + stage 映射表；`refs-check` 过。

## 六、落地条件

- 上述拷问记录由人逐条定夺后，status 才可改 implemented（由人标，AI 不代标）。
- 全量自检链（syntax / agents / workflow / refs / selfcheck / agent-smoke / go test / gate-channel / lease-channel）PASS 后方可宣称切片完成。