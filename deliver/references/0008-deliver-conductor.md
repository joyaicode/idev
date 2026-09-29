# 端到端交付：阶段机编排规格/架构/编码，证据仍走 verify

当前入口：`idev`；本决策对应 `idev/deliver`，红绿走 `idev/verify`。文内 `joypaas-verify` 是历史称谓。

AI 端到端交付是 **阶段机 + 回退**，不是新验收权威、也不是第二套测试框架。需求拆解与架构确认之后才编码；编码与提测的红绿仍调用 verify 模块。下游发现缺陷必须定 `defect_origin`、拷问确认，从该阶段改起再向后重跑。`aligned` 须人授权（改 YAML 或确认用语）。

## Considered Options

- **把需求/架构/编码全塞进 joypaas-verify**：验证器变成厨房。拒绝。
- **另建交付平台或新测试语言**：平行流程。拒绝。
- **AI 写「绝对对齐」即完成**：无门槛、不可复验。拒绝；对齐 = 自测门 + 提测门 + 人写 `aligned`。
- **只改代码、需求口头改**：下游证据与规格分叉。拒绝；回退必须作废下游 accepted。

## Consequences

- 机读拆解在 `<票目录>/req.yaml` / `arch.yaml` / `deliver.yaml`；人读规格在 `doc_home.py --key spec` 解析出的路径。
- 不清的边界进 `open_questions`，拷问前不准进下一阶段。
- deliver 模块编排到 `done`；ops 模块接投产后现象；verify 模块只负责可执行证据。入口是 `idev`。
- 试运行同样收反馈、改 Skill 仍须拷问（与 ADR-0007 同一门）。
- 需求评审密封基线见 [ADR-0009](0009-deliver-baseline-seal.md)；本决策不授权下游改 goal。

现行契约：[how-to.md](how-to.md) · [deliver-schema.md](deliver-schema.md)
