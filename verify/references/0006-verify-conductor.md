# 证据导体：同一闭环，五个模式；AI 不盖章

当前入口：`idev`；本决策对应 `idev/verify`。文内 `joypaas-verify` 是历史称谓。

开发验证、排障复现、自测、测试验收、巡检回归共用一条「猜想 → 可运行用例 → 红绿证据 → 人签字」循环。对外是顶层 Skill `idev` 的 verify 模块，对内是 `plan.yaml` + Maven / 脚本；v1 不做独立 CLI 二进制。AI 只提名和执行；`PASS/FAIL/UNPROVEN` 只针对已执行或因缺基线不能执行的用例；需求 / 设计 / 架构由人签。

## Considered Options

- **五套验收器 / 报告模板**：没有红绿，无法定位根因或验收兼容性。拒绝。
- **AI 对需求/架构/性能打分盖章**：与「人批准、AI 执行」冲突；无基线的「达标」是幻觉。拒绝。
- **v1 独立 CLI + 通用 adapter**：编排层再造运行时，且把 JoyPaaS 路径做成插件系统。拒绝；脚本是日后抽 CLI 的缝。
- **影响面由 AI 划定并自动开跑**：漏掉的范围从不出现在报告里。拒绝；`plan` 必须人确认。
- **证据写 `.scratch/`**：本仓禁止再写该目录。拒绝；plan/report 进 `<票目录>/verify/`。

## Consequences

- 真入口只有 `diff+意图`、`现象+环境/产物`、已登记巡检包。禁止整仓漫游。
- 模式 / 维度 / 运行器是**登记表**（`plan-schema.md`），不是 Skill 里写死的五个 if。扩展加行；修正升 `schema_version` 并写 ADR，不改写旧 plan 的证据。
- 生成测试落 `generatedverify/`（gitignore），入库必须人 `promote` 勾选。
- 四仓同一 Skill。产品仓不平行写一套验收流程。
- 试运行评估与进化见 [ADR-0007](0007-verify-conductor-evolve.md)，不在本决策里自动改 Skill。

现行契约：[how-to.md](how-to.md) · [plan-schema.md](plan-schema.md)
