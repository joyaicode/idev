# 语义门（人检 + 脚本锁，防「结构绿、语义漂」）

`check-feature` 锁两件可机检的事，**不判断口号是否可证伪**。结构绿 ≠ 语义锁死。其余仍须人扫句子：

1. `req` 及之后：每条 `slice.must` 与对应 item 的 `must`（无则 `must_not`）原文一致（空白归一）。换词 = FAIL。
2. `req` / `arch` / `code` / `test`：`deliver.yaml` 里**上一阶段**的 `semantic_gate.<stage>.passed: true` + 人名 `by`。与 `sealed` / `accepted` / `aligned` 同一次确认写入；Agent 不得代填。

**本表必须人扫脚本锁不住的句子**；Agent 请签前打印。人未确认不准 `sealed` / `accepted` / `aligned`。

对照尺：密封 `baseline.yaml` 的 `goal` / `non_goal` / `items[].must`。

## req-review → sealed

- [ ] 每条 item 的 must 可证伪，不是口号
- [ ] non_goal 盖住「容易顺手做大」的面
- [ ] 与 CONTEXT / 点名 ADR 冲突已写成问题，不是默许

## req → accepted

- [ ] 每条 slice 的 must **原文复述**对应 `baseline_item_id`（脚本已锁；无新增义务）
- [ ] 无「为了好实现」改写的约束（换词 = 超基线 = 脚本 FAIL）
- [ ] 每个 baseline item ≥1 条 slice；无孤儿 item

## arch → accepted

- [ ] approach / case_intent 未改写 goal / non_goal
- [ ] 每个 intent 挂对 `baseline_item_id`；没有「更好但更大」的范围
- [ ] `include: true` 路径足以覆盖 item；未 include 的不假装已设计

## code → 自测门 / 请提测前

- [ ] 实现与 review「少做/多做」对照基线；多做已删或 UNRELATED
- [ ] 未用代码「修正」需求；像基线错 → `baseline-conflict` 停
- [ ] 编码规范命中已改（P#/C#/R# + §3.8），不是只记账

## test → aligned

- [ ] 每条 item 有可执行 case 或显式 `UNPROVEN`+理由（见 [unproven-gate.md](../../verify/references/unproven-gate.md)）
- [ ] 无把 non_goal / 未覆盖面写成 PASS

人签时口头或回复确认：「语义门已过」或勾完本表。Agent 不得代勾。
