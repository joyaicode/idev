# 各阶段专家标准（可检查，不是扮演）

每个阶段按该行的**拒过清单**处理。禁止用「作为资深专家我认为」代替清单。过清单后才能请人签字。

| stage | 身份 | 必须做到 | 拒过（有一条就不能请人 accepted） |
|-------|------|----------|-----------------------------------|
| `req-review` | 资深产品 / 领域评审 | 拷问到目标、非目标、边界、细节无 `open` 异议；与 CONTEXT / ADR / 现有契约不打架；goal 有可量化 SMART 指标、验收可证伪（[req-quality.md](req-quality.md)） | 未拷问就请人密封；用猜测补细节；和已锁契约冲突却不写进问题；无一条可证伪 item；`objections` 未清空；验收含主观词（合理/友好/流畅）不可测；用解决方案冒充需求 |
| `req` | 资深分析 | 把**已密封基线**译成 slices，不增不减 must；`slice.must` 原文锁 + [semantic-gate.md](semantic-gate.md)；每条 slice 过 INVEST（[req-quality.md](req-quality.md)） | slice 的 must 对不上 `baseline.items` 原文；新增基线没有的义务；丢掉基线一条 item；`baseline_revision` 对不上；缺上一阶段 `semantic_gate`；故事 > 8 点未拆 |
| `arch` | 资深架构 | 方案只实现基线；影响面诚实；用例意图覆盖基线 item | 方案改写目标/非目标；为「更好」扩大范围；case_intent 不挂 `baseline_item_id`；与现有 SPI / 路由契约重复发明 |
| `code` | 资深开发 + Review | 按方案实现基线；写前按 [coding.md](../../conventions/coding.md) §0 匹配，扫表开 [coding-tables.md](../../conventions/coding-tables.md)；写中按 §2 纠正；结构调整过 §3；§3.8 增强扫描；`review.md` 用 `P#`/`C#`/`R#`；`check-feature code` PASS；少做/多做对照基线 | 不打开 coding.md 就写；该匹配未运用或不该用的模式上了；气味命中只记账未改；混戴重构/加功能帽或无护栏重构；另起表号；跳过五轴/栈指南；`review` 仍是 `P?`/`C?` 或缺五轴；顺手重构基线外行为；用代码「修正」需求；不跑 verify；预置模式 / 两行包装 / 空值省略 / 兜底猜值；留下废弃符号或过期注释；未跑扫描或留下黄条；`git add generatedverify` |
| `test` | 资深测试 | 用例证明基线 item；疑问拷问的是**理解**，不是改基线 | 用新用例发明需求；把基线外的期望写成 FAIL；对基线 item 无 case；未确认环境/产物却写 PASS |
| `ops` | 资深排障 | 先分类；现场四件齐；特征缺陷须复现后才能回退 | 未确认环境/产物就写结论；猜根因未复现；把接入/集群当 feature 改代码；自动做生产写；用排障改 baseline |

`done` 没有专家扮演：只认密封基线 + 自测门 + 提测门 + 人授权的 `aligned`。  
`ops` 的执行本在 ops 模块，本表只给拒过清单。
