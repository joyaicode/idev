# 各阶段专家标准（可检查，不是扮演）

每个阶段按该行的**拒过清单**处理。禁止用「作为资深专家我认为」代替清单。过清单后才能请人签字。

| stage | 身份 | 必须做到 | 拒过（有一条就不能请人 accepted） |
|-------|------|----------|-----------------------------------|
| `req-review` | 资深产品 / 领域评审 | 拷问到目标、非目标、边界、细节无 `open` 异议；**密封前把需求落到既有代码上**（`grounding`：落点 / 影响面 / 与存量的冲突 / 边界 / 演进方向，见 `scripts/req-ground.py`）；与 CONTEXT / ADR / 现有契约不打架；goal 有可量化 SMART 指标、验收可证伪（[req-quality.md](req-quality.md)） | 未拷问就请人密封；用猜测补细节；和已锁契约冲突却不写进问题；无一条可证伪 item；`objections` 未清空；验收含主观词（合理/友好/流畅）不可测；用解决方案冒充需求 |
| `req` | 资深分析 | 把**已密封基线**译成 slices，不增不减 must；`slice.must` 原文锁 + [semantic-gate.md](semantic-gate.md)；每条 slice 过 INVEST（[req-quality.md](req-quality.md)） | slice 的 must 对不上 `baseline.items` 原文；新增基线没有的义务；丢掉基线一条 item；`baseline_revision` 对不上；缺上一阶段 `semantic_gate`；故事 > 8 点未拆 |
| `arch` | 资深架构 | 需求签收后交出可评审的 `design.md`（六节）+ `arch.yaml`；用例骨架与 `case_intents` 同一轮对齐；**grilling 的 arch 轮**问完做法、契约、回退、用例对照；影响面诚实（`codegraph_impact --depth 1`）；**写明回退** | 只有一行 approach、没有 `design.md`；方案改写目标/非目标；为「更好」扩大范围；case_intent 不挂 `baseline_item_id`；用例与方案不是同一批；arch 轮未闭合就请签；与现有 SPI / 路由契约重复发明；要改多处却没有 `impact_candidates`；没有回退路径 |
| `arch`（设计透镜） | 资深设计 | 涉及新领域概念先过 [domain-modeling.md](../../conventions/domain-modeling.md) 建通用语言；对外契约（API / 事件 / 存储结构）先定再实现；命名在票内一致 | 术语在票里前后不一致；契约边界没定就开始写实现；用实现细节命名领域概念；同一概念三处不同叫法 |
| `code` | 资深开发 + Review | 按方案实现基线；写前按 [coding.md](../../conventions/coding.md) §0 匹配，扫表开 [coding-tables.md](../../conventions/coding-tables.md)；写中按 §2 纠正；结构调整过 §3；§3.8 增强扫描；`review.md` 用 `P#`/`C#`/`R#`；`check-feature code` PASS；少做/多做对照基线 | 不打开 coding.md 就写；该匹配未运用或不该用的模式上了；气味命中只记账未改；混戴重构/加功能帽或无护栏重构；另起表号；跳过五轴/栈指南；`review` 仍是 `P?`/`C?` 或缺五轴；顺手重构基线外行为；用代码「修正」需求；不跑 verify；预置模式 / 两行包装 / 空值省略 / 兜底猜值；留下废弃符号或过期注释；未跑扫描或留下黄条；`git add generatedverify` |
| `test` | 资深测试 | 用例证明基线 item；疑问拷问的是**理解**，不是改基线 | 用新用例发明需求；把基线外的期望写成 FAIL；对基线 item 无 case；未确认环境/产物却写 PASS；断言写成「不报错 / 返回 200 / 进程还在」而不是用户那条现象 |
| `test` → `done` | 资深交付 | 提测门齐：维表六族有 case 或显式 `UNPROVEN`；残留 `UNPROVEN` 人明确接受；回退路径可执行 | 用「大部分通过」代替计数；把 `UNPROVEN` 悄悄当通过；人没接受残留 `UNPROVEN` 就请 `aligned`；没有回退就上线 |
| `ops` | 资深排障 | 先分类；现场四件齐；特征缺陷须复现后才能回退 | 未确认环境/产物就写结论；猜根因未复现；把接入/集群当 feature 改代码；自动做生产写；用排障改 baseline |

`done` 没有专家扮演：只认密封基线 + 自测门 + 提测门 + 人授权的 `aligned`。  
`ops` 的执行本在 ops 模块，本表只给拒过清单。

## 哪些已经有机器在查

本表的拒过清单分两半。**可机检的那一半**由 `scripts/stage-gate.py` 执行：

```bash
python3 scripts/stage-gate.py --feature <f> --stage <stage>
python3 scripts/stage-gate.py --feature <f> --all      # 输入齐了的阶段全跑
python3 scripts/stage-gate.py --list                   # 各档查什么
```

| stage | 已机检 |
|---|---|
| `req-review` | 验收含主观词 · 验收无可量化指标 · 无验收 · 解决方案冒充需求 · `objections` 未清空 · goal 含主观词 · 界面需求无 `ui` 块 · 已密封却无 `grounding` |
| `req-review` 的 `grounding` | `touches` 空或没到 `file:symbol` · 冲突没挂 grill 问句 · 挂的问句在 `grill.md` 里不存在 · 无 `boundary` · 无 `direction` · 与竞品有差异却没写 why 或没拷问（`req-ground.py`） |
| `req-review` 的 `ui` 块 | 缺 screen/intent · 必填字段无 `on_invalid` · action 无 `on_success`/`on_failure` · 缺 `states.loading`/`error` · 写了实现细节(`el-xxx`/class/css) · 含主观词（`ui-spec.py`） |
| `req` | 故事 > 8 点 · slice 不挂 `baseline_item_id` · 丢掉基线 item |
| `arch` | `case_intent` 不挂 item · 要改多处却无 `impact_candidates` · 无回退路径 |
| `code` | `review.md` 仍是 `P?`/`C?` · 命中标成「待改 / 下轮」 |
| `test` | `PASS` 无证据路径 · case 不挂 item · 弱断言（「不报错」这类） |
| `ops` | 现场四件不齐 · `kind=unknown` 却已写根因 · 根因未复现 · 提到生产写操作 |

**不可机检的那一半**仍要人按本表过，并在 grill 里拷问：拆解是否忠实、架构是否合理、
用例是否有意义、术语是否一致、回退是否真的能执行。

**机检没发现 ≠ 这一关过了。** `stage-gate` 的 PASS 只说明「没撞上已知的硬错」，
不说明「做对了」。签字之前仍要过本表 + `check-feature.sh` + `gates.md`。
