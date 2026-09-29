# 需求评审密封基线；后续阶段不得改写；每阶段按专家拒过清单

在拆解之前增加 `req-review`：拷问到正确、合理、边界与细节无异议后密封 `baseline.yaml`。之后拆解 / 架构 / 编码 / 测试的验收只对齐这条基线。下游反馈可以改实现和切片译法，**不能改 sealed 原文**。要改基线只能人显式解除密封，回到 `req-review` 再拷问。

各阶段「资深专家」= 该阶段拒过清单（`experts.md`），不是角色扮演。

## Considered Options

- **后续阶段发现需求不好就改 goal**：评审作废，验收失去固定尺。拒绝。
- **不设评审、拆解时一边拷问一边改需求**：与「先评后做」冲突。拒绝。
- **专家 = 加长人设提示词**：不可检查。拒绝。
- **基线冲突时 Agent 自行改 baseline**：推翻评审。拒绝；只许 `baseline-conflict` 停住，或人 reopen。

## Consequences

- 阶段序：`req-review` → `req` → `arch` → `code` → `test` → `done`。
- `defect_origin` 不含「在 test 里改基线」。origin=`req-review` 仅当人写 `reopen_baseline`。
- `deliver` schema_version = 2。
- 切片 / case 必须挂 `baseline_item_id`。

契约：[deliver-schema.md](deliver-schema.md) · [experts.md](experts.md)
