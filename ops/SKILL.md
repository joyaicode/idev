---
module: ops
parent: idev
---

# Ops 模块（运维排障）

由 `idev` 按内容调起。本目录不是独立 Skill。  
交付生命周期的**最后一环**，不是新验收权威，也不是第二套测试框架。  
先**分类**，再取证。红绿只调用 verify 模块（`debug` / `patrol`）。  
先跑 `python3 ~/.cursor/skills/idev/scripts/session-context.py --repo <仓根> --feature <feature> --scenario S6 --stage ops [--product <点名的产品>]`，打开每一行 `OPEN`。路径写入 trace 的 `extensions`（没有页就写 `extensions: []`）和 `opened`。  
特征缺陷回退 deliver 的 `req` / `arch` / `code`。接入坑和集群故障**交出去**，不要抄进本模块。  
`ops.yaml` 写在 `<票目录>/`。`<票目录>` 只认 `doc_home.py --key task`。

## 本阶段 5 步（先做这些）

1. `session-context.py`（S6/ops）→ 只开 `OPEN`。
2. 写齐 `ops.yaml`：phenomenon / env / artifact / observable + `kind`（禁长期 `unknown`）。
3. `check-feature.sh <f> ops`；红绿只走 verify `debug`/`patrol`。
4. `onboard`/`runtime` 只写 handoff，不抄交出口正文；不自动做生产写操作。
5. `resolved` 须人名 `by`；`trace.sh append`。

| Need | Doc |
|------|-----|
| 怎么用 | [references/how-to.md](references/how-to.md) |
| 分类 | [references/classify.md](references/classify.md) |
| 契约 | [references/ops-schema.md](references/ops-schema.md) |
| 签字前 | [references/gates.md](references/gates.md) |
| 证据 | `~/.cursor/skills/idev/verify`（`debug` / `patrol`） |
| 回退 | `~/.cursor/skills/idev/deliver` |
| 接入/联调坑 | 当前产品 `.idev/handoff.yaml` 的接入 Skill |
| 集群现场 | 当前产品 `.idev/handoff.yaml` 的事故 Skill |
| 决策 | [0010](references/0010-ops-conductor.md) |
| 试运行台账 | [入口 state/ledger.yaml](../state/ledger.yaml) |
| 唤起 | `~/.cursor/skills/idev/references/invoke.md` |
| 本轮决策观测 | `~/.cursor/skills/idev/references/trace.md`（入口统一写） |

`resolved` / `defect_origin` / `reopen_baseline`：人手改 YAML，或按 [chat-confirm-signoff.md](../references/chat-confirm-signoff.md)（回退须带 `origin=`，解封须带「解除密封」/`reopen`）。

## Hard rules

1. **先分类再动手。** 写 `<票目录>/ops.yaml` 的 `kind`。`unknown` 不准给结论，也不准改代码。
2. **猜想须复现。** 对齐 `verify-with-cases`。未在用户同一现象上红过一次 → 不写根因。
3. **先认环境/产物。** 要齐：现象 + 哪套环境 + 哪份产物 + 可观察物。对不上就停。
4. **红绿只走 verify。** `kind=feature` → `mode=debug`；`kind=patrol` → `mode=patrol`（无包拒跑）。不要第二套断言引擎。
5. **不准抄平行 Skill。** `onboard` / `runtime` 交当前产品 `.idev/handoff.yaml` 里的 Skill。本模块只写 `handoff`，不叠第二套客户端。
6. **不准自动做生产写操作。** 不重启、不 failover、不 kubectl patch、不建告警屏蔽。预案等人判定。
7. **不准用排障改密封基线。** 像需求写错 → `baseline-conflict`，停。人选基线内修或 `reopen_baseline`。
8. **未拷问确认 `defect_origin` 不准回退。** origin 只许 `req` / `arch` / `code`。
9. **无本轮确认用语不得写 `defect_origin` / `reopen_baseline`；`resolved` 只在 P1/P2 账本收敛时可写 `auto:`，否则同样要确认用语。** 回退确认句须带 `origin=req|arch|code`。`by:` 必须是人名。细则 [chat-confirm-signoff.md](../references/chat-confirm-signoff.md)。
10. **请人签字前跑**  
    `bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> ops`  
    （内含 `outbound-skills-check.sh --repo`。当前产品 `.idev/marker.yaml` 为 `marker: idev` 且有 `handoff.yaml` 时，缺其中的 required Skill 即 FAIL。没有标识或不写名单，就不要求任何产品的 Skill。）  
    FAIL 不准请签。
11. **由本模块调用的 verify** 只写 `conductor-eval`，不为导体进化另停一次。
12. **试运行改本模块**：提案 + 拷问后只改真源 `~/.cursor/skills/idev/ops/`。不要写回仓库。

## 阶段怎么走

1. **认现场** — 人给 feature（或点头用分支名）+ 现象。缺环境/产物/可观察物就问，不要猜。
2. **分类** — 按 [classify.md](references/classify.md) 写 `ops.yaml`（[ops.example.yaml](references/ops.example.yaml)）。`kind` 不是 `feature` / `patrol` 则 `handoff` 后**停**，打开对应 Skill。
3. **取证** — `kind=feature`：起草 verify `debug` plan（goal 抄基线）→ 人确认 → run。原现象至少红一次。  
   `kind=patrol`：只重放 `doc_home.py --feature <feature> --key patrol` 输出的巡检包。
4. **根因** — 读代码之前先 `bash ~/.cursor/skills/idev/scripts/codegraph-sync.sh --repo <仓根> rootcause`。能红/绿切换才写进 report。对照密封基线 item。超出基线 → `baseline-conflict`。台账里有两条以上 `open` 假设时，先跑 `fanout.py assess --activity rootcause`。`FANOUT` 时每个 `idev-ops` 只查一个 id，只写 `verify/shards/rootcause-<id>.yaml`。另一片的结论不是证据。导体 `merge` 才改 `hypotheses.yaml`。只有一条 `open` 时不拆。
5. **回退** — 人写下 `defect_origin` 后，把 `deliver.yaml.stage` 回到 origin，作废其后 accepted / aligned，按 deliver 再向后走。
6. **关闭** — `check-feature.sh <feature> ops`。P0：人写 `resolved: true` + `by:`。P1/P2：`hypothesis.py check` 绿、无 `open`、有 `proven` 时写 `resolved: true` + `auto: hypotheses.yaml`，不停；否则停问人。人没提提升 / 巡检包 / promote 则不问是否把本次 debug case 晋升巡检包。

`deliver.yaml.stage`：仅当当前已是 `done` 时才改成 `ops`；交付中途的现象就地 `debug`，不要跳阶段。关闭且无回退 → 回到 `done`。

## 不要做

- 未确认环境/产物就改代码或让用户刷新验收
- 把接入登录/PIN/CORS 当 feature 缺陷去改业务
- 把集群 ISR / raft / 磁盘当控制台 bug
- 未复现就回退 deliver
- Agent 代填 `resolved` / `by`
- 结构检查 FAIL 仍请人签字
