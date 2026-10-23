---
module: deliver
parent: idev
---

# Deliver 模块（评审密封 → 提测）

由 `idev` 按内容调起。本目录不是独立 Skill。  
阶段：`req-review` → `req` → `arch` → `code` → `test` → `done` ⇄ `ops`。  
先拷问密封**原始需求基线**；后面只许对齐，不许改写。红绿只调用 verify 模块。  
投产后的现象走 ops 模块（先分类，再 debug 或 handoff）。  
每阶段按 [experts.md](references/experts.md) 拒过，不是扮演专家说话。  
停哪里、怎么签、何时 `AUTO`：只认 [chat-confirm-signoff.md](../references/chat-confirm-signoff.md)。

## 本阶段 5 步（先做这些）

1. `session-context.py` → 只开 `OPEN` 行；S1 必开 grilling + [docs/SKILL.md](../docs/SKILL.md)。
2. 读本阶段票文件（`baseline` / `req` / `arch` / `review`…），边界不清先 grilling，勿自拷问。
3. 改产物；请签前 `check-feature.sh <feature> <stage>`（FAIL 看 HINT）。
4. 有确认用语才代写当前停问点；`aligned`/`done` 必须人名 `by`。
5. `trace.sh append`；对话一行运行路径。

| Need | Doc |
|------|-----|
| 怎么用 | [references/how-to.md](references/how-to.md) |
| 契约 | [references/deliver-schema.md](references/deliver-schema.md) |
| 专家拒过 | [references/experts.md](references/experts.md) |
| 证据 | `~/.cursor/skills/idev/verify` |
| 投产后排障 | `~/.cursor/skills/idev/ops` |
| 拷问 | `~/.cursor/skills/grilling/SKILL.md`（缺则 `bash ~/.cursor/skills/idev/scripts/link-companion-skills.sh`） |
| 决策 | [0008](references/0008-deliver-conductor.md) · [0009](references/0009-deliver-baseline-seal.md) |
| 试运行台账 | [入口 state/ledger.yaml](../state/ledger.yaml) |
| 签字前检查 | [references/gates.md](references/gates.md) |
| 需求质量判据 | [references/req-quality.md](references/req-quality.md)（INVEST / SMART / 验收量化，拷问判据补强） |
| 唤起 / 停问档 | `~/.cursor/skills/idev/references/invoke.md` |
| 本轮决策观测 | `~/.cursor/skills/idev/references/trace.md`（入口统一写，本模块不另开账） |

## Hard rules

1. **不准跳阶段。** 无 `deliver.yaml` 从 `req-review` 建。
2. **grill 未闭合不准请签需求通过。** 每个档位都在 req 末一次签 `sealed` + `req.accepted`。基线就绪后可以起草拆解，不必先密封。未决问句只写 `<票目录>/grill.md`。`<票目录>` 只认 `python3 ~/.cursor/skills/idev/scripts/lib/doc_home.py --repo <仓根> --feature <feature> --key task`。`baseline.yaml` 仍有 `status: open` 或未清空 `objections` 时，关闭的 `grill.md` 不算数 → **自动唤起** `~/.cursor/skills/grilling/SKILL.md`，把本轮能问的一次问完；不准口头「差不多了」请签。
2a. **确认前 frontier 必须已空。** 请签需求通过之前，`grill.md` 必须在：`frontier` 与 `shared_understanding` 各自单独成行，正文有 `❓` 与 `➡️`。frontier 不是 `empty` → 不准请签、不准代写。`shared_understanding` 由这次确认写成 `true`，请签前可以仍是 `false`。不要先请一次「共享理解」再请一次密封。缺这份文件也不准把基线标成 `sealed: true`。
3. **密封后不准改 baseline 正文。** 下游只引用 `baseline_item_id`。要改原文：人写 `reopen_baseline`，回到 `req-review`。
4. **回退 origin 只能是 `req` / `arch` / `code`**（译法、方案、实现）。禁止用提测反馈直接改 goal。
5. **编码必须衔 verify**；case 必须同时挂 `slice_id` 与 `baseline_item_id`。
6. **过专家拒过清单才能请人签字。** 清单不过就停，不要用「资深意见」绕过。编码 / 路由 / PIN 先过 `../conventions/` 对应类。
7. **无本轮确认用语不得写 `sealed` / `accepted` / `aligned` / `reopen_baseline`。** 有确认用语则按 [chat-confirm-signoff.md](../references/chat-confirm-signoff.md) 只代写当前停问点。`继续` 不算。解封须带「解除密封」或 `reopen`。
8. **试运行改本模块**：提案 + 拷问后只改真源 `~/.cursor/skills/idev/deliver/`。不要写回仓库。台账 [入口 state/ledger.yaml](../state/ledger.yaml)。
9. **尺是密封基线。** specs 只复述；和 baseline 打架就改 specs。verify 的 goal/non_goal 必须复制基线原文。
10. **停问按 `risk_tier`（默认 P1）与信号。** 见 [chat-confirm-signoff.md](../references/chat-confirm-signoff.md)。被本模块调用的 verify 不再为导体进化另停一次。
11. **请人签字前必须跑结构检查。**  
    `bash ~/.cursor/skills/idev/scripts/check-feature.sh <feature> <stage> [--product <点名的产品>]`  
    再打印 [gates.md](references/gates.md)。脚本 FAIL 不准请签。  
    `req` 及之后：slice.must 原文锁 + 上一阶段 `semantic_gate`；`test` 维表六族须覆盖；`ops` 内含外送 Skill 检查。
12. **reopen：** `baseline.revision + 1`，旧 item id 不装新含义；下游 accepted 作废。
13. **`sealed` / `accepted` / `aligned` 必须带人名 `by:`。** 解析见 [chat-confirm-signoff.md](../references/chat-confirm-signoff.md)。禁止 `agent` / `ai`。
14. **编码只改 `arch.yaml` 里 `include: true` 的路径。** 其它脏文件写入 `review.md` 的 UNRELATED，不准顺手改。Review 落票目录里的 `review.md`（同一条 `doc_home.py --key task`）。
15. **每阶段结束写票目录里的 `deliver-eval.md`**（件数，照 [deliver-eval.example.md](references/deliver-eval.example.md)）。路径仍由 `doc_home.py --key task` 决定。
16. **人写 `aligned` 之后进入 `done`。** 不自动 `promote`；人没提提升 / 巡检包 / promote 则不问。
17. **无当前停问点不请签。** 自测完成后只停实现审核；通过后进入提测，不另问要不要提测。用例计划不单独请签。

## 阶段怎么走

进入 `req-review`、`req`、`arch`、`code`、`test` 时，先跑：

`python3 ~/.cursor/skills/idev/scripts/session-context.py --repo <仓根> --feature <feature> --scenario S2 --stage <stage> [--product <点名的产品>]`

打开每一行 `OPEN`。这些路径写入 trace 的 `extensions`（没有页就写 `extensions: []`）和 `opened`。没有 `OPEN` 就只走内核。点了产品名就传 `--product`，否则用仓 marker 的 id。声明了但文件不在时，这条命令和 `check-feature` 都失败。

### req-review（需求评审）

1. 对照 CONTEXT / ADR / 现有契约起草规格与 `baseline.yaml`（[baseline.example.yaml](references/baseline.example.yaml)）。落盘前打开 [docs/SKILL.md](../docs/SKILL.md)。未决问题写该票的 `grill.md`（`convention: grilling`）。
2. 正确性、合理性、边界、细节、非目标：全部写成 `grill.md` 里的问句。文件放哪认 [docs/SKILL.md](../docs/SKILL.md)。`review_questions` 保持空列表。冲突不得默许。
3. **自动唤起 grilling（硬）：** 本阶段一进入「定边界 / 清异议」就打开并执行 `~/.cursor/skills/grilling/SKILL.md`。把本轮 frontier 上的问题一次问完，每题带推荐答案；人的回答打开新问题就再来一轮。回答不是确认用语。推迟项写进 `non_goal`。`objections` 保持空。缺 grilling 先跑 `scripts/link-companion-skills.sh`。**禁止**用「自己拷问」或跳过 grilling 直接请签。
4. frontier 空之后不停在本阶段。直接起草拆解。需求通过的那一次确认在 `req` 末。

### req（拆解）

1. 只把密封 item 译成 slices，不增不减。
2. 译不清进 `open_questions`（只问理解）。想加义务 → `baseline-conflict`，停。
3. `check-feature.sh <feature> req`。每个档位一次签 `sealed` + `req.accepted`（同一个 `by`），并写入 `shared_understanding: true`。签完才能 `arch`。译法上还有问题就再开一轮提问，不要拆成第二次签字。

### arch

需求签收后、请人评方案之前，先交方案，供人整体 Review。不要只留 `arch.yaml` 里的一行 `approach`。用例文件这阶段不写。

1. **方案叙述** `<票目录>/design.md`（照 [design.example.md](references/design.example.md)）。六节都要有正文：目标、方案、契约、影响面、回退、用例。目标节照抄基线 `goal`。每条基线 item、每条 `case_intent` 都在文中点名。细到人能按节评审，不写实现代码。
2. **机读方案** `arch.yaml`。`approach` / `non_approach` 都要有。`case_intents` 挂 `baseline_item_id`。方案若「更好」但超出基线 → 拒过，不改基线。
3. **先给整包，再等 Review。** 不要在交出方案之前先开一轮必答拷问，也不要为了过门造一个问句。人 Review 时若有未决分叉，再打开 grilling，问句写在 `grill.md` 的 `## arch` 轮，`arch_frontier` 回到 `empty` 才能请签。没有分叉就不要写这一轮。需求轮的 `frontier` 保持 `empty`。
4. **架构范式自查**：按 [canon.md](../conventions/canon.md) §1 协议扫 §2 信号与 §4 念头，§5 必答 A1–A8，§7 模板记账；答不出的项标 `UNPROVEN` 并写进 `design.md` 的方案节。真有分叉就在 arch 轮里问完。
4a. **领域建模透镜（涉及新概念时）**：本轮引入新领域概念 / 跨模块术语时，先过 [conventions/domain-modeling.md](../conventions/domain-modeling.md) 建通用语言；术语不一致先对齐再出方案，术语表随票走。无新概念可跳过。
5. `check-feature.sh <feature> arch`。方案对齐、没有未决分叉后，人 `accepted` + `by` 才能 `code`。这次确认不包含用例计划。

### code

1. 只改 `include: true` 的文件。写 `review.md`（[review.example.md](references/review.example.md)）。多做删掉；少做补；像基线写错 → `baseline-conflict`，**停**。
2. **写前匹配、写中纠正。** 打开 [coding.md](../conventions/coding.md) §0；扫表时再开 [coding-tables.md](../conventions/coding-tables.md)。用本轮变化扫 §1，命中第一行就运用，禁止行当场拒绝。每新增函数扫 §2，命中当轮改掉。
3. **Review 再扫一遍。** `review.md` 必须写 §1 命中 / 零命中和 §2 已扫；命中只记账未改 = 拒过；若命中 canon 的 `T#`（加层 / 拆分 / 缓存 / 重写类念头），一并写入 `review.md`。按 [coding-tables.md](../conventions/coding-tables.md) §3.8 跑 `bash ~/.cursor/skills/idev/scripts/coding-scan.sh <repo>`，做五轴 + 栈指南；blocking 译成 `P#`/`C#` 当轮改。然后清废弃、对齐注释/文档、跑扫描（Java：Problems / `qodana.starter`；前端：`lint-fix`）。
4. **架构通过后连续做完三件事，中间不再请签：** 按 `case_intents` 起草 `verify/plan.yaml`（每条意图一条 case，`goal` 复制基线），编码，跑 selftest/logic。要加一条 case，先补 `case_intent` 和 `design.md` 的用例节。计划无 `SIGNAL` 记 `AUTO`（每个档位）；有 `SIGNAL` 先记下，不要为此停下来。`check-feature.sh <feature> code` 通过且自测有跑证之后，停一次实现审核。确认写入 `semantic_gate.code` 并把 `stage` 改为 `test`。不另问要不要提测。
5. 实现/译法问题回退 `code`/`req`/`arch`，重跑向后。

### test

1. 用例证明基线 item。疑问拷问理解，答案不得写成新 must。
2. `mode=test`。`check-feature.sh <feature> test`。跑完后一次确认测试结果：`aligned` + `by`，才 `done`。人没提提升 / 巡检包 / promote 则不问巡检包。

### done

基线仍密封。新一轮要改原文必须 reopen 评审。  
投产后的现象、巡检、回退：交回入口走 ops 模块，不要在本阶段口头改 goal。

### ops（投产后；由 ops 模块执行）

当前已是 `done` 才能把 `deliver.yaml.stage` 写成 `ops`。交付中途的现象就地 verify `debug`，不准跳到 `ops`。  
回退 origin 仍是 `req` / `arch` / `code`。关闭且无回退 → 回到 `done`。

## 不要做

- 拆解或编码时改 goal / items
- 用测试用例发明需求
- 跳过 req-review
- 扮演专家空谈而不走拒过清单
- 口头改需求继续向后做
- 结构检查 FAIL 仍请人签字
- 改 `include: false` / UNRELATED 文件
- Agent 代填 `by`
- 把投产现象当成新需求改 baseline
