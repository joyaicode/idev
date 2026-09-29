# 运维排障纳入交付生命周期；先分类，证据仍走 verify

当前入口：`idev`；本决策对应 `idev/ops`，红绿走 `idev/verify`。文内 `joypaas-verify` / `joypaas-deliver` 是历史称谓。

`done` 不是生命周期终点。投产后的现象由 ops 模块分类：特征缺陷走 verify `debug` 再回退 deliver；接入坑和集群现场交出现有 Skill。运维排障**不是**新验收权威，也不是第二套测试框架。入口是 `idev`。

## Considered Options

- **把排障步骤写进 joypaas-deliver 当新专家人设**：交付阶段机膨胀，和「先分类」混在一起。拒绝。
- **另建运维验收平台 / 新断言引擎**：与 verify 平行。拒绝。
- **把 onboard-diagnose / jmiss-incident 抄进本 Skill**：两套 Confirm、叠 CORS/PIN。拒绝；只写 handoff。
- **未复现就回退或改基线**：把猜想当结论。拒绝。

## Consequences

- 阶段序：`req-review` → `req` → `arch` → `code` → `test` → `done` ⇄ `ops`。
- `ops.yaml` 只登记分类与回退指针；红绿仍在 `verify/plan.yaml`。
- `defect_origin` 仍只有 `req` / `arch` / `code`。
- 本机实验，不写回产品仓。

契约：[ops-schema.md](ops-schema.md) · [classify.md](classify.md)
