# idev 变更记录（给人看，Agent 无需读取）

- 2026-11-07：恢复《Effective Java 中文版（第 2 版）》三条已签字落源（T3 异常翻译、T8 失败原子性、T14 保护性拷贝）。`8152e13` 曾把它们误回退为「建议落点」，但 `state/proposals/20261107-effective-java-gaps.md` 仍为 landed，且未同步提案或变更记录；本条恢复真源、报告「已落地」标注与提案状态的一致性，不新增编号或门禁。

- 2026-11-07：《代码整洁之道》第 14–16 章 + 附录 A–B、《修改代码的艺术》第 3/5/7/9–12/16–22 章、《重构》第 5–14 章 72 个手法逐条精读收口，本轮落 2 处真源缺口：`conventions/canon.md` T10 增补死锁避免（多把锁 / 多资源按固定、一致的次序获取，消除循环等待）；`conventions/coding-tables.md` C21 增补命令/查询分离（CQS）双向覆盖（查询函数夹带可观察副作用 → 拆查询 + 修改，缓存等不可观察副作用豁免）。其余手法经对照由既有 T/C/P/R 承载或属机械步骤 / 设计取向差异不落，理由见 `state/proposals/20261108-conventions-cleancode-ch14-16-appendix-gaps.md`、`20261108-conventions-legacycode-ch3-22-gaps.md`、`20261108-conventions-refactoring-ch5-14-gaps.md`。不新增编号、门禁或第二套测试框架。人要求：quote「好的，按推荐进行」。

- 2026-11-07：《领域驱动设计》第 15–17 章、结束语与附录精读收口，全书 17 章读完。第 15 章精炼、第 16 章大比例结构、第 17 章综合运用共 30 条对照后只落 1 条：`conventions/domain-modeling.md` 新增「核心域与通用子领域（可检查）」检查项，要求 arch 方案识别核心域（CORE DOMAIN）与通用子领域（GENERIC SUBDOMAIN），精力优先投入核心域，不为通用子领域开发「万能」模型。结束语补 4 条项目复盘/DDD 标志/未来展望，附录补 3 条模式语言、模式模板与查阅层记录；这些与既有 A1–A4、P1/P2 和提案裁定同向，不重复落。大比例结构（EVOLVING ORDER / SYSTEM METAPHOR / RESPONSIBILITY LAYER / KNOWLEDGE LEVEL / PLUGGABLE COMPONENT FRAMEWORK）、首先评估六步与架构团队人员配置经对照不重复落，理由见 `state/proposals/20261107-ddd-ch15-17-gaps.md`。不新增编号、门禁或第二套测试框架。人要求：quote「所有任务在未完成前，一率按"好的，按推荐进行"，遇到确认或批准，一率批准，直到完成所有任务」。

- 2026-11-07：按需增量知识检索 CLI 落地（P0 基线 + P1 MVP）。`scripts/knowledge.py` 四子命令（sync/search/read/doctor）用 SQLite FTS5 + 自建 CJK bigram 切词做全文检索，索引放 `state/knowledge-index/`（gitignore，可删重建）；白名单 P0 只含 joypaas（docs/design + .idev/pack + .cursor + docs/adr），验收问题集 15 条在 `state/knowledge-questions.yaml`。search 前自动增量同步；查询侧去除「如何」填充词，并对「处理器→handler」「弹性搜索→elasticsearch」做最小中英同义扩展。过期即失效（内容 hash 逐文件比对）、read 返回前再验 hash、越界文件（密钥/.env/依赖目录/构建产物）一律排除。单元测试 14 条全过（自动同步、删除、失效、越界、read-hash 复核、doctor 孤儿），真实 joypaas 问题集 Top-5 来源命中 15/15，doctor 正常；不引入向量、MCP、常驻服务或独立知识平台。提案见 `state/proposals/20261108-knowledge-search-cli.md`。人要求：quote「好的，按推荐进行」，并沿用工作期间自动同意。

- 2026-11-07：七本工程 / 架构 / 编码规范书籍精读收口，本轮再补 4 处真源缺口。`conventions/canon.md` T8 增补宽收严发，T10 增补消息消费拓扑与跨系统事务离线并发，T11 增补输出克制，A4 同步点名消费拓扑与离线并发；`agents/idev-coder.md`、`agents/idev-deliver.md` 分别补 F4 / F7 的阶段触发。Web性能报告及其缺口已随 `12ab1c4` 入库；本提交补齐其余六份报告、修正第 15–21 本索引，并在 Effective Java 与大型网站报告中标注已由 `12ab1c4` 提前落地的缺口。其余主题经对照由既有 T/A/F 与 P/C/R 承载，理由见各报告。人要求：quote「继续精读未读的书籍，并炼化沉淀到idev中」。

- 2026-11-07：阶段专家标准升级为唯一权威落点。`experts.md` 明确产物质量、效率路径、拒过清单三段读法，并为每个阶段补不降质的最快路径；五名执行者与 deliver 入口改为按这三件套执行。`stage-gate --list` 修复为输出各阶段真实规则 ID，并用 agent-smoke 锁住。不新增专家角色、编号、门禁或第二份专家页。人要求：quote「沉淀到idev中，做为最权威的专家指导各阶段的工作，提升阶段产物质量和效率。」

- 2026-11-07：《程序员的职业素养》第 14 本精读收口。全书第 1–14 章、附录与尾部元数据对照后只落 1 条阶段经验：`deliver/references/req-quality.md` §5 明确预估不是承诺，只承诺可掌控的具体行动；不确定时用乐观 / 标称 / 悲观或区间表达，不说“试试看”；预估与 deadline 冲突或预计延迟时当轮报告风险、原因、剩余范围和选项。TDD、完成证据、危机纪律、工具链与团队组织方法经对照不重复落，理由见 `scripts/docs/notes/程序员的职业素养-精读缺口.md`。不新增编号、门禁或第二套测试框架。人要求：quote「继续精读未读的书籍，并炼化沉淀到idev中」。

- 2026-11-07：《程序员修炼之道：从小工到专家》第 13 本精读收口。全书 70 条 tip 对照后只落 3 条阶段经验：`deliver/references/req-quality.md` 新增估算参照物、不确定性单位与按真实增量复估；`deliver/SKILL.md` 架构阶段要求多步骤流程先分析可并行 / 必须串行的工作流，接口不承载隐式调用顺序；`verify/SKILL.md` 要求新纳入的复现型 / 回归型 case 首次 run 先证明断言能红一次，再恢复跑绿。函数级 DBC、配置 / 元数据优先、独立破坏员与黑板模式经对照不落，理由见 `scripts/docs/notes/程序员修炼之道-精读缺口.md`。不新增编号、门禁或第二套测试框架。人要求：quote「继续精读未读的书籍，并炼化沉淀到idev中」。

- 2026-11-07：删除预算纳入 `skills/`。`deletion-budget.py` 的统计范围补上同伴技能副本，并用临时 git 仓的范围锁测试锁住两件事：`skills/` 的增删会计入，`state/` 仍不计入。`references/self-evolution.md` 同步说明 2026-11-07 起的最大零删除增量来源已进入度量；不改 2.0 阈值、不新增门禁、不把 WARN 变成 FAIL。提案见 `state/proposals/20261107-deletion-budget-skills-scope.md`。人要求：quote「好的，按推荐进行」。

- 2026-11-07：效率根因提案收口，删除 `references/deletion-budget.md`。删除预算、范围、`skills/` 盲点与精读沉淀豁免的唯一真源收敛到 [self-evolution.md](self-evolution.md)「删除预算 / 自建期退出条件」节，消除同一规则双处记账；这不是新增规则，而是执行该页已写明的 delete pass。提案 `state/proposals/20261104-efficiency-root-cause.md` 从「三项落地、一项受阻」改为全项 landed。验证见提案「已收口」节。人要求：quote「好的，按推荐进行」，并沿用工作期间自动同意授权。

- 2026-11-07：修正精读可达审计的阶段范围口径。`deep-read-audit.py` 现在把阶段页中的 `A1–A8` / `P1–P19` / `C1–C31` / `R1–R7` 展开为全表 `staged`，不再只认两端字面量；「只有记账」逻辑保留为无 trigger / staged / enforced 时的独立测试。三个真实剩余失败模式进入自然阶段：`idev-deliver` 的 F2 要求引入或替换依赖前读真实契约 / 源码并用学习测试钉住第三方行为，`idev-verifier` 的 F5 要求断言取自契约或用户现象，`idev-coder` 的 F6 要求大 diff / 无护栏 / 无回退先缩小步子。全量审计 10 份缺口报告均满额可达、全局只有记账为空；这表示至少 trigger / staged / enforced 一层可达，不表示全部可机检。验证见 `state/proposals/20261107-deep-read-stage-ranges.md`。人要求：quote「继续炼化未读完的书籍」，并沿用工作期间自动同意与书籍精读持续授权。

- 2026-11-07：全量精读可达审计与测试阶段经验落点。`deep-read-audit.py --all-books` 补上使用说明中已有但未实现的入口，只收 `*-精读缺口.md`，逐份报告输出可达数与「只有记账」编号，并汇总全局未落真源 / 只有记账集合；DDD 逐章笔记的局部编号与《程序设计实践》的提案直落成果不进这批，避免把同形编号当真源编号。`agents/idev-verifier.md` 在维度骨架后新增测试气味扫描：C26 单测方向 / 最小 setup / Input-Expected-Actual，C28 套件金字塔与快速重跑，C29 随机失败 / 跳过 / 长期红灯当轮处理，C30 stub 优先、mock 只验对外副作用。C27 是代码结构气味，不挂进 verifier；这四条也不做插件，避免断言语义、套件配比和正当 mock 语境产生高误报。效果：TDD 报告可达 18→22/45，微服务设计 16→20/22，修改代码的艺术 5→8/14。验证见 `state/proposals/20261107-deep-read-all-books.md`。人要求：quote「好的，按推荐进行」，并沿用书籍精读持续授权。

- 2026-11-07：已过闸经验进入每个阶段入口。新增 `scripts/lib/prior_art.py` 统一 scopes、票内 / 内核台账路径、格式化与可选降级：`session-context.py` 在 `STAGE` 后输出 `PRIOR` 与 `PRIOR_NOTE`，`workflow.py` 的委派包复用同一读取器并保持 `既往:` 行为不变。只取 `lessons.py` 的 `authoritative` 与 `sediment.py` 的 `kept`，candidate / retired 不进执行上下文；不新增台账、语义检索、评分或阶段门禁。落地中发现并修复两个边界：内核台账实际在 `state/`，以及台账读取器依赖 PyYAML 时会把无 PyYAML 的阶段入口拖垮，现改为依赖缺失时安静跳过。文档更新 `references/agent-brief.md`、`references/self-evolution.md` 与 `references/agents.md`。验证：`test_session_context.py` 8 例、`test_prior_art.py` 16 例、`test_workflow_enhance.py` 16 例、`test_problems_scan.sh` 13 例全部通过；`selfcheck.sh` 在 `/private/tmp` 缓存下 PASS（191s）。提案见 `state/proposals/20261107-stage-prior-art.md`。人要求：quote「经验沉淀到idev中，增强各阶段的处理和产出质量和效率」。

- 2026-11-07：执行 trace `20261105-004` 的 C9 推荐，集中清理 Python `if` 嵌套超过两层的存量债务。重构前 16 个目标文件正则命中 91 处；AST 审计确认 84 处真实 `if` 语句，7 处是三元表达式 / comprehension 续行造成的误报。`canon_smells.nesting_hits_indent` 接受 AST 语句行，`python_inspect` 解析 `ast.If` 后传入，只把真实控制流嵌套计入 C9。`check-feature`、`workflow`、`artifact-match` 等用阶段函数、守护子句和判定 helper 拆平，当前 168 个 Python 文件 C9=0，剩余 40 处为既有 C7/C12，未扩大本轮范围。验证含 18 个目标文件 `py_compile`、29 个 smell 测试、全仓扫描、597 项 unittest 与 selfcheck；默认沙盒缓存下有 2 项环境失败（本地 socket bind 被拒、Go build cache 不可写），缓存改到 `/private/tmp` 后仅剩 socket bind，该测试在沙盒外重跑 OK，selfcheck 最终也只剩同一 socket 限制。另 `check-feature-tiers` 的 2 个 verify-plan 失败已由重构前快照复现，属既有 sealed projection 缺失。

- 2026-11-07：Kent Beck《测试驱动开发》（中文版）全书第 1–32 章与附录 A–B 精读收口，第十二本。PDF 文本层不可用，报告基于 `测试驱动开发-OCR.txt`（179 页 / 9885 行）完成。核心增量逐项对照后无需改真源：红绿重构与小步护栏归 T6 + R1–R4；单测方向 / setup / 断言消息归 C26；套件配比、脆弱测试、过度 mock 归 C28–C30；第三方行为钉子已在 F2，自证式测试归 F5；提交前证据归 verify plan/run 与 `workflows/test-pack.yaml`。严格 test-first、测试顺序独立性、期望异常模板、提交前全量测试、学习测试五个候选均裁定不新增或已承载，防止重复立条。`deep-read-audit` 对报告 45 个编号给出 18 个可达（含 T6 trigger、R1/R7 staged、C22 enforced），PASS。报告见 `scripts/docs/notes/测试驱动开发-精读缺口.md`。

- 2026-11-07：GoF《设计模式：可复用面向对象软件的基础》全书第 1–6 章与附录 A–C 精读收口，第十一本。相对既有《设计模式之禅》《HeadFirst 设计模式》无产品级真缺口：23 个模式已由 P1–P19 场景表收编；组合优于继承归 C27；聚合 / 相识与所有权生命周期归 C19；Template Method 的 hook / protected / final 细节裁定为语言实现层细节，不落。Lexi 案例、C++ 变体、模式关系目录与参考文献均不进真源，防止把模式名录抄成第二套编号。`deep-read-audit` 对报告 30 个编号给出 14 个可达（含 T1/T3/T4 trigger、P1/P2/P19 staged、C22 enforced），PASS。报告见 `scripts/docs/notes/设计模式：可复用面向对象软件的基础-精读缺口.md`。

- 2026-11-07：《代码大全》第一版中译全书第 1–33 章精读收口，第十本。这不是第二版，逐条对照时只取仍适用于当前 Go / Java / TS / Vue 工程的判据，不搬 Pascal / Basic 时代的语言细节。主体已由既有真源承载：信息隐藏 / 深模块归 T3/T4，防错性编程归 T8/C7/C13，命名归 T5/C12，作用域与全局数据归 T14，控制结构归 C1/C9 与圈复杂度 ≤10，测试 / 调试归 T6/C26/rootcause-guards，性能归 T9。唯一真缺口是 `switch` / `case` 的 default：未列值不能伪装成合法缺省。C2 原来只覆盖 `if (有值) 带上; else 省略/默认`，现增补「`case/default` 把未列值当合法缺省」气味，纠正为 `default` 只承载显式合法缺省，否则报未知值。改既有 C2 行最小 diff，不新增编号，不动 §3.5 与 canon §2/§4。`deep-read-audit` 对报告 33 个编号给出 22 个可达（含 C2 staged、C7/C9/C12 enforced），PASS。断言宏、防火墙多层消毒、最近改动启发式、错误集中 80/20、PDL / 布局、代码调整目录、项目管理和性格叙事均裁定不落，理由见 `scripts/docs/notes/代码大全-精读缺口.md` 第四节。

- 2026-11-06：把仓里唯一标着「port it next」的两条机检移植到 Go，然后堵掉让这次移植差点静默通过的那个洞。`parity_test.go` 的 deferred 清单里，`gate-held` 与 `deliver-gates` 两条都写明 **NO PREREQUISITE** —— 没有前置依赖，只是 Go 侧没跟上，且各有同构的已移植范本（`gate-held` 照 `scope-held`，`deliver-gates` 照 `scope-declared`）。① `gate-held`：审查者的 CHANGED 只许 `review.md` 与 `review/shards/*.md`，改了测试、用例门槛或产品代码就是**把自己要守的那道闸搬开了**，所以是 FAIL 不是 WARN；没有 CHANGED 行的回报仍过（字段比某些旧回报新，缺字段不等于写过东西）。适用条件用 `Registry.AgentFor("review.report")` 表达「谁执行审查那一步谁就是审查者」，不在 Go 里再硬编码一遍 agent 名（Python 侧是硬编码的，这边不必）。② `deliver-gates`：请签前两条 GATE 行（check-feature 与 stage-gate 各一行），三种失败按要紧程度排 —— 门没点名、结论读不出、**`STATUS=PASS` 却压着一条 FAIL**；第三种才是值得有的那条，签在一个拒绝之上不是格式笔误。只按 kind 判定，因为 `kinds.yaml` 已经把 `deliver.advance` 钉给 deliver agent，再查一遍 agent 只会多一个两处说法打架的机会。Report 加 `Gates []string`（存原始行，因为同一行要读出三样东西）。踩到一个真实的 **Go/Python 正则行为差异**：`不适用\b` 在 Go 永远匹配不上（Go 的 `\b` 只认 ASCII 词边界，Python 的认 Unicode），被 `TestNotApplicableIsAReadableVerdict` 逮住，改成把 `\b` 放进各自的 ASCII 分支（`PASS\b|FAIL\b|不适用`），`PASSED` 仍不会读成 PASS。③ **堵洞**：移植完跑 `go test` 是绿的 —— 而它本该报「listed as deferred but is implemented」。根因是 `goCheckNames()` 是手抄名册，而 parity 测试只问「Python 有而 Go 没有」，于是一个**实现了但没登记**的检查读起来就是「没移植」，继续待在 deferred 里，整套静默通过。手抄是有意的设计（注释写着「加了常量却没决定归属，不该静默通过」），但那个意图自己没有锁。新增 `TestEveryCheckConstantIsOnTheRoster`：从 `checks.go` 源码 grep 所有 `Check* = "..."` 常量与名册双向对账（Python 侧一直是这么对自己的）。16 条新行为用例 + 名册锁都验过红绿切换：名册里删掉 `CheckDeliverGates` → 新锁报出缺的那一条；把 `verdict[1] == "FAIL"` 改成 `"FAILX"` → `TestSigningOverAFailingGateIsCaught` 变红。`go test ./...` 全绿、`go vet` 干净、`gofmt` 对 delegsvc 干净（`mcpface.go` 与 `workspace.go` 的格式问题在 HEAD 上就有，无未提交改动，不是本轮引入）。人要求：quote「修复问题继续」。

- 2026-11-06：重录 golden 要说出理由。先更正上一轮的覆盖边界 —— 我说「九份判定为无需细读」，但其实**完全漏看了 `.joycode/` 与 `docs/fix|feat|plan`**；那不是判断，是漏。`.joycode/skills/` 下正躺着两个和 idev 同类的东西：`ai-software-engineering-lifecycle/SKILL.md`（663 行）与 `ai-development-deep-spec/SKILL.md`（927 行）+ 41 条反模式目录 —— 之前读的都是它的工程文档，不是它的导体。逐类对过：上下文（C-1..6）、需求（R-1..6）、设计（D-1..6）、实现（I-1..8）在 `conventions/` 与 `req-quality.md` 已全覆盖，T-7「忽略测试」idev 的 `unrun` 还更强，六阶段 / 三层角色 / 有界修复状态机同构，打分与发布阈值仍不取。**只有 T-4「快照滥用：大快照无人审阅」命中了一处真空**：`test/golden/record.sh` 自称整个迁移的安全网，docstring 第一句就写着「a golden file that silently encodes a bug is worse than no golden file」，**而裸跑它会把 53 个快照全部覆盖，没有任何保护、没有提示**；仓里关于「重录前逐条确认差异」只存在于 changelog 的叙述（我上两轮正是这么做的），不是规约、不是机检 —— 纪律全靠谁刚好去读那段 diff。**把安全网拆掉而不被发现的唯一办法，就是在一处真实回归上重录一遍。** 现在裸跑把每处漂移打成 `DRIFT` 并**拒绝写入**（新快照不受限，那是新增不是漂移），`--accept "<理由>"` 才写，理由打在结果旁边。造条件实测五条路径：无漂移裸跑正常重录；**往 `check-feature-arch.txtar` 注入一行伪造回归后裸跑 → 打出 DRIFT、rc=1、那个文件原封不动没被盖掉**；`--accept` 不给理由 rc=2；未知参数 rc=2（不再静默当成重录）；`--accept "<理由>"` 写入并打出理由，顺带把注入清掉，`--verify` 回到 53 same / 0 different。参数校验这一半进了 `agent-smoke.sh` 第 34 段（482→486 条，不进主循环所以不花时间）；DRIFT 拒绝那一半要跑三次 13 秒的完整录制，没进自动化，按手工实测记在这里。README 补「重录 golden 要说出理由」。**如实记下：那 4 条新断言只验过绿，红绿切换没验完** —— 把 `--accept` 的理由检查临时削弱后要重跑 `agent-smoke.sh`，被权限分类器拦住；削弱已立即还原并逐行确认（`record.sh:70` 无 `&& false`），两条拒绝路径与 golden 53/0 都复验过，但「这条锁逮得住它该逮的失败」这一步缺一次实证。人要求：quote「继续吸收经验」。

- 2026-11-06：把 jsonschema 装上，然后修掉它一装上就暴露的东西。`selfcheck` 一直在「这些锁本次没有执行」里列着 `delegation-return schema: no jsonschema` —— `requirements.txt` 早把它列为单条锁依赖，缺的是本机没装。① homebrew 的 python 被标成 externally-managed，`pip install --user` 直接被 PEP 668 拒；pyyaml 却在 user site，说明当初就是加 `--break-system-packages --user` 装的，按同样方式装上 jsonschema 4.26（venv 在这里解决不了问题：selfcheck 和所有脚本调的是裸 `python3`，不会进 venv）。那条锁从 2 跑 4 跳变成 **6/6**，`selfcheck` 的「未执行」整段消失。② 装上之后第一次真跑，就打出 `jsonschema.RefResolver is deprecated as of v4.18.0`——而 `requirements.txt` 要的正是 `>=4.18`，**所以这段代码一直跑在会告警的版本上，没人看见，因为唯一碰它的那条锁在本地一直跳过**；「a future release will remove RefResolver」，到那天这条锁会直接炸。改用 `referencing` 的 `Registry` / `Resource`（它是 jsonschema>=4.18 的传递依赖，`requirements.txt` 不必新增条目）。`-W error::DeprecationWarning` 下 6/6 全绿。**专门验了跨文件 `$ref` 没有静默失效**——registry 注册错会让校验器变成恒绿，那比报错更坏：造条件喂 `delegation_id: 'not-a-ulid'` 报出 `common.schema.json#/$defs/ulid` 的 pattern，喂 `changed: ['/etc/passwd']` 报出 `repoRelativePath` 的绝对路径拒绝，两条约束都来自被 `$ref` 的那份 schema。③ 四处安装提示各抄了一份会被 PEP 668 拒的命令（`selfcheck.sh` preflight、它的 SKIP 行与 `unrun` 行、`test_delegation_return.py` 的 skipTest），又是「声明在一处，用的是手抄的另一份」——全部改成指向 `requirements.txt`，装法连同那个 flag 只留一处真源，该文件头部补上 PEP 668 的说明与为什么 `--user` 不能省。golden 53 same / 0 different，`agent-smoke` 482/0。人要求：quote「解决 jsonschema问题」。

- 2026-11-05：从 `coding.jd.com/dts-ai-agent` 吸收三处机制。那是个运行时 AI Agent 平台（ReAct + 4 层 RAG + KEPA 自进化 + 分级降级），形态和导体不同，所以逐条判定能不能搬，而不是照抄架构图。① **标注迭代循环**（`scripts/annotate.py`）—— 它的 `docs/rules/AI编程规约.md` §1.4 把这个称作整条 AI 协作流里「最具价值的环节」：人不在聊天里复述十处要改的地方，而是**在文档里原地写注释**，文件成为人机之间的共享可变状态。idev 以前没有这个形态。落地换掉了原版的守卫（原版靠提示词里的「先不要实现」，idev 用本来就有的硬规则 3「矛盾、冲突或不清楚没对齐之前禁止写 sealed / arch.accepted」），并多加一条原版没有的判据：**标注被抹掉** —— 台账里有、文里 `@me:` / `@done:` 都找不到。前两条（未处置、处置无留痕）只是漏做，第三条是人的意见被一次重写悄悄吃掉，比没有这套机制更坏，因为人会以为自己提过了。原文 sha256 是身份，改措辞同时报「被抹掉」和「无留痕」。`check-feature.py` 在 `req-review` / `req` / `arch` 三个 stage 调它。仍不等人点头：agent `settle` 完并改成 `@done:` 这一关就过。**并补上发现性那一端** —— 机检闭环了，但触发它的是人，人不知道可以标注就不会标，那这个机制等于不存在（和仓里反复出现的「没人跑的闸等于没有闸」同一形状）；三处告诉人：`deliver/SKILL.md` 的 `req-review` 第 5 条与 `arch` 第 1 条（交出文档时说清路径和写法）、`references/guide.md`「一次交付怎么用」。grilling 和标注互补不重复：前者是导体发现分叉去问人，后者是人看完主动标；只有前者时，人心里那十处要改的地方仍然只能在聊天里复述。② **委派包注入既往**（`workflow.py` 的 `既往:` 行）—— 对应它的 `LearningLoop.GetRelevantSkills()`：任务执行前把历史技能拼进任务描述。idev 两本台账早就有且闸更严，缺的只是最后一步自动注入，以前要导体手动 `recall`，于是多数时候不发生；而执行者每次被派都是新上下文，**这张票已经付钱学到的东西，不随委派包到达就等于没有到达**。只取已过闸的 `authoritative` / `kept`，**候选明确不进** —— `recall` 的读者被告知过那是未验假设，委派包的读者是从零开始的执行者，一条未确认的结论以上下文身份到达，正是 `lessons.py` 自己点名的「一次局部错误变成系统性错误」那条路。自动注入不计 `uses`；台账读不了就不要这一行，不挡委派。③ **有界修复第二条红线改为实测**（`failure_signature.py`）—— `evidence.md` §5 早就写着这条，脚本也在判，但判的东西不对：`delta` 手填，`semantic_change` 实际是失败签名的影子，而不是「这一版补丁是不是上一版」。改成从 git 算增删行数与归一化 diff 的指纹。实测中发现一个会让红线**永远不触发**的缺陷：`.idev/` 下就是这本台账自己，不排除的话每轮都显示有改动；`test_bounded_fix.py` 用「票目录已提交」的真实形态锁住它。非 git 树退回手填 `--delta` 并打 `WARN`，不红。**明确不取**并写进提案正文：KEPA 置信度自适应（+0.05/−0.1）、100 分制发布阈值 80、LLM-as-Judge 混合评估 —— 三者都是分数门禁，而一个会自己涨落的数字最终会被当成「这条可以信了」的许可；Tier 1/2 语义缓存与向量检索（向量库已退役）；「执行任务期间遇到询问一律确认，不需要人工介入」（与 HITL 正面冲突）；MCP 合规 / A2A / DAG / Reflexion（是它自己要补的课，idev 已在更前面）。三组新锁各验过红绿切换（39 例）。golden 3 处差异逐条确认只来自 check-feature 新增那一行后重录，53 same / 0 different。`agent-smoke` 482/0。**覆盖边界**：第一轮下「只有三条可取」时只读了约 40% 的候选文档，第二轮把 AI 相关的剩余部分读完，四份逐一判为零新增并写明理由 —— `统一工程方法论`（INVEST/SMART/验收禁主观词都在 `req-quality.md`，`stage-gate.py` 已机检；函数长度、深模块、接口参数在 `coding-tables.md` 与 `canon.md`）、`大模型生成增强设计方案`（唯一机制是生成记录表，trace schema v2 已记 model/token/调用链）、`skill-dynamic-orchestration-design`（`workflow.py` + 配方更强；参数引用 `{PrevSkill.result.field}` idev **有意不做**，步骤间走落盘工件，内存变量引用会让中间结果不可审计）、`Go 语言 AI 编程规约`（Go 已由 `coding-tables.md` P5、`lang-scan.sh` 与 `reference/go.md` 覆盖，Java/Vue 另设 `conventions/` 页是因为有产线，有意分层）。另有九份判定为无需细读（dts 自己的代码地图、技能清单与产品功能设计），边界写进提案，日后发现遗漏可接着查。**如实记下**：`test_turn_cost.py` 的 `test_the_conductor_budget_is_untouched` 在本轮之前就红 —— 造条件验过，撤掉本轮对 `SKILL.md` 的唯一一行改动它照样红。根因不是脚本错了，是**断言用的代理判据被 SKILL.md 的正常演进推翻**：它断「输出里不出现 `idev-coder.md`」，而预算 `total` 只由 `COLD` 两页构成、on-demand 那段明写 `not counted`，执行者页**本来就该**在那张表里（能力表按名字指向它们，`BODY_REF` 正则也显式包含 `agents/`）。它要保的性质仍然成立，失效的只是代理，所以改成直接查性质：计数段里有两页冷启动、没有 `agents/`，`--agents` 的表头不出现在导体视图。强度没削弱，造条件验过 —— 把 `agents/idev-coder.md` 塞进 `COLD`，它变红并打出 `'agents/' unexpectedly found`，`total` 20487→35159。一个长期红着的本地闸和恒绿的闸一样有害，它训练人忽略红，而这是本地唯一那一条。顺手补了三个上一会话遗留的执行位（`deep-read-audit.py`、`test_canon_smells.py`、`test_deep_read_audit.py`，和本轮新增的三个测试犯同一个毛病，`chmod` 不改内容）。正文在 `state/proposals/20261105-absorb-dts-ai-agent.md`。人要求：quote「吸收../../coding.jd.com/dts-ai-agent在AI方面的架构和成功经验，把可取的地方补充到idev中，提升效率和精准度」、「继续」。

- 2026-11-04：名册自己也挑了一个目录，三项检查本地无闸。① `test-roster.py` 原来只扫 `scripts/test_*.py`，而仓里还有三个在那之外：`scripts/lib/test_doc_home.py`（**selfcheck / CI / test-roster 三处闸全无**，没有任何东西跑过它）、`scripts/lib/test_ticketless.py` 与 `test/promptfoo/test_r2_check.py`（只有 CI）。三个加起来 22 例，实测全绿 —— 缺的是闸不是正确性。**一个挑了某个目录的名册，和一份手打的名册漏得一样**，改成 `kernel.rglob("test_*.py")` 并跳过 `.git`/`__pycache__`/`attic`/`state`/`node_modules`，48→51 个文件，本地由 test-roster 跑的 24→27。② `syntax-check.sh`（0.5s）、`agents-check.py`（0.0s）、`refs-check.sh`（0.2s）此前只有 CI 跑 —— `refs-check` 名义上有 healthcheck 兜着，但没有任何自动化跑 healthcheck；三项合计 0.7 秒，挂进 selfcheck 并放在最前，它们逮的是最便宜的失败：脚本压根不解析、agent 定义与 kind 表脱节、文档链接指向不存在的东西。③ 紧接着发现同一个毛病还剩一半：名册只读 `.py`。四个 `test_*.sh`（`test_codegraph_sync` / `test_idea_inspect` / `test_lang_scan` / `test_problems_scan`）在 selfcheck 与 CI 里**都是零**，跑起来全绿（29 秒）—— 缺的仍是闸不是正确性，但「零闸」已经出现三次：手打的名册漏、挑目录的名册漏、挑后缀的名册也漏。改成扫 `test_*.py` 与 `test_*.sh`；shell 测试只接「可达性」这一半判据（没有 unittest 摘要可读、没有 `TestCase` 可找入口），跑的时候用 `bash`。51→56 个文件，本地跑的 27→32，test-roster 自身 24s→52s。`test_test_roster.py` 加 4 条用例锁住新行为（18 例），**红绿切换只红 2 条** —— 另两条是负向断言，扫描退回只读 `.py` 后同样满足，防的是误报不是漏报，如实记下。人要求：quote「继续优化」。

- 2026-11-04：本地闸也管 Go 侧。`go test ./...` 在**纯 HEAD 上就是红的** —— `TestPythonChecksAreEitherPortedOrListedAsDeferred` 报 `deliver-gates`、`gate-held` 两个 Python 机检在 Go 侧既没移植也没列为延期；没人撞见是因为本地没有任何东西跑 go test，而 `v2` 领先 `origin/v2` 两个提交、还没推。两者都是纯文本判断（路径白名单 / 双工具正则），和已移植的 `scope-held`、`scope-declared` 同构，所以进 `deferred` 清单时理由如实写 `NO PREREQUISITE — port it next`，不伪装成有前置；移植是实质 Go 开发，不在本轮。`go build`（6s）+ `go vet`（5s）+ `go test`（不带 -race，12s）挂进 selfcheck，走 `unrun` 通道，`-race` 留给 CI。另报告一处**只报告不动代码**的既存债：`golangci-lint run` 在 HEAD 上 170 个 issue（errcheck 63、gosec 75、gofumpt 10…），CI 用固定 `v2.14.0` 且无 `only-new-issues`，所以 lint job 一直红着 —— 但根因是配置与代码风格脱节：仓里裸 `defer x.Close()` **45 处**、包成 `_ =` 的只有 1 处（还带注释），而配置启用 errcheck。按 linter 改代码、放宽配置、或 CI 加 `only-new-issues` 三条路都改变项目约定，该由人定；本地 lint 闸也因此没挂（`--new-from-rev=HEAD` 实测会报 5 条，全来自上一会话未提交的 Go 改动，一挂就红）。第二轮量了代价与顺序：四条新锁让 selfcheck 从 2:12 变 3:50，而**慢到没人等的本地闸就是没人跑的闸** —— 零侵入计时（输出接进按行打时间戳的管道）得出 34 段 230s，最慢一段是**既有的** `signoffs follow the risk tier` 57s（其中 `test_record_findings` 16s + `test_step_land` 16s 占一半），本轮四条合计 83.7s。两个假设都查过不成立：`bin/idev` 不 stale（手工构建后重量仍 16.5s），两个文件里 `time.sleep` 零次（2.1s/用例是端到端起进程加 SQLite 的固有成本）。不做并行化：多锁共享 `IDEV_DATA` 与 `TMPDIR`，几十秒不值得拿输出交错和夹具互踩去赌。改顺序：`go build` 6s 发现的编译错误最便宜最常见却排在 207s 处，把这条锁移到函数定义之后、第一条实质检查之前（它不依赖夹具），**Go 侧结论从 207s 提前到 13.6s**。`selfcheck PASS` 改为带 `(${SECONDS}s)`，让下一个加锁的人在结论行看到自己的代价（改前确认过无代码断言该文本）。另用仓里的 `turn-budget.py` 自检本会话，判出 `serial_reads=10 rounds=10 ratio=1.00` —— 判得对，我一路串行发互不依赖的只读调用，低于规约的 1.5，已改为同条消息并行发、长命令放后台。这条判据没有门禁（「不为观测另停」），所以只在有人去读时起作用，而本会话之前没有一轮读过它。正文在 `state/proposals/20261104-local-gate-covers-the-go-side.md`。人要求：quote「继续优化」。

- 2026-11-04：让 CI 真的跑它声称要跑的东西。两处缺口同一形状 —— 声明在一处，CI 用的是手抄的另一份。① `bin/idev` 被 `.gitignore:39` 排除、不在 checkout 里，而 `python` 与 `kernel locks` 两个 job 只有 setup-python：造条件实测（影子 PATH 摘掉 go + 无 `bin/` 的 31M 副本），`test_record_findings` 6/6、`test_step_land` 8/8 **完全空跑**，`test_auto_gate` 1/10、`test_hooks` 2/23、`test_idev_bin` 1/9 局部失效，五个都退出 0；完全空跑的那两个 CI 根本不点名、只能靠 selfcheck，而跑 selfcheck 的 job 也没有 Go，**所以这两条锁在 CI 上从来没执行过**。给这两个 job 补 setup-go（`golden` 钉死 `IDEV_BIN=off`、`generate` 只比对生成物，都不加）。② 四个 job 都写 `pip install pyyaml`，而 `requirements.txt` 才是依赖分档的真源（pyyaml + jsonschema）——jsonschema 从来装不上，`test_delegation_return` 每次 CI 都 6 个跳 4 个，那份「硬依赖/单条锁依赖」的分档一天也没生效过；四处改成 `pip install -r requirements.txt`。验证把条件造出来做完了：有 Go 的干净 checkout 下 `test_auto_gate` 10/10、`test_hooks` 23/23 skipped 归零，CI python job 的四步命令全 `rc=0`、十个测试全绿；隔离 venv 装齐依赖后 `test_delegation_return` 从 `OK (skipped=4)` 变 `OK`。不改那五个测试的 skipTest 条件（没有二进制就跳过是对的，要修的是跳过了没人知道，已由 `unrun` 汇总解决）。③ 补 setup-go 时我自己写了硬编码 `go-version: "1.26.x"` —— 和 ② 同一个毛病，版本真源是 `go.mod`，改成 `go-version-file: go.mod`（`go` job 的 matrix 与 lint/vuln 的固定版本是有意选的测试面，不动）。④ `agent-smoke.sh`（482 条断言、覆盖委派层脚本与契约、不需要模型、27 秒）本地无闸，CI 把它作为 selfcheck 之后的独立步骤跑；挂进 selfcheck 并撤掉 CI 那个步骤，不在两处各列一份（无 Go 环境实测同样 482 条全过，不需要 go 守卫）。README 481 条更正为 482。查过但不改：`install-weekly-audit.sh` 跑 healthcheck 的 `|| true` 注释明写 `(non-fatal)`，是播种快照不是门禁；`healthcheck.sh` 查本机环境与拓扑，挂进 selfcheck 会让红随环境漂；`boost.md` 里「healthcheck 恒定 FAIL」是历史例子不是现状。正文在 `state/proposals/20261104-ci-runs-what-it-claims.md`。人要求：quote「continue」、「继续优化，创造条件验证」。

- 2026-11-04：安全网也要有人拉一下。`test/golden/record.sh` 自称「整个迁移的安全网」、README 把它和 selfcheck 并列成「两本引擎账，两本都要绿」，但**本地**零调用（selfcheck / healthcheck / Makefile 全不跑它）—— 跑一次是 `43 same, 10 different`。更正一处先前写错的话：CI 里**有**一个 `golden replay` job 跑 `--verify`（`ci.yml:33`），我最初只搜 `.sh` 与 Makefile 就说「零自动化调用」是不准确的；准确说法是远程有闸、本地没有，而这 10 个差异都来自未提交改动，CI 从来没机会看到。其中 8 个只差 `DIGEST match` 一行（配方哈希变了，场景行为零变化，所以重录不掩盖任何东西）；另外 2 个是硬缺陷：当前实现开始多打 `HANDOFF rounds=359 ctx=308926` 和回合预算 WARN 两行，而这个数字**两次 verify 之间就在变**（它数的是当前会话转录长度），所以这一类**重录也救不了** —— 上一会话把 `turn-budget.py` 改成「不给路径就读本会话自己的转录」（动机对，同一条线），副作用是 `trace append` 的输出开始依赖谁在什么时候调用它。`normalize.py` 救不了这一类：问题不是值会变，是这两行出不出现都取决于会话长度。所以在源头抑制 —— `session_rounds()` 认 `IDEV_NO_SESSION_PROBE=1` 答「没有会话」，`record.sh` 录制与验证都设它；正常调用不设，行为不变。`record.sh --verify`（13 秒）与 原有那条 gate/lease channel 守卫的 `echo SKIP` 改走 `unrun`（**更正**：这两个脚本 selfcheck 一直在跑、也一直有 `command -v go` 守卫，先前说它们「零自动化调用」是因为那条 grep 带了 `head -6` 被截断，却据此下了全集结论；按此加的重复锁已撤销）。README 三处数字按实测更正（golden 50→53、gate 14→23、lease 17→25）。不改 `normalize.py`（它的替换清单是 Python 录制与 Go 回放的契约，两边必须逐条一致）；不让 `trace append` 默认不观测会话（那个观测解决的是真问题，只在录 golden 时关）。正文在 `state/proposals/20261104-golden-safety-net.md`。人要求：quote「继续」。

- 2026-11-04：`gate-channel.sh` 的「ask 不跨 gate request 持 run lock」用例有竞态，挂进 selfcheck 后第一次全量跑就红（`held=1`），而单独跑 5/5 全绿。根因是它等 `run.yaml.lock` 文件出现就当作 `start` 已结束，但那个文件是 `start` **创建时**出现的，于是和 `start` 自己的持锁窗口赛跑，机器一忙就输。改成在那 2 秒窗口内重试加锁。断言强度没削弱，单独验过：锁被全程持有时仍 `rc=1 held`，释放后 `rc=0`，并行 3 个实例制造负载 3/3 绿。一个会随机红的锁和恒绿的锁一样有害 —— 它训练人忽略红，而这把锁是上一条改动挂进来的，所以一并修掉。人要求：quote「继续」。

- 2026-11-04：negative 锁要说出它是因为什么失败的。33 条「期望失败」的锁里，只有 `aligned forge` 一条验了失败原因（它从写出来起就把输出存文件并 grep 文案，是仓里早就有的正确范例，只是没名字、没人照它改其余的），另外 32 条的判据都是退出码非 0 —— 而 `selfcheck.sh` 的 preflight 注释自己承认过这件事（2026-11-01 缺 pyyaml 时，每条锁都因为错误的原因通过了，preflight 堵的是那一个原因，不是这一类）。`expect_fail <stage>` 覆盖走 `run()` 的 16 条，`expect_fail_sh <shell 代码>` 覆盖另外 17 条（命令是子 shell 或自带环境变量赋值，传不进 argv；用 `eval` 而非 `bash -c`，因为其中一条要调用当前 shell 的 `run()`），三者共用 `_reason_or_fail`：失败**且**输出里有指定原因才算过，因别的原因失败就打出真实的 FAIL 行再报红。关键词先按文案推断（29 条猜对、4 条按实测修正），再回头读各检查器源码把 7 条过泛的收紧 —— `promote refuse` 原来用 `FAIL` 作关键词，而负向场景的输出必然有 FAIL 行，等于不检查，现在用 `plan has FAIL cases`（`promote.sh:61`），能和另两种拒绝原因区分开。顺手修掉 outbound 两条负向锁共用同一句 fail 文案、红了分不清是哪条的问题。仍只看退出码的剩 0 条。不动 preflight（没有 yaml 时早停仍然对，两者互补）；不把关键词写成完整文案（文案会改，那是噪声）。正文在 `state/proposals/20261104-negative-locks-name-the-reason.md`。人要求：quote「提交，然后继续审查」、「修复优化」。

- 2026-11-03：锁没执行不等于通过。五条锁（auto gate、hooks、record findings、step land、idev bin）在既没有已构建 `bin/idev`、又没有 Go 的机器上把用例全部 `skipTest` 掉、退出 0，而 selfcheck 用 `>/dev/null 2>&1` 跑它们 —— 整块保护以**通过的样子**失效，比 pyyaml 那次「以失败的样子失效」更难发现。`run_test` 解析 unittest 摘要，全 skip 记「这条锁没跑」、部分 skip 记「N of M」，`unrun` 把未执行的锁汇总到 `selfcheck PASS` 旁边（2000 行输出里的一行 SKIP 没人看）。含 skip 的 7 处点名改用 `run_test`，`test-roster.py` 不许会 skip 的测试再被吞输出。`requirements.txt` 补上 Go 工具链这一档 —— 它影响五条锁，却是唯一不在依赖声明里的。不把全 skip 改成红：Go 是可选档，要的是明确告知而不是逼人装。`delegation-return` 那条锁是正确范例（显式 `import jsonschema` 守卫 + 可见 SKIP），不是缺陷。人要求：quote「按分析出的结论优化，并修复所有缺陷」。

- 2026-11-03：每个测试都要被撞上，而且跑起来真的在跑。`scripts/test-roster.py` 查名册本身：有 `TestCase` 子类却没有 `unittest.main()` 入口 → FAIL（跑它等于跑 0 个断言）；`test_*.py` 既没被 `selfcheck.sh` 点名又没在这里跑过 → FAIL；它自己跑的那些全 skip → FAIL。47 个测试文件里 23 个没被 selfcheck 点名，而 CI 自己那份手工名册只覆盖其中 3 个 —— 20 个两边都没有闸；`test_lessons_conflict.py` 有两个真用例、无入口，`python3` 跑它无输出退出 0 —— 补入口后真跑真绿。不把 selfcheck 的 24 条点名改成全自动（会丢掉每条锁自己的失败文案），不引入 pytest 作为门禁依赖。检查器自己也配了测试（`test_test_roster.py` 14 例）。正文在 `state/proposals/20261103-test-roster.md`。人要求：quote「继续」。

- 2026-11-03：`signoff-audit` 不再把执行者字段当签字字段判。`by` 按父节点分语境：`signoff.by` / `confirmed_by` / `signed_by` 必须 `is_human`；`verification.by` / `recorded[].by` / `delegations[].by` / `revisions[].by` 接受人名或已登记的执行者名（`kind_agents.AGENTS` + `conductor`），但仍要求命名一个真实主体，所以占位词 `by: human` 照样报；空值不报（没有签字就谈不上失效）。`quote` 同理：`signoff.quote` 是确认语，`decisions[].quote` 不是（「决策不是签字」）。命中按类别分组输出：签字类才说「需要人重签」，执行者类说「记录里的 by 是角色词，重签不是解决办法」—— 那 2 条 `by: human` 的 note 表明是人下指令、agent 执行改写，填人名等于伪造审计记录，所以**不改那两行 yaml**。`--all` 保留旧的全量清单。`newly-failing` 从 27 降到 2。不改 `is_human`，不挂进 selfcheck（它扫产品仓历史，会让红随交付漂）。正文在 `state/proposals/20261103-signoff-audit-field-context.md`。人要求：quote「继续」、「按分析出的结论优化，并修复所有缺陷」。

- 2026-11-01：停问前评估这一步是低效、不合理，还是在替较弱模型付代价。`process-eval.py stop` 打出 `now=CORRECT` 就按已经写明的规则做，不问。同一类重复出现，或补丁的代价还在、要挡住的失败却没有了，`scan --propose` 才写草案。草案带 `accept: later`，起草用过的轨迹不能再当接受证据。不打分，不按模型名字删步骤，不自动改 Skill。复盘只把计数写进正文，不抬 signal。正文在 `references/process-eval.md`，补丁登记在 `references/scaffolds.yaml`。人要求：quote「增加skill，流程机制评估识别能力，以及时发现低效不合理的环节并更正，具备面向更强大模型自进化能力」。

- 2026-11-01：需求、设计把认知和还缺的信息摊开，有矛盾、冲突、不合理或不清楚才停下来对齐。编码及之后按该阶段规范做，验收不过就自省改到通过，再进入下一阶段。一句确认、通过或继续仍然不改变后面怎么做。人要求：quote「整个工作流程中，需求、设计阶段需要人机充分沟通对齐认知和信息。后续阶段依次向后推进，每阶段开始和结束都会有相应的规范制定和成果验收，达不到预期标准需要自省来发现问题、解决问题直到通过阶段验收，然后继续下一个阶段工作...遇到矛盾点、冲突点或者不合理不清楚的地方，需要停下来和人讨论对齐认知，然后继续。」

- 2026-11-01：只有要人做选择时才停。审查签收、实现审核、测试结果确认、文档定稿不再等人点头：`next` 打出 `GATE pass`，`drive` 记下并继续。`with.decision: true` 的闸才打出 `DECISION` 并停下，目前是提交推送和自进化落地。前面步骤还有未答信号时，后面的关卡不能记过。`code-review` 的 `review.fix` 带 `accept_all_findings`，待签收的 `I*` 也进入用例分片。人要求：quote「直有遇到需要决策时，才需要停下和我讨论，而不是我各种应付式的签确认、审查...后才向下执行」。

- 2026-11-01：「验收」「继续」「确认」「通过」以及只由这些词组成的句子是催办。`scripts/nudge.py` 打出 `NUDGE proceed`：做当前阶段还开着的事，不改密封基线的 goal / items / non_goal，不记 `stop`，不写 `next`，不复述「没有写入」或「关卡没有变化」。检查没过就补那一项；检查过了就写这一关。`decide` 收到这种原话不记成回答，也不再问一次。点名解封或回退仍是 `NUDGE named`。人要求：quote「优化这些毫无意义的反复确认、验收」。

- 2026-11-01：派发前把请求头冻进 brief，打印不再重读执行者文件。同一执行者的定义 sha256 变了，下一份委派包写 `请求头变更`。`PROGRESS` 也冻在那份 brief 上。`react` 里候选之外的调用记成 `UNKNOWN_TOOL` 或 `NOT_ADMITTED`，循环仍开着，不走 `on_fail`。`open` 时候选未登记仍拒绝。不引入 Cordis。正文在 `references/agents.md`「模型看见的内容从日志重放」。人要求：quote「继续深度解析和集成」。人确认：by wangwei794，quote「确认」，2026-11-01T20:16+08:00。`parse_confirm` 收下。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-11-01：外挂 Skill `~/.cursor/skills/understand-anything`（包装 [Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) `4e6d329`）。读实现、根因和 `review.report` 在仓内已有 `.ua/knowledge-graph.json`（或旧目录 `.understand-anything/`）时打开它，用一跳邻域提名要读的文件。没有图不建，不 `pnpm install`，审查步不写 `diff-overlay.json`。图摘要回到源码锚点或 codegraph 已点名的符号才进 `I*` / 根因。不替代 `codegraph_impact`，不把 `.ua` 收进经验或检索。`link-companion-skills.sh understand-anything` 可显式链别名。人要求：quote「集成skill：https://github.com/Egonex-AI/Understand-Anything用于辅助代码理解和Review」。

- 2026-11-01：执行者每次被派都是新上下文，模型看见的内容改从日志重放。`请求头:` 记下执行者定义的 sha256 和声明的 tools。`attempt > 1` 把 `reads.yaml` 里 sha256 仍一致的区间原文放进委派包，最多 4 段、共 4000 字；字节变了、文件不在或路径不在仓根内就不重放。不再告诉新的执行者不要重读。不引入 Cordis，不另起运行时。正文在 `references/agents.md`「模型看见的内容从日志重放」。人要求：quote「使用deepseek harness架构增强agent」。
- 2026-11-01：最后一片 `workflow.py land --shard` 在各片都已记下且没有打回时跑 `fanout.py merge`。这一步仍由导体打开证据后 `record` 一次。不派执行者。人要求：quote「继续优化」。
- 2026-11-01：`workflow.py land` 在 `SEND BACK` 的同一段输出里打出带 `prior_failure` 的重派包。分片同样。不派执行者。人要求：quote「继续优化」。
- 2026-11-01：`workflow.py drive` 在分片前跑内核脚本的 `PREP`（`coding-scan.sh`）。退出码 0 或 1 都算扫完，日志路径写进每片委派包的 `扫描:`。编译这类 `PREP` 仍由导体先跑。不派执行者。人要求：quote「继续优化」。
- 2026-11-01：`workflow.py drive` 打出 `PARALLEL` 时，为这一波每个执行者打出委派包，并跑过各自的 assess。每个回报仍只 `record` 自己的 step。`ASK slot` 仍原样打出。不派执行者。人要求：quote「继续优化」。
- 2026-11-01：`workflow.py drive` 在 `FANOUT` 且没有 `PREP` 时为每片打出委派包并领该片租约。一片的回报用 `land <step> --shard <id>`，这一步仍等 merge 之后只 `record` 一次。`PREP` 仍留给导体先跑。人要求：quote「继续」。
- 2026-11-01：`workflow.py drive` 停在单个执行者之前会自己跑 `FANOUT_ASSESS`。`SERIAL` 打出委派包，`FANOUT` 只打出分片清单，`MERGE` 且没有 `SHARD` 时跑 merge。`PARALLEL` 和 `ASK slot` 仍原样打出。不派执行者。人要求：quote「继续优化」。
- 2026-11-01：小改的范围检查不再派 `idev-ops`。`scope.baseline` 由导体核对密封基线与 HEAD。`workflow.py drive` 连续跑导体自己的命令，到执行者、人或失败就停。委派包带必读页摘录和 `include: true` 路径；重派带已读区间。宿主没给耗时就用起止时间或转录文件的时间。导体的一次 PASS 在 `ApplyMany` 里同一事务写入。`deliver.code_pass` 和 `review.fix` 只在 include 路径分属不相交的顶层模块时分片，每片只锁自己的路径。人要求：quote「按当前优化方案依次改进落地」。

- 2026-10-31：审查和根因分析的中间文件进 `.idev/task/<feature>/`（`doc_home.py --key work`）：`review.md`、`review/`、`hypotheses.yaml`、`lessons.yaml`、`ops.yaml`。最终交付物才写入使用 idev 的工程文档（`docs/prd`、`docs/spec` 或 `docs/specs`、`docs/test-case`、`docs/task` 里的交付票与 issue）。已有规范文档时，`--key task` 仍是交付票。`code-review` 没有交付物，票目录就是 work。人要求：quote「两者不冲突，review或者问题根因分析过程中会产生大量中间文件，这些中间文件都要放在.idev中，最终输出交付物时，才进使用idev的工程文档中。」

- 2026-10-31：整仓代码审查过程不记入工程文档。feature `code-review` 的票目录固定为 `.idev/task/code-review/`，仓库已有 `docs/` 也不再写入 `docs/task/code-review/`。人要求：quote「code review 过程不记入工程文档」。

- 2026-10-31：Spec Kit 的核心过程对照写进 `references/spec-kit-mapping.md`。采纳的是：存量仓只写有界变更和必须保持的行为；规约冲突时改这张票；对照代码时尺只认密封基线、方案和 slice，勾选和「已经实现」不是证据，少做和部分补上、多做删掉、与基线相反则停；点名的复现没跑不能写成通过；想法要有反对证据，停下来不建票。不搬 `.specify/`、覆盖率、评分卡、用默认值猜掉澄清、自动追加任务直到 Converged、以及从规格生成实现。人要求：quote「深入研究 https://github.github.com/spec-kit/ 沉淀核心能力到idev中」。人确认：by wangwei794，quote「确认」，2026-10-31T16:10+08:00。`parse_confirm` 收下。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-30：控制面对上现有部件。写租约、分片指纹、会话收尾、`prior_failure`、委派包和 `QUEUED` 就是书里的锁、终止、进度和总线。审查者 `CHANGED` 只许 `review.md` 和 `review/shards/`，`gate-held` 挡住改测试和门槛。同一上下文里不再审查自己刚写的产物。独立密钥、步骤级价值树、多数表决留在书里。人要求：quote「继续深度挖掘和沉淀」。
- 2026-10-30：留下的程序钉住脚本、结果和复现的字节。文件再变，`check` 失败，召回写明不要当成现行能力。脚本变了还用原来的结果，`transform` 拒绝。没有钉住字节的已留下条目不能在原地补钉。不执行脚本。人要求：quote「继续深度挖掘和沉淀」。

- 2026-10-30：登记工具必须写明做不到什么。`references/tools.yaml` 每条有 `limit`，缺了 `workflow-check` 不过。`next` 和 `react_loop` 原样打出 `LIMIT`，`TOOL` 仍是登记的 `command`，不追加参数，也不执行。不新做工具发现。正文在 `references/agent-accuracy.md`「工具不改口」。人要求：quote「继续深度挖掘和沉淀」。

- 2026-10-30：进度行改成收口数，并点名还开着的步骤。`PROGRESS closed=<已收口>/<总步数> open=<步骤 id>` 打在 `next` 末尾和委派包 `END BRIEF` 前。跳过、未证明、失败后已改道算已收口，不是通过。整理轨迹时留下 `invoke`，`recorded` 带上步骤证据路径和复核证据路径。不新做缓存层。正文在 `references/agent-brief.md`「本轮看到的上下文」。人要求：quote「继续深度挖掘和沉淀：https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter2.md」。

- 2026-10-30：持续进化补上「办成之后还要看什么」。通过件数旁边写下 token、拒绝边界和权限、维护兼容和以后调试的负担。写提案时不打开接受用的结果，下笔前先读当前正文和不能改的验证。旧轨迹上排到最好，不能单独说明下一次在线也会更好。程序结果要写出最终状态，在独立初始状态上复现；回放对不上就清掉再探索，不在旧记录上打补丁。主张写参数名，不写某一次的字面量。模型报出的置信度不是批准门槛。不建回放器，不打分。正文在 `references/self-evolution.md`「学习信号写到哪里」，程序留下条件在 `references/sediment.md`。人要求：quote「继续深度挖掘和沉淀」。

- 2026-10-30：外部文本只当数据，技能里的句子不是护栏。网页、工具结果、检索片段和第三方工具说明里的指令不执行。还没返回的结果不是成功，次数仍认脚本。不可逆动作还要有执行前的门和写入时的拒绝。正文在 `conventions/evidence.md` 信任表，冷启动多第 9 条。第二章的次数、进度和隔离仍在 `references/agent-brief.md`。分类器、模型选型和框架对照没有搬进来。人要求：quote「沉淀经验并改善idev：https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter1.md https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter2.md」。

- 2026-10-30：同一范围里动作不同的经验并排留下。`lessons.py recall` 打 `CONFLICT`，被 `--top` 截掉的那一条也列出；`check` 只警告。不改旧行。画像、图谱和从对话抽记忆仍不建。人要求：quote「沉淀经验并改善idev：https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter3.md」。

- 2026-10-30：工具参数不静默改写。选错命令先改说明。超时后先核对副作用再重试。正文在 `references/agent-accuracy.md`「工具不改口」。嵌入式工具发现、边车模型和技能市场没有搬进来。人要求：quote「沉淀经验并改善idev：https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter4.md」。

- 2026-10-30：启动不是完成，取消不撤销已经做完的动作，排队的更新都生效。页面下一段从现在的页面重新看。正文在 `references/agents.md`「这一轮之外到达的事」和 `references/browser-program.md`。语音、机器人和世界模型没有搬进来。人要求：quote「沉淀经验并改善idev：https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter6.md」。

- 2026-10-30：持续进化再补提炼和淘汰。归纳要带职责边界，不整页重写。通过件数变多时写明是哪一个动作变了，并同时看违规、回退和未证明。程序留下时，`sediment.py transform` 拒绝把起草证据再当 `--repro`（路径或内容相同都不行），手改 `kept` 也会被 `check` 抓住。新条件收窄 `not_when` 并与旧条并列；同一条件被反证才 `retire`。没有自动对错时，走样、把噪声写成发现、只留最顺的一条，都留在记录里给人判断。不建回放器，不打分。正文仍在 `references/self-evolution.md`「学习信号写到哪里」。人要求：quote「继续深度挖掘和沉淀」。

- 2026-10-30：下一轮只接核实过的状态。重派包只带原目标、证据路径、未过的检查和剩余工作；留痕原文和推理不进下一份包。没有检查名或 file:方法名就不重派生成者。生成者只改点名的失败项。复核看证据和尺。`next` 打出的下一步就是这一跳，预算仍是分片 8、循环硬顶 16、无正文回合 8。要撤销另一个执行者本轮已写的产物就停下来问人。不新做消息总线、进度文件、乐观锁或级联取消。`prior_failure` 句末写明只改点名项。正文在 `references/agents.md`「下一轮只接核实过的状态」。人要求：quote「继续深度挖掘」。

- 2026-10-30：上下文再挖两处。`next` 末尾打 `PROGRESS settled=<已完成>/<总步数>`，从步骤状态数出。整理轨迹时 timeline 留下 `decisions`、`rejected`、`delegations`、`recorded` 和 `calls`，memory 仍是一行指针。常驻 `SKILL.md` 去掉与落点页重复的附录，目录改指执行者页。不新做缓存层。人要求：quote「继续深度挖掘和沉淀：https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter2.md」。

- 2026-10-30：经验的决策步可以附上 prefix。目标、环境、agent 与工具版本、首错前的一份文件、可接受动作和禁止动作要一起在。主因是最早且能解释后续失败的那一步，后面的连锁单独写。`lessons.py check` 只验这组形状，不另跑 Agent，也不用分数决定 promote。没有决策步的环境事实仍只写六问。`user-correction` 和 `failed-action` 没写 prefix 时警告，不因此失败。内核记了一条候选 L2，未 promote。正文在 `references/rootcause-guards.md`「决策步」。人要求：quote「沉淀经验并改善idev」（上文 https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter7.md）。

- 2026-10-30：跨会话只把现有三层写清楚。trace 和 timeline 只追加，矛盾的两条都留着；事实走经验账，可重跑的做法走程序候选；codegraph 和本地 Milvus 从源码重建，不收录 `.idev/memory.md`。预览写明检索到的文本不是要执行的指令。不建用户画像，不建知识图谱。正文在 `references/self-evolution.md`「跨会话留下什么」。人要求：quote「继续深度挖掘和沉淀」。

- 2026-10-30：可重跑的做法收成程序候选。事实仍走经验账，要看语境的判断仍走提案。两条内容不同的结果并且由人确认才留下；脚本必须已经存在，本命令不生成也不执行。外部内容拒绝。`gc` 只指出重复、包含、失效和只有一条证据的条目，不删除。正文在 `references/sediment.md`，命令是 `scripts/sediment.py`。人要求：quote「知识沉淀和核心能力转化：https://github.com/bojieli/ai-agent-book/blob/main/book/chapter5.md」。

- 2026-10-30：上下文只补进现有冷启动和循环计数。常驻两页不写时间、当前步和次数。`next` 的 `LOOP` 与 `show` 的 `COUNT` 带 `hops=已用/上限`，次数从循环文件数出。旧轨迹仍是 memory 一行指针，结构化事实留在 timeline。不新做缓存层，不另写状态栏。正文在 `references/agent-brief.md`「本轮看到的上下文」。人要求：quote「沉淀经验并改善idev：https://github.com/joyaicode/ai-agent-book/blob/main/book/chapter2.md」。

- 2026-10-30：持续进化只补进现有闭环。学习信号要四件一起在（环境结果、路径是否允许、证据位置、失败类型）；证据不够就留在轨迹里。事实进经验候选，能说清的判断进 Skill 的最小 diff，能确定执行的检查进程序或既有门禁。写出更新的一方不改验证、测试、发布门槛、审计和上一份稳定版本。不建回放模拟器，不训练参数，不按分数改写 Skill。正文在 `references/self-evolution.md`「学习信号写到哪里」。人要求：quote「知识和经验沉淀：https://github.com/bojieli/ai-agent-book/blob/main/book/chapter9.md」。

- 2026-10-30：再派执行者只为上一手生成时拿不到的信息。跑出来的结果、独立读到的产物和尺、写集不相交的另一片、带证据路径的领域约束，这四样才算。`STATUS: PASS` 仍是提议。三种假象打回原执行者补证据：做了一部分就说全部做完、一条路不通就说整步做不到、口头办成但没有对上尺的产物。分片保持互补，先完成的一片不取消其余。辩论、投票、蜂群、worktree、跨组织协议没有搬进来。正文在 `references/agents.md`「再派一个执行者」。人要求：quote「知识和经验沉淀：https://github.com/bojieli/ai-agent-book/blob/main/book/chapter10.md」。

- 2026-10-30：本地 Milvus 改为两路召回再重排。词和汉字双字各走一路，两路都有命中时用倒数排名合成（k=60），再按片段里查询是否原样出现、词覆盖了多少来重排。汉字双字只补单路词检索覆盖不到的正文。不下载重排模型。人要求：quote「混合召回和重排序」。

- 2026-10-30：两阶段读增加本地 Milvus 提名。`index` 把源码片段写入 `.idev/rag/milvus.db`，`preview` 用它补符号检索没覆盖的正文用词。库里没有函数体；源文件一变，旧库就拒绝再查。不另起 Docker。人要求：quote「考虑增加RAG增强检索，使用单机版milvus来辅助」。

- 2026-10-30：接着挖了四类页面现象。监听要写在动作前，新页面要在 `finally` 里关，定位歧义之后不能改用序号去点。进行中和成功必须是两句不同的字，同名动作用 `scope` 分开。会改页面的后续程序沿用任务里已有的幂等键。`tally` 把虚假成功、结果不明、失败、已核对分成四个数，不加总。人要求：quote「继续深度挖掘和沉淀」。

- 2026-10-30：界面、前端实现和故障现场补进既有落点。`ui` 块要求动作有唯一名字，并写明进行中看得到的字。组件按这个名字和这三态来写。页面故障用 `scene` 核对回执里还缺的现场项，截图只收文件路径。人要求：quote「涉及到UI设计、前端编码规范、运维中故障现场抓取等层面经验和沉淀」。

- 2026-10-30：浏览器程序补上下一步。`advise` 读一条回执，告诉自动化、根因和复现下一段是等待、只读核对、收紧定位、处理遮挡，还是从当前页继续。回执仍只证明发生过什么。不安装浏览器。人要求：quote「集成UI自动化、问题根因分析和问题复现层面可以借鉴的经验和工具」。

- 2026-10-30：两阶段读收进内核。读实现先出薄目录，再加载一个行区间；同一路径同时出现在符号和经验证据里时用倒数排名前移。不建索引，不调用模型。上游仓库里的深度研究图和 Wiki 分析没有可运行实现，没有搬进来。正文在 `references/context-stage.md`，命令是 `scripts/context-stage.py`。人要求：quote「深入理解https://github.com/joyaicode/codestyle代码解读增强处理能力，集成核心能力到idev中，辅助AI端到端能力」。

- 2026-10-30：浏览器程序按确认补全。一段程序里同时放观察、动作和断言。回执带结果、阻塞原因、页面变化和是否结果不明；失败原因带到下一段。页内硬点、base64 截图、任务外浏览器、并行改页面、抢前台、超过 8 个未丢弃任务、把认领的标签页丢掉，都拒绝。`inspect` / `finish` / `claim` / `discard` 只改回执记录。人要求：quote「确认，完全集成」。

- 2026-10-30：浏览器程序收进内核。一段程序一次提交，回执按任务和请求号保存，会改页面的同一段只跑一次；`succeeded` 不等于业务办成。不安装浏览器，不调用外部 CLI。正文在 `references/browser-program.md`，检查是 `scripts/browser-program.py`。人要求：quote「目标：核心能力集成，不一定要装浏览器或者cli」。

- 2026-10-29：编码或查问题期间本轮启动的服务，任务结束时关停清理。正文在 `conventions/SKILL.md`「会话收尾」；编码出门、排查收尾和三个执行者各留一行指针。只关本轮拉起的进程。人要求：quote「规约：编码或者查问题期间启动的服务，在任务完成后要进行关停清理」。

- 2026-10-28：没有未决分叉就在同一轮接着做。`stop` 为空时不把「补跑证 / 再审查」写成 `next` 等人说继续。trace 只作记录，不结束本轮。人要求：quote「优化流程，提升交互效率：不需要停下来对齐认知的地方，直接继续向后执行即可。」

- 2026-10-28：确认文法从批准路径拆掉。疑问、否定、空句子、解封不带关键字都批准。`prompts.log` 不再核对原话。否决只走 `gate reject` / `record FAIL`。人要求：quote「确认机制过于死板机械，完全是负担，没有带来任何收益，彻底废除干净。」

- 2026-10-28：废除交付签字确认。需求通过、架构通过、实现审核、提测结果不再等人说确认或通过。`check-feature` 过了、没有未决分叉，就写下这一关并继续。`继续`、空 quote、`看着差不多` 都批准交付门。疑问、否定、`驳回` 仍不落笔。解封和回退仍要点名。手改 `reopen_baseline` 仍被钩子拦住。人要求：quote「把签字确认环节彻底废除，太垃圾了」。

- 2026-10-28：点名回退或解封但带否定或犹豫，不再算同意。今天工作区里新加的「普通说法点名也算」那条路径跳过了否定和犹豫检查，`不要解除密封`、`先别解除密封，再想想`、`不要回退到需求` 在 Python 和 Go 两边都判成通过；门批不批就靠这个解析。现在两条路径共用同一个拒收检查，中文拒收词补上转折 `但` / `可是`（英文早有 `but`）。密封门上说出密封本身（`密封` / `进行密封` / `确认密封`）也算同意，带否定、转折、犹豫或问号照样拒；kafka-project 那边人回「进行密封」被判成没表态，门至今挂着。Go 的 `gatesvc` 原先没把密封门的类型交给解析，密封门回「确认 回退到实现」也会批准，现在判关键词不符。共享用例表 `test/signoff/cases.yaml` 补 18 行，`gatesvc` 补一条端到端用例，修前都红。人选定：密封门认点名密封。另：`idev audit verify` 补进 CLI，默认从最后一个检查点之后算（没有检查点就从创世），`--from 1` 从创世全算，断链时报出第一条坏的 seq 并退出 1；真库 204 条复算无断。`app.go`、`baseline_cli.go` 补跑 gofmt。未提交。

- 2026-10-28：人机对齐即签字。`idev gate approve --quote` 用对话里的原话批准开着的门，不再要终端，也不再要短码。通道记 `chat`，保证仍是低。会话已在记 prompts.log 时，原话必须出现在这份日志里。`workflow.py record PASS --by --quote` 在门还 pending 时用同一句原话把门批准，再把批准读回这一步。`继续` 仍不批准。人确认：quote「优化这种低效无意义的签字，人机交互达成共识后即算签字。」

- 2026-10-28：签字护栏只查票据和 run 的 YAML。Cursor 改文件时会把整份文件交给 `pre_tool.py`，签字字段的正则又会命中源码里的 Go `by :=`、Python `by: str,` 和字符串里的 `semantic_gate.`，所以内核里 52 个文件对 agent 来说改哪一行都会被拒，`workflow.py`、`delegation.py`、`selfcheck.sh`、`cmd/idev/app.go` 都在内。现在只对 `docs/task/*/`、`.idev/task/*/` 和 `workflow-runs/` 下的 `.yaml` / `.yml` 查签字字段；源码、测试和文档不查；没带路径的写入照旧查。内核里剩下被整份拦的只有 `llm-wiki` 票据的 5 张已签阶段文件。`test_hooks.py` 补 3 条用例，6 个变异全被抓住。人选定：收窄护栏。未提交。

- 2026-10-28：12 张旧基线收进真库。joypaas 8 张、kafka-project 4 张逐张跑 `idev baseline adopt --by wangwei794`，理由「存储上线前已封存，之后未改；wangwei794 在对话里确认由 agent 代跑」。先在真库副本上演练，再写真库；之后密封检查由 FAIL 转 PASS，审计多出 seq 192–203 各一条 `baseline.adopted`，从创世复算 203 条无断。`create-category-pin` 的基线在切换点前没有提交，adopt 拒收，要走闸门重新封。另：gate 通道和 3 个 golden 跟上「交互只为达成同一幅图」后的拒签措辞，拒签行为不变；`claims.py`、`vue-skills.py` 及其测试补上执行位。selfcheck 全绿。人选定：你来执行，确认收这 12 张。未提交。

- 2026-10-28：委派回路收口。遥测：`subagent_stop.py` 每条留痕带 `duration_ms`、`tool_call_count`，宿主没给记 0，`agent-metrics.py` 单列没有遥测的条数；回报的 `SUGGEST` 与 `CONCLUSION` 分字段，`agent-review.sh` 把被 `SUGGEST` 点名两次以上的脚本、agent 或 kind 起草成 `state/proposals/` 草案。真数据要先装 `install-idev-hooks.sh`。审计：Go 引擎每次投影 `run.yaml`，记录变了的步骤逐条写 `step.recorded` / `step.amended` / `step.skipped` / `step.retried`，带结果、证据、签字人、复核人、租约和 `delegation_id`，审计链不读文件也能按步重放。trace：`trace.py append` 从留痕和 `run.yaml` 生成 `round`、`delegations`、`recorded` 三段，一条委派只落进一份 trace；闸门写了标记而 `signoff` 缺失时按记录补上。签字护栏只看结构字段（写入动词、`signoff.marks`、闸门记录、`chose: chat-confirm-signoff`），否定词不再触发；append、check 和周审用同一个函数。真 trace 上周审硬告警由 0 变 3（007、012、030），016、018、027 复核不违规。导体回路：`workflow.py step <id>` 领租约、按 attempt 打出委派包并存档，重试的包带 `prior_failure`；`workflow.py land <id> --report -` 一次做完写留痕、机检、退回和记录。带复核的委派步由 8 条命令降到 3 条，不复核的 2 条。复核租约要在写手回报被接受后才能领，且 30 分钟过期，所以复核那一程另用一条 `land`。BLOCKED 文案的 golden 不变。导体冷启动按 `agent-brief.md` 规定的两页量，现 21,075 字符，在 2.4 万以内；原先按 7 页量出的 47,311 多算了按需页，真实 trace 里它们的打开率是 0% 到 17%。`cold-start-size.py` 打出两页字数和各页打开率，selfcheck 锁 2.4 万上限，本轮不挪内容。钩子装到用户级 `~/.cursor/hooks.json` 与 `~/.claude/settings.json`，原有条目保留。检查只留一套这一项按建议等两周真实数据再定。人选定：按推荐方案；冷启动改口径并加锁、不挪内容；钩子装用户级。未提交。

- 2026-10-28：委派协作收紧。`record PASS` 默认拒绝写手最新留痕里归 agent 的机检 FAIL；确认是检查器误判才用 `--accept-with-findings "<理由>"` 放行，各项和理由写进该步 `accepted_findings`，Go 引擎下另记审计 `delegation.accepted`。复核者的留痕带 `role: verifier`，落成 `<step>-<attempt>.verify.yaml`，挂在写手那次 attempt 上、不占新号，Go 引擎下另记 `verification.recorded`；`next` 打出 `delegate <step> --verify`。`delegation.py eval` 和 `agent-metrics.py` 把逐字节重复的留痕算一份，重试只在同一 run 目录里算，旧扁平目录里 `attempt > 1` 的单列并摘出 `prior_failure`；回报按当前检查器重算，留痕写入检查器版本 `checker`。joypaas code-review 由 14 次委派、10 次重试变为 11 次、0 次重试加 4 条待人判读。`idev baseline adopt` 把存储上线前已在 git 里封存、之后没改过的基线收进库，记 `provenance: legacy-yaml`、`assurance: low`，必须写 `--by` 和 `--reason`。`idev` 二进制只由 `scripts/lib/idev_bin.py` 解析：`IDEV_BIN` 显式优先，`off` 关掉，内核 `bin/idev` 比 Go 源旧就重编；钩子拒绝 agent shell 里的 `IDEV_BIN=off`。selfcheck 以所在的树为根，用临时 `IDEV_DATA`；pytest 经 `conftest.py` 同样封闭，测试不再写进 `~/.idev`。`install-idev-hooks.sh` 按钩子脚本名认自己的条目，不再依赖检出目录叫 `idev`：换了目录名的内核重装不会叠出第二份，卸载也删得掉。人选定：P0 和 P1 一起做；默认拒绝，允许带理由放行并写入审计。

- 2026-10-28：整理存量知识库时，拆掉过时的人读产物，留下审过的需求、规格、密封基线、代码、规约和已晋升经验，再按生成步骤重做。没点名的仓不删。人确认：quote「确认；确认」。本轮未删文件。

- 2026-10-28：Vue 技能收进内核 `skills/vue/`。UI 设计、编码、自测、测试、UI 自动化、根因由 `vue-skills.py` 按阶段打出要打开的 `SKILL.md`；`session-context.py` 在 Vue 仓上打出同样的行。上游是 vuejs-ai/skills。

- 2026-10-28：面向人另交的专业知识文档，先跑该票摄取和校准，退出码非 0 就不生成。正文只写知识库里已有的句子。图用 archify，先校验再交 HTML，不装进内核。需求和规格仍是权威，生成稿不回写。人确认：quote「是；确认；确认」。`llm-wiki` 的 B1–B9 不动。

- 2026-10-28：文档体例改权威。审过的需求和规格是人机同一份，也是权威；规格复述密封基线。方案、测试设计、评审、测试报告进索引只作对照，与这份权威冲突就停。`llm-wiki` 的 B1–B9 不动。人确认：quote「改」。

- 2026-10-28：答完就落笔。`按建议` / `听你的` / 选项号 `a` / `1` / `选a` 就是当前这一步的对齐，不再补第二句。没有未决就不编题。对人只摆方案和证据；`将代写` 留在导体落笔，不念字段名。推翻方案的那一档改方案，不落笔。单独的 `继续` 仍不算。人确认：by wangwei794，quote「确认」，2026-10-28T14:51+08:00。`parse_confirm` 收下。无票、无 A 类闸，不写签字字段。

- 2026-10-28：交互只为达成同一幅图。`可以` / `就这样` / `按这个方案` / `没问题` / `无异议` / `行` 以及「确认，继续」「确认，不用一直询问」都算当前这一步已经对齐。回退和解封用白话点名（`回退到实现`、`打开基线`），不再把 `origin=` 或门短码当验证码。单独的 `继续` / `好` / `ok` 仍然没有说出这幅图。疑问、否定、犹豫、改方案、零宽字符和表情仍然不算。人指出确认不该是答字画押。无票、无新的 A 类字段。

- 2026-10-28：当前这一关的「通过」就是确认。`通过` / `通过了` / `架构通过` / `需求通过` / `实现通过` / `提测通过` / `审核通过` 写入确认文法，Python 与 Go 同一份 `test/signoff/cases.yaml`。人已经这样说了，并且检查过了，就写下这一关。不再回一轮只说明文法不收、字段仍是 false、门仍 pending。基线已经密封就写架构通过。`继续` 仍不算。人指出这类确认毫无意义，应优化掉。无票、无新的 A 类字段。

- 2026-10-28：交互按编制收束。`staffing.py` 从产品名单或 `.idev/staffing.yaml` 认出一个人兼任七岗，还是多人各管一段。一个人把七个视角一次问完；多人只问当前这个人持有的岗位，别人的列成待。判据唯一的既有问题直接写 `scope_debt.decision`。岗位还没写明时只问一次岗位表，写完才签字。`record PASS` 在多人编制下拒绝不在该闸岗位上的人。人确认：by wangwei794，quote「确认，继续」，2026-10-28T13:56+08:00。`parse_confirm` 对这句是 `unparsed-tail`（「继续」不是确认用语）。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-28：架构评审三阶段落地。阶段 0：留痕路径、自检/CI、白名单、AUTO 自跑、产物移出跟踪。阶段 1：客户端钩子、`prompts.log` 核对 quote、计时覆盖率、trace 骨架、结构化回报、`idev run write`+`ProjectRunWithAudit`（Go 默认写 YAML，空 expect 也 stale）。阶段 2：outcome 度量、console 在制品老化、timeline 保留结构化字段、A/B 评测夹具、usage-scan/attic、删除预算与 curator。阶段 3 提案 blocked（要触发条件）。人确认阶段 0–2 各提案原话；未提交。

- 2026-10-27：分析代码的步骤里，更新索引写在读代码之前。审查的 `coding-scan`、根因里的 `codegraph_impact`、需求落地、事实工具箱和结构问题原先都是先读后更新。`scripts/test_codegraph_before_read.py` 锁住这个顺序。

- 2026-10-26：缺的槽位用 `workflow.py param` 写回当前开放步骤。工具登记的 `inputs` 缺了也先 `ASK`。`next` 对照 `recipe_digest` 打出 `DIGEST match|drift|missing`，文件变了不改已展开的步骤。声明了 `react` 的步骤打出 `LOOP` 状态，不挡这一步。分支不能落进一组的中间，也不能跳到已经记完的步骤。

- 2026-10-26：步骤可以声明 `slots` 和向前的 `branch`。缺槽位时 `next` 先 `ASK`，不委派。工具失败走 `on_fail`（`human` / `stop` / `skip`），跳数用尽仍走 `on_exhaust`。`skip` 保持循环开着，不写 inbox。工具可以登记 `inputs` / `outputs`，`next` 打出 `IN` / `OUT`。`show` 回放这一跳的 Thought、Observation 和 `TOOL` 命令。`start` 把配方摘要写入 `recipe_digest`。周审计多计工具跳，并点数未消费的关节失败，不进 `HARD_COUNT`。

- 2026-10-26：运行路径在 hops 一行下面按跳列出「追踪」，带上 `why`、`result` 和耗时，并写出顶层 `react:`。控制台把这条链画出来，时间线单独列出工具跳。不打分。

- 2026-10-26：配方步骤可以写 `tool`、`tool_group` 或 `use`。工具和工具组按 `references/tools.yaml` 的步骤协议展开，一条配方可以引用另一条。`adjust` 能跳过、排序、替换 `label`/`with`/`react`，或追加步骤。`next` 对工具步骤只打出 `TOOL` 命令。

- 2026-10-26：声明了 `react` 的步骤，`next` 打出 `REACT_LOG` 绝对路径和 `REACT_OPEN` 到 `REACT_SHOW`。这些行只打印。本轮 trace 的 `react:` 抄 `REACT_LOG`。同类失败标签满两次，`evolve-review` 算热标签并起草提案，不改 Skill。

- 2026-10-26：ReAct 失败的 inbox note 带上 step、工具名和观察摘要。`next` 打出 `REACT_LOG`。`react_loop.py show --feature` 列出该 feature 的每一跳、成败和耗时。

- 2026-10-26：ReAct 候选必须先登记在 `references/tools.yaml`（`id`、`summary`、`command`）。`workflow-check` 和 `react_loop.py open` 拒绝未登记的名字。`act` 打出该工具的 `TOOL` 命令。登记本身不执行命令。

- 2026-10-26：配方步骤可以声明 `react` 关节。循环只在候选工具里走，用尽或工具失败走 `human` 或 `stop`，并把每一跳写入当轮 trace。反馈进 inbox，不自动改配方。没声明的步骤行为不变。人确认：by wangwei794，quote「确认」，2026-10-26T11:28+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：规范插件不再把正确写法报成违规。`===` / `!==` 不算 `==` / `!=`。`try (` 里后面的资源不算漏收的流。Shell 只报会分词的未加引号变量，引号、命令替换里的引号、heredoc、`[[ ]]`、`$(( ))` 不算。Go 不再用正则猜被丢掉的返回值。闸门读标准输入失败时把错误返回去，不再当成空回答。人确认：by wangwei794，quote「确认」，2026-10-25T20:28+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：前置节只要列出既有问题就问人，选项是先修或本次不修。小于本需求改动的 1/5 或边界分得开，只写进 `scope_debt.recommend: mark`，不代替人的选择。一条都没有才直接 `mark`。仍是 B 类决策，不增加第五次签字。人确认：by wangwei794，quote「确认」，2026-10-25T16:09+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：架构方案在六节之前写 `## 前置`。先审影响范围内已经存在的问题。没有重大缺陷，并且规范与质量改动小于本需求改动的 1/5，或者和本次改动分得开，就只在方案里标明，不另开子需求。有重大缺陷，或比例达到 1/5 且分不开，先问人要不要先修；同意则另开缺陷修复或重构子需求，从头做完再实施本需求。不新增机检，不增加第五次签字。判据只在 `deliver/SKILL.md` 的架构阶段。人确认：by wangwei794，quote「确认」，2026-10-25T15:55+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：Python、Go、Shell、JS/Vue 规范扫描只依赖 `scripts/plugin/` 里的 `python_inspect.py`、`go_inspect.py`、`shell_inspect.py`、`js_inspect.py`。`coding-scan.sh` 调用 `lang-scan.sh`。不安装 ruff、golangci-lint、shellcheck、eslint 或 Node，也不下载。插件不在时退出码 2，是 `UNPROVEN`。`python3 -m compileall` 的 0 不是这层扫完。
- 2026-10-25：Java 规范扫描只依赖 `scripts/plugin/java_inspect.py`。`problems-scan.sh` 不再安装 IntelliJ，也不安装 JDK。插件看未收进 `try (` 的流、没有调用的私有方法，以及至少两处调用都是同一字面量的私有形参。插件不在时退出码 2，是 `UNPROVEN`。
- 2026-10-25：编码和 Review 的 Java 规范扫描加上 Qodana。`coding-scan.sh` 调用 `problems-scan.sh`：本机已有 CLI 和检查插件就用；没有就远程安装到 `$HOME/.cache/idev/qodana`；没有网络就用 `offline/qodana`。插件不可用时仍用本机 IntelliJ `idea-inspect.sh`。两个引擎都没有报告是 `UNPROVEN`，不是扫干净。二进制不进 git。

- 2026-10-25：编码和 Review 的 Java 规范扫描由 `coding-scan.sh` 调起 `idea-inspect.sh`。它用本机已安装的 IntelliJ（`IDEA_HOME` 或本机 Applications / Toolbox），profile 名 `Project Default`，不下载，不改 `idea.plugins.path`。没有安装时退出码 2，输出 `UNPROVEN`。`java_hygiene.py` 的 0 仍然不是 Problems 已空。易受攻击的依赖项只计数，不作为这次失败。

- 2026-10-25：架构方案和编码补上码如文字、最小实现。定义仍在 `coding.md` 底线 4、5，已确认的前三条不改。方案和代码顺着读要能指出重点；注释只写代码看不出的为什么。用最少的代码实现目标，只权衡这一轮碰到的性能、并发安全、易使用、易扩展，无基线不优化。文件数和行数说不出换来什么就是膨胀。只有 get/set、没有业务信息的哑对象是拒过；协议形状可以只有字段。`design.md` 方案节和 A1 要答到这一点。不另起编号，不新增机检。人确认：by wangwei794，quote「确认」，2026-10-25T14:35+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：`java_hygiene.py` 报 blocking 0 不能当成 Problems 已空。它只覆盖正则能判定的子集。验收以 IntelliJ「Project Default」对改动模块的 `inspect.sh`（或同一配置下的 Problems）为准。try-with-resources、形参恒定、非 getter 的未使用方法、拼写不在这套正则里。

- 2026-10-25：编码和 Review 守住文首底线三条，定义只在 `coding.md`。大道至简：不把问题做成框架或分层；关键路径（失败会让基线结果错或没有）当轮写失败条件、怎么停或怎么降、日志，其它路径不加 catch / 默认值 / 重试。易用性：人能看出入口和失败时怎样；扩展沿现有类型和契约加，不改已有分支的含义，也不为以后预埋钩子。禁止随意发挥：每段新代码要指得出依据（基线、本轮那句话、第三次重复、或已经看到的失败），指不出就删。命中仍落 `T#`/`C#`/`P#`/`F#`，不另起编号，不新增机检。`idev-coder` 写前过，`idev-reviewer` 先于总则写成 `I*`。人确认：by wangwei794，quote「确认」，2026-10-25T14:15+08:00。无票、无 A 类闸，不写 `sealed` / `accepted` / `aligned`。

- 2026-10-25：`TaskStore` 的 Problems 仍在时，审查不能报 blocking 0。blocking 补上 `Collections.sort` → `List.sort`、`(a, b) -> a.f.compareTo(b.f)` → `Comparator.comparing`、循环里的 `Thread.sleep`、40 行内相同的日志句子。间隔等待改 `TimeUnit.MILLISECONDS.sleep`。没人用的返回值改 `void`，没人调用的方法删掉。

- 2026-10-25：`TaskExecutor` 的 Problems 仍在时，审查不能报 blocking 0。`Collections.<K, V>emptyMap()` 这类「可以推断」改为 blocking。`src/main` 里简单 getter 没有生产调用记「方法从未使用」（只在测试里调用也算未使用）；模块 pom 已有 Lombok 时，仍被生产调用的 `return field` 记「可以具有 Lombok @Getter」。`Collectors.<T>toList()` 仍是 note。

- 2026-10-25：代码审查先清 java.md 里能机检的黄条，再写内聚和设计模式。`scripts/lib/java_hygiene.py` 扫分支 diff。blocking 是构造上的显式类型参数（`new ArrayList<String>()` → `<>`）、`valueOf`、compiler=8 的 `List.of`；匿名类在 compiler=8 不报。`Collectors.<T>toList()` 只作 note，Java 8 经常推断不出来，不打回。`coding-scan.sh` 会打出这些行。`review.report` 漏记 blocking 的 `file:line`、以及 `code_pass` / `review.fix` 把 blocking 留在 `CHANGED` 里，`delegation.py` 的 `java-hygiene` 打回。不新编号。

- 2026-10-25：五个执行者都能沿交付链读上游的尺和下游的后果，落笔仍只在自己的 kind。本领域以拒过清单为下限。指导别的角色只经导体：回报 `GUIDE` 由导体抄进下一委派包；`BLOCKED(domain)` 才另派一次咨询，不问人，咨询不套娃。`SUGGEST` 仍只说本定义哪一步含糊。`delegation.py write` 把抄约束、咨询、打回打成 `HANDOFF` / `CONSULT` / `REBRIEF`，导体照着做。

- 2026-10-24：中控台加上计量和定向调整。计量把最近窗口的场景、执行者耗时、观察覆盖、回报、技能调起和假设摊成件数，不打分、不设阈值。点某一格，依据写进意见。意见分改关口、改这一步、补观测、质疑基线，仍进 console 线程，下一轮由导体读取。页面不派工、不签字。

- 2026-10-24：分片草稿已经在磁盘上时，`fanout.py assess` 打出 `MERGE`，清单仍保留每一片。不再只留下还没写完的那一片，也不再派一个执行者去重写 `review.md` 或 `plan.yaml`。已经签收的 `review.md` 不会被合并盖掉。

- 2026-10-24：审查和用例起草可以按片派。`review.report` 在写集不是单独一份 `review.md` 时，按改动的顶层模块分片深读，机械扫描仍是一条 `coding-scan.sh`。`verify.plan` 在还没有两条 `case_intent` 时，按已签收的 `I*` 分片，每片只写自己的 shard 和 `verify/checks/<I*>/`。`FANOUT` 时 `delegate <step> --shard <id>` 发的验证租约只覆盖该片路径，不再放大成整棵票目录。留痕落到 `delegations/<run_id>/`，新的一轮不再撞上旧的 `report-1.yaml`。`review.fix` 仍是一个执行者。

- 2026-10-24：外挂 Skill `~/.cursor/skills/super-linter`（包装 upstream Super-Linter）。仓内已有 workflow/env 时由 `coding-scan.sh` 打印 Skill 路径并走本地工具映射；不默认拉镜像。人明确要求容器跑时按 Skill 钉 `v9.0.0`。`link-companion-skills.sh` 可显式链 `super-linter`。命中仍译 P#/C#。
- 2026-10-24：中控台。`python3 scripts/console.py` 在本机打开一页，看各 agent、耗时、skill 调起和详情，并可下达任务、对话。数据仍是 trace、委派留痕、`run.yaml` 和假设台账。页面上的话进 console 目录的线程，导体下一轮读取并回复。派工前记一条进行中，回报后清掉。控制台不签字、不派 agent。

- 2026-10-24：自测、用例设计、用例执行、根因可以按需拆成多个 agent。`fanout.py assess` 先看工作是不是彼此独立：少于两片、写集相交、或同一个 Maven 模块没有 `runner.parallel: true`，就保持一个 agent。`FANOUT` 时同一条消息派每个分片，分片只写自己的路径，导体 `merge` 后这一步只 `record` 一次。仍是一份 run。`verify.plan` / `verify.run` 的 `next` 会打出 `FANOUT_ASSESS`。
- 2026-10-24：波次打开时给票目录留哈希，组外的新文件 `record` 拒绝。`delegate --open` 一次委派当前波的每个 agent 步骤。`steps` 投影带上 `group_id` 和 `writes_json`，读回来的 run 用 `Open`。`design.md` 六节、`case_intent` 和报告只索引进了 `check-feature`。配置了 super-linter 时 `coding-scan.sh` 跑本机已有的对应工具，不下载。
- 2026-10-24：`review.fix` 之后增加 `refresh`，把 case status 回写 `verify/plan.yaml`，并重写 `selftest.md` 和 `accept.md`。带 `writes` 的步骤若已有委派，回报必须有 `CHANGED`，写出清单之外的路径则 `record` 拒绝。Go 的 `Run.Open` 让同一 group 的步骤可以一起激活，组后面的步骤仍要等组内全部完成。
- 2026-10-24：`lite-change` 在编码之后把用例、自测、独立审查、验收索引放进同一个 `group: check`，写集分别是 `verify/plan.yaml`、`verify/selftest.md`、`review.md`、`verify/accept.md`。`next` 打出 `PARALLEL`，`record` 和 `delegate` 接受组内任一未完成步骤。人闸和写租约留在组外，审查修改和实现审核仍在这一波之后。
- 2026-10-24：五份文档收成同一体例；编码完成前必须由审查者写编码规范节；扩展配置的每个键有解释和示例。需求、设计、用例、Review、测试报告同一事实只写一处，人读和机读对同一批 id（`docs/SKILL.md`）。`lite-change` 在实现审核前增加 `review.report` 与 `review.fix`（`accept_all_findings`），不另设人闸。`review.md` 要有 `审查者: idev-reviewer` 和带数字的 `文件与行数`。§2.4 补单文件 400 行、新增文件、触及文件。规范扫描跑仓内已有的那一套（super-linter 是例子，不新装）。`references/extension-config.md` 解释 marker / extensions / workflow-defaults 的每个键并给示例；`config-doc-check.py` 对一下内核真的去读的键。

- 2026-10-23：trace 补四层可选观察，给减负和 shortcut 用，不新增门禁。技能调起写 `invoke.how` / `invoke.skills[]`；委派决定写 `decisions.kind: delegate`（`none` 表示导体自己做）；模型与一行思考写 `kind: model` 和 `calls.thinking`；组件从哪跳到哪写 `calls.from` / `calls.to`。运行路径多 `skills` / `choices` / `hops` 三行，空着是 `(none)`。`path-stats` 与周审计各加一组计数（技能入口、委派、模型、组件跳），不进 `HARD_COUNT`，也不进必须清零。旧痕迹不用回填。

- 2026-10-23：交付主路径收成四次人确认。需求把不明确的问题一轮问完（可多轮），回答不是签字，每个档位在拆解末一次写密封和拆解通过。架构先交整包方案等人 Review，有分叉才拷问，此阶段不交用例。通过后连续做用例、编码、自测，计划无信号则自动过。自测完成后停一次实现审核，然后提测，最后只确认测试结果。promote、推送、解封、回退、经验入库不动。提案 `state/proposals/20261023-fewer-signoffs.md`。

- 2026-10-22：code-review 真票全程闭环（joypaas，run 01M5F7EKCQ1EK4M5ANY5CRQF70 done：report→gate-report（chat 通道人签）→plan（5 selftest case，verify-plan 门禁 0 FAIL）→gate-plan（P1 AUTO）→fix（两轮委派+reviewer 独立复核，894/0/0/3）→run（5/5 PASS））沉淀三件，两件当轮落地、一件立稿待审：① **delegation 留痕 YAML 折叠吞换行（已修）**——`delegation.py write` 落盘 `report.raw` 经 `yaml.safe_dump` 单引号折叠把多行回报压成一行，行锚定机检（FACTS/DOC_DRIFT/SCOPE/RED_FIRST/ASSUMED/S0）全部失明并误标 agent 责任；新增 `scripts/lib/yaml_representers.py`（LiteralString + 块标量 representer），落盘改走 `yaml_representers.dump`，换行保真；端到端验收：合成多行 raw 落痕 RC=0 零 FAIL，golden 50 same、selfcheck/syntax/refs/agents-check 全绿。② **方法名锚点惯例（已落）**——I1/I3 行号在 review 与 fix 之间漂移（101→122、1893→1669），两轮委派靠「方法名+第 N 个该构造」才定位成功；`idev-coder.md` 的 CHANGED 字段、`idev-reviewer.md` 硬规则 6、`workflow-code-review.md` 的 I* 位置字段统一改为 file:方法名 锚点为主、行号辅助。③ **selector 断言对应（已落）**——I1 的 plan selector 指向配置绑定侧测试（38 例但不断言 validateMapped），真正断言在 BudgetRecognizerTest；`idev-verifier.md` plan 骨架节补「selector 必须指向含该 case assert 语句的测试类」。提案稿 `state/proposals/20261022-delegation-raw-folding.md`（status: draft）记录全过程证据链。

- 2026-10-22：存活探测不再指向全量 `healthcheck` / `agent-smoke`。这两份和四条套件一样，`block_until_ms` 大于 30000 记 `suite_block`。存活是一行不调用工具的回复。

- 2026-10-22：selfcheck、golden record、gate-channel、lease-channel 的 `block_until_ms` 大于 30000 时，`turn-budget.py` 记 `suite_block` 并失败。先说一句再把这四条套件等到结束，不再放过。`block_until_ms` 为 0 的后台启动通过。其它长命令仍只要先开口。

- 2026-10-22：回合预算的机检补上已经写进 Skill、但脚本没判的三条。先开口再连续 9 个无正文回合会失败；`block_until_ms` 大于 30000 且这一条和上一条都没有正文会失败；命令里的 `claude -p` / `agent -p` 会失败。先说一句再跑长命令仍然通过。结构问题用 `codegraph_context` 仍是做法，不进脚本。

- 2026-10-22：回合预算落地（提案 `state/proposals/20261022-agent-turn-budget.md`）。聊天里长命令先说一句再放后台，连续 8 个无正文工具回合先报现状，存活探测不再用 `claude -p` / `agent -p`。`scripts/turn-budget.py` 只数第一句正文之前的无正文回合，红夹具 9 失败、绿夹具一行 `ALIVE` 通过，`selfcheck` 跑这两份夹具。不并行多开执行者，不改迁移跳过和租约时长。

- 2026-10-21：签字改成聊天确认。人回复 `确认` / `同意` / `全签` / `LGTM` 即认可当前停问点，导体 `record PASS --by --quote` 落笔；终端 `idev gate approve` 仍可用，不再是必经。密封、架构、提测在每个档位仍各要一次确认。同日先把 P1/P2 架构关改成机检通过即过，人补了一句「架构方案还需要我签」，该条撤回。E1.2（把生命周期闸改成终端批准）否决。

- 2026-10-21：代码审查对规范显式成文。`coding.md` 文首新增**规范总则**五条（控制膨胀 / 高内聚低耦合 / 条件链先上模式 / 语法糖优先 / 复杂度有界），编码侧补「写完回扫本轮 diff」一步、Review 侧在最前补「先扫总则」一步（六步变七步，`idev-reviewer.md` 展开同步）。`coding-tables.md` §2.4 量化阈值补两行**变更级**粗筛（净增行数说得出换来什么 → T1/C3/C6；单文件变更理由 = 1 → C12/C1），与函数级五行同表同判定；§1 P5「运用」列补按栈语法糖一句（Java 多例 SPI / 经典 switch；Go 表驱动；Vue/TS 对象查表 + computed）。克制：命中一律落既有 `P#`/`C#`/`T#`，不新增报告字段与机检——`check-feature.py` / `test_review_coding.py` / golden / agent-smoke 零改动，`review.example.md` 编码规范节字段不变（仅说明行点出总则同扫）。

- 2026-10-21：`start` 不再把「没有 steps」或读坏的 `run.yaml` 当成没有进行中的 run 去覆盖。`record` / `abort` 在 `run.yaml` 写成功之后才更新 `report.md`，避免报告跑在 run 前面。`decisions.yaml` 里有一条不是 mapping 的记录时，`decide` 拒绝再追加。

- 2026-10-21：两个 `start` 不再各自写一份 run 再互相覆盖；检查和写入在同一把锁里，已有进行中的 run 就拒绝。同一个 signal 在同一次 attempt 上只接受一个 `decide`，第二次会和第一次矛盾，直接拒绝。

- 2026-10-21：`ask` / `record` 不再占着 `run.yaml` 的锁去跑 `idev`。问已经写入 SQLite、编号没落进 run 时，再次 `ask` 写回已有的 pending 编号（冲突信息里带这个编号；落盘失败则留在 `gate-<step>.id`），不开第二问，也不会把人卡在没有编号的 pending 上。已批准且内容未变时不再另开一问。

- 2026-10-21：大规模并发下两处会失真的检查。`idev` 每次打开数据文件都跑 goose.Up，即使 schema 已是当前版本也会占写锁，一群 gate/lease 查询会排在一次空迁移后面；已记录版本不低于内嵌迁移时改为只读版本号，落后的库仍会补迁移。`deliver.code_pass` 这类独立复核原来只核对 `--verified-by` 和 `--verify-evidence` 两个字符串，报告可以不存在；现在报告必须是非空文件，且 `delegations/` 里要有复核者自己的留痕用整词引用该路径，执行者的留痕不算。空文件和缺失文件分开拒绝。

- 2026-10-21：需求签收后的方案评审要交齐三份，并经 grilling。`check-feature` 在 `arch` / `code` / `test` 要求 `design.md` 六节（目标照抄基线 goal，点名每条 item 与 case_intent）、`grill.md` 的 `## arch` 轮闭合（`arch_frontier: empty`，`arch_shared_understanding: true`），以及 `verify/plan.yaml` 与 `case_intents` 按 slice / item / dimension 一一对应。`verify-plan` 也查这组对应。编码阶段补 runner，不另起用例。

- 2026-10-20：销 N1（设计 v3 的 `IDEV_ROOT` 与术语表冲突）。设计文首（版本块末）补术语注记：本文是 idevd 落地后的目标态，`IDEV_ROOT`（默认 `~/.idev`）指唯一配置根；迁移完成前以 [glossary.md](glossary.md) 的两个词为准——`IDEV_ROOT` = 内核 checkout（`~/.cursor/skills/idev`）、`IDEV_DATA` = Go CLI 数据根（默认 `~/.idev`）。设计文件 SHA-256 `7672a259…9824fea0` → `7db523d4…974fcbde`，README「Go 核心」段同步；agents-todo 验收段保留验收时点值并注明当前值；N1 行按「做完即删」移除（其完成判据即文首注记）。同笔并入当日 README / agents-todo 验收状态对齐：lease-channel 17 例与 verify 租约围栏描述、`go test -race` 注释（domain 零 IO；app 与 sqlite 同测）、停问步说明改「先 `ask`，人在自己的终端 `idev gate approve`，再 `record PASS`（不带 `--by`/`--quote`）；`IDEV_ENGINE=python` 才回到人名加确认原话」。

- 2026-10-20：修 go 引擎下 verify 租约从不生效的安全缺口。`kinds.yaml` 声明 `lease: verify` 的 kind（verify.run 等，执行者只许写票内验证产物）在 `workflow.py` 只对 `lease: write` 走租约围栏，verify 类从不取租约、record 也不校验——Go CLI 的 `--purpose verify --ticket-dir` 早已支持（ticketDir 必须搭配 --purpose verify，且自动把 `ticketDir/**` 并入 WritePaths），缺的只是 Python 驱动接线。TDD 先红后绿：`needs_write_lease` 重构为 `lease_purpose()`（write/verify/None），新增 `ticket_dir_repo_relative()`（票目录不在 git 仓内直接 Blocked）；`delegate` 的 verify 分支以 `--purpose verify --ticket-dir` 取租约（打印 `LEASE … fencing=N … paths <ticket>/**`）；`record` 对 verify 类 PASS 无租约拒绝、改动越出票目录拒绝并要求 revert；write 类两套文案与行为原样保留。lease-channel 断言 13→17（无租约拒绝 / 围栏限票目录 / 越界拒绝 / 票内释放后 RUN DONE，rival fencing 断言 2→3），红态 12 OK 5 FAIL 形态与预测一致；回归 gate-channel 14 OK 0 FAIL、golden 50 same 0 different、selfcheck PASS。

- 2026-10-20：agents-todo #7 首段（真票 joypaas 跑 code-review 配方）跑到 `report` 步 PASS，停 `gate-report` 等人签收（run `01M5A5RVBC2K2GGP1K6ETSJESM`，gate `01M5A86FX2GB614BK2TGF80DV6`）。异步委派全程留痕（delegations/report-1.yaml），五项诚实性检查全过——其中查证闭环了 review 窗口内新出现的 CONTEXT.md/ADR-0009：三重转录扫描证明是用户平行设计会话的产物而非 agent 所写，reviewer「本步未动」声明属实。审查产出 208 行 review.md：9 I* / 7 O* / 3 UNPROVEN，canon §7 命中 T3/T7/T8/T10+T11/F4，五轴齐写；正向记录（SSRF 双重校验、文案泄漏过滤、token 不入日志）与 UNPROVEN（mvn/qodana 未跑、前端 lint 未跑）都如实区分。两个环境坑记录在案：裸 prompt 会被宿主 CLI 内置技能截胡、须 `/idev` 前缀唤起；后台任务 600s 上限须设 `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`。首轮唯一 SUGGEST 是脚本问题而非 prompt 措辞问题（对 #8 是正向信号）。同日修 `coding-scan.sh` 五处管道缺陷：`set -o pipefail` 下 `find | head` 的早期退出把 SIGPIPE（exit 141）传死整脚本——package.json / pom.xml / go.mod 三处探测加 `node_modules -prune`（顺带消除 node_modules 里 package.json 的误报）、package.json 探测删掉无消费者的 `head -5`；Boot 版本回退探测原 `grep -Rqs … | head -1 | grep -q .` 因 `-q` 无输出恒为假（死代码），改为对根 pom 直接 `grep -qs`；checkstyle 探测原 `find | xargs grep -l | head -3 | grep -q .` 在 ≥2 匹配时同样 SIGPIPE→恒假，改为 `find … -exec grep -l … {} +` 落变量判空。修复后 joypaas 全程 exit=0（java=1 level=8 / vue=1（docs/prototype 真实依赖）/ go=0 / ts=0，node_modules 误报消失）、合成用例与 idev 自身均过，syntax-check / refs-check / selfcheck 回归全绿。

- 2026-10-19：补上 Claude Code 的 skill 安装缺口。契约（[agents.md](agents.md)）要求 skill 装在 `~/.claude/skills/idev`，但 `link-idev-aliases.sh` 只建了 `~/.agents` 与 `~/.joycode` 两条别名——而 Claude Code（v2.1.287 实测）只从 `~/.claude/skills` 读用户级 skill，`/idev` 在那边完全不可见。补建别名后：skill 列表 4→5、5 个 agent 全可见、debug 无 skip、`/idev status` 真实唤起并落 trace `20261019-001`。`healthcheck` 标签同步更新；README / SKILL.md / portability-checklist 的别名链补上 `~/.claude`。已知遗留：Claude Code 技能列表超预算（17 个 7832 字符 > 6000，description 被截断），但不影响本次命中——同日实测不打 `/idev`、直接说交付诉求即自动唤起（S1 冷启动、停问等人），trace `20261019-002` 落盘；若后续命中率不稳，调法在用户级 settings 的 `skillListingBudgetFraction`，本仓不动（agents-todo #5 有备注）。

- 2026-10-19：agents-todo #6（P0「签名归一化在自己栈上」）验证完成并销项。用 joypaas 真实服务器日志喂 `failure_signature.py sig`：同错（同线程 `exec-1`、不同时间戳）签名相同，时间戳剥为 `<ts>`；不同错（中文无异常类名的登录失败行 vs `UnknownHostException` 块）签名不同——验收两项均过。边界发现：线程名（`http-nio-8099-exec-N`）不在 VOLATILE 归一化表，同 bug 跨线程分裂签名，「同签名 3 次」红线在服务器日志上难触发。按该待办告诫只记录不修（归一化刻意保守，防止反向把不同 bug 合并）；服务器日志上跑 bounded-fix 时喂同一处线程的行，真需要时再议线程名剥离。

- 2026-10-13：修两处「永远红」的既有检查。`healthcheck` 与 `link-idev-aliases.sh` 都硬性要求 `~/.cursor/skills/idev` 是真目录，而本机拓扑是「git 仓是真源、那里是 symlink」——于是 healthcheck 恒定 FAIL，等于一个没法用的健康检查，新问题会被淹没。「真源」的意图是**只有一份内容**，不是「这个路径必须是真目录」，而版本化的 checkout 是更好的形态。改为接受两种形态，并把「物理根必须等于真源」从字符串比较改成物理路径比较（否则 symlink 必然被读成第二份副本）。`link-idev-aliases.sh` 内部本来就用 `pwd -P` 比对别名，只是前置检查拦住了。另：`selfcheck` 的 trace sink 锁同理已修。

- 2026-10-13：agent 层合并进内核，idev 成为一整套。新增 `agents/`（五个执行者：deliver / coder / reviewer / verifier / ops，按生命周期阶段与模块归并）与 `kind → agent` 登记表 `scripts/lib/kind_agents.py`；`workflow.py next` 原生多打一行 `DELEGATE`，`trace.py` 的 `calls[].kind` 增 `agent`。导体（`/idev` skill）独占签字权与人交互，执行者是 subagent——`is_human()` 的黑名单本就含 `agent/ai/cursor/assistant`，所以这条分工是代码级的，不是约定。新增委派留痕与五项诚实性检查（`delegation.py`）、跨票指标与复盘（`agent-metrics.py` / `agent-review.sh`，只起草不 land）、提效三板斧（`failure_signature.py` 签名归一化让 evidence.md 的三条红线判得出来、`hypothesis.py` 假设台账、coding.md §0 三项交代可机检）。自检三道：`syntax-check.sh` / `agents-check.py` / `agent-smoke.sh`（143 条）。顺手修两处内核既有问题：`selfcheck.sh` 的 trace sink 锁死路径含 `.cursor/skills/idev`，而 `kernel_root()` 用 `resolve()` 必然得到物理路径，该锁在 symlink 拓扑下永远不通过；复制进来的脚本补执行位。`cohesion.md` 加 `agents` 登记并论证它不是第二个顶层 Skill（subagent 名与 skill 名不同命名空间，入口仍只有 `idev`）。


- 2026-10-01：P6 综合缺陷修复。`aligned`/`done` 须人名 `by`；`check-feature` FAIL 打 HINT；`late-lifecycle-smoke`（test→promote→ops→拒伪造 aligned）与 `second-product-smoke` 挂入 healthcheck；audit 软信号 S1 未开 grilling；curator 14d→stale、30d→archive，evolve-review 把超龄 draft 当硬信号；agent-brief 钉死两页冷启动；三模块 SKILL 顶加「本阶段 5 步」；Linux systemd/cron 模板。真实产品票 `done` 仍须人确认（不伪造）。

- 2026-09-30：workflow 补齐三件套。编排语法的代码形态收进 `scripts/lib/workflow_spec.py`（kind 与落点、顶栏 / 参数 / 策略取值、配方与 run 校验），`workflow-check` 改用它，并开始拒绝未知字段、非法 `from` / `policy` / `risk_tier`。新增驱动器 `scripts/workflow.py`（`resolve` / `start` / `next` / `record` / `status` / `abort`）：按配方写 `run.yaml`，给出下一步与落点页，守跳步、签字原话、失败即停，不替 Agent 执行步骤。无票运行落 `product_sink.py workflow-runs`。自检锁住文档 kind 表与代码一致和驱动规则。`workflow-check` 对齐驱动器：产品配方从扩展根读；产品可有多条配方，但一个 id 或别名只许指向一条生效配方；`--run` 核对步骤与所记配方一致。配方校验时停问步骤必须声明 `with.will_write`（`[]` = 将代写: 无）或在 `label` 写 `将代写`，驱动器 `next` 打印该行。

- 2026-09-30：自检与健康检查各用一个本轮独占的临时目录，不再写死 `/tmp/idev-*`，两份并发不互相覆盖；macOS 下带后缀的 `mktemp` 模板去掉。产线在 `AGENTS.md` 或 `issue-tracker.md` 声明 `docs/specs/` 时，规格目录用复数，两份同在时并入复数那份。巡检包、测试设计、`current.md` 的执行页一律指向 `doc_home.py --key`。lite-change 烟测改在本会话 trace 目录找小改记录。配方新增可选 `doc`，`session-context --workflow` 列成 `OPEN`；UI 全量、UI 建设、启停三页执行说明移到产品仓 `.idev/pack/references/`，内核不再点名产品配方 id。

- 2026-09-30：`session-context.py` 等 5 个带 shebang 的 Python 入口补执行位，自检改为凡有 shebang 的脚本都须可执行。`evidence.md` 收尾不再写死 `docs/debt/`，未修的同类缺陷在当前票目录另开 issue。`verify/references/evolve.md` 去掉「模块实验台账」说法，与只有入口台账一致。周审计不再把内核 `state/traces/` 的导体会话记为未绑票。删掉无人调用的兼容壳 `pin-summary-check.sh`。`docs/SKILL.md` 的票目录文件改为指向各模块契约，不再只列五个。`workflow-schema.md` 不再说「不是第五模块」。

- 2026-09-30：健康检查把 lite-change 的 `WARN` 计入 `warns`。path-view 与自进化检查分开，缺进化脚本时仍检查路径视图。`coding.md` 快捷表去掉平台默认值和账本用语，与全表一致。

- 2026-09-29：票路径只认 `doc_home.py`。进入阶段跑 `session-context.py`，S8 同时列出 `s8` 和当前交付阶段；点名的产品用 `--product`。产品仓 trace 必须写 `extensions`。第一次保存放行 `.idev/task/` 与 `.idev/docs/`。缺 `evolve` 不当成试点。内核入口只列内核配方 id。

- 2026-09-29：`from: product` 与启停命令读扩展根的 `workflow-defaults.yaml`。文件或键缺失时 `s8-preflight` BLOCKED。执行模块写票路径时先跑 `doc_home.py`。

- 2026-09-30：产线文档以技能接入交付。写文档、S1 落票、S5 回填和 `docs.backfill` / `docs.changelog` 打开 `docs/SKILL.md`。目录仍认 setup-agents-docs，问句仍认 grilling。`link-companion-skills.sh` 同时挂上这两份同伴技能。

- 2026-09-29：产线文档目录认 setup-agents-docs（Matt Pocock），问句认 grilling。idev 不另定一套。已有这两套时归入 `docs/`，冲突时规范文档优先。还没有时阶段状态写 `.idev/task/`，不新建仓库根的 `docs/`。

- 2026-09-29：文件规范收成一份，写在 `conventions/docs.md`。

- 2026-09-29：`docs/spec/<feature>.md` 与 `docs/specs/<feature>.md` 同时在时，以 `docs/spec/` 为准。另一份里还没有的正文先并入，然后删除 `docs/specs/` 那份。只有旧路径时仍读旧路径。

- 2026-09-29：同一文件同时在规范目录 `docs/` 和 `.idev/` 时，规范文档优先，`.idev` 副本不覆盖它。只存在于一边的票仍留在那边。

- 2026-09-29：产线文档先认 Matt Pocock（setup-agents-docs）和 grilling。两套都在时，新文档和阶段状态按 `docs/prd`、`docs/spec`、`docs/test-case`、`docs/task` 归类。缺一套时改放到 `.idev/docs/` 与 `.idev/task/`。已有的票留在原树。解析在 `scripts/lib/doc_home.py`。

- 2026-09-29：交付仓用自己的 `marker`。共用类页写相对路径 `extension_root`。阶段页可按 `products` 过滤。`check-feature` 跑带阶段声明的产品检查。要不要票只认配方 `needs_ticket`。剥离词表改到各仓 `.idev/strip-tokens.txt`。第一次保存写下空的阶段清单、检查目录和保留 `memory.md` 的 gitignore。
- 2026-09-29：产线 `.idev` 自动整理。热集合留最新 20 条 trace、最近复盘、未消费 inbox、仍打开的提案。被自进化点名满 2 次，或满 3 代，先写入纳入版本库的 `.idev/memory.md`，再删过时原件。真实复盘结束时自动执行。产品 `.gitignore` 需保留 `!.idev/memory.md`。

- 2026-09-29：产品仓文件合同写在 `conventions/docs.md`。密封基线要有一份人读规格，`grill.md` 的字段行只能各有一行，问句必须是 `❓ **Q1** - **标题**:` 配 `➡️`。`review_questions` 保持空。

- 2026-09-29：`sealed: true` 必须有 `grill.md`。`convention` / `frontier` / `shared_understanding` 各自单独成行，正文要有 grilling 的 `❓` 与 `➡️`。散文里提到这两句不算关闭。YAML 里残留的 `status: open` 不会被关闭的 `grill.md` 盖掉。编码评审、checklist 记录、执行残留分三处，清理只删 `.idev/reviews/`。

- 2026-09-29：产线文档目录认 setup-agents-docs（`docs/spec/<feature>.md`，不再用 `docs/specs/`）。未决问题写 `docs/task/<feature>/grill.md`，问法认 grilling。有这份文件时，基线 `sealed: true` 要求 frontier 已空且人已确认共享理解。

- 2026-09-29：产线 `.idev` 的重点是执行阶段产物（trace、复盘、inbox），给定自进化参考。`docs/task/` 仍是交付票。`execution-clean.sh` 默认预览，`--apply` 才删超窗残留；不删提案、不删产线特性和交付票。

- 2026-09-29：阶段读取产线页。有 `marker: idev` 时，`stage-extensions.py` 按 `.idev/extensions.yaml` 列出该阶段要打开的文件；`check-feature` 会跑它。产品自己的检查放在 `.idev/checks/`。第一次保存中间态时写下 `marker`（`evolve: false`），已有标记不改写。启停和 UI 命令改从 `workflow-defaults.yaml` 的 `commands` 读取。自检不再要求某一产线必须有 `coding_root` 或 `ui-automation-build.yaml`。

- 2026-09-29：使用说明写入产线文档默认路径。目录认 setup-agents-docs，未决问题的问句认 grilling，两边同一 `<feature>` 路径。

- 2026-09-29：使用说明写在 `references/guide.md`（目标、架构、产线边界、一次交付与后续会话怎么接）。路由、认票、边界细则仍各认原权威页。

- 2026-09-29：`.idev/` 由 idev 在产线交付中写入。idev 识别产线侧特性，需要保存状态时持久化到该工程 `.idev/`，后续会话再读。人不用先建这个目录。

- 2026-09-29：入口对齐边界。交出口要先有 `marker: idev` 才读 `handoff.yaml`。产品会话的 inbox / 提案草稿进该工程 `.idev/`；内核 `verify/state/` 只留给没有当前产品的导体会话。

- 2026-09-29：边界拆分。产品使用 idev 时先激活内核。内核需要的中间态和产品特性都放在该工程 `.idev/`（`marker.yaml` 的 `marker: idev`）。自净化用这个标识发现 `evolve: pilot` 的仓，复盘计数进内核收据，正文留在该仓。

- 2026-09-29：产线退出内核。当前产品的类页、交出口名单在该仓 `.idev/pack/` 与 `.idev/handoff.yaml`。内核 `handoffs/registry.yaml` 的 `packs` 为空。编排器不再内置产品名。编码表去掉某一产品的类名列。

- 2026-09-29：流水线产物归当前产品。为产品构建的配方在该仓 `.idev/workflows/`，参数在 `.idev/workflow-defaults.yaml`（`from: product`）。idev 只留编排契约、kind 表、`workflow-check`，以及不绑产品布局的能力配方。

- 2026-09-29：去掉未点名产品时的 JoyPaaS 运行默认。`pack-link` / `link-outbound-skills.sh` 没有 `--pack` 且本机没有已选 pilot 时拒绝猜测；磁盘上有产品仓也不再自动选中。JoyPaaS 类页从必读的 `conventions/SKILL.md` 挪到 `packs/joypaas/conventions/`。核心 `workflow-schema` 不再登记 kafka / etcd / zk 目录。

- 2026-09-29：中间文件与内核分界。产品仓会话的 trace / 提案草稿 / 复盘 / inbox 落到该仓 `.idev/`。idev 内核只留工具本身和导体自身会话。提升进内核须人说「提升到内核」，并先过 `scripts/kernel-promote-check.sh`。交付票仍在 `docs/task/`。

- 2026-09-29：入口瘦身（提案 `state/proposals/20260929-p3-entry-slimming.md`）。认票五步与 H1–H6 只留 `invoke.md`；`agent-brief` 不再写少了「最近一条 trace」的四步。决策树只留 `SKILL.md`（补上停问点确认、clean、done 后不改 goal，以及配方命中一句）。速查与 invoke 的第二张场景表改为三行摘要。启停 / UI 生命周期的 `coding_root` 与产品目录改到 `packs/joypaas/workflow-defaults.yaml`，核心配方 `from: pack`，读不到就问人。

- 2026-09-29：可移植性解耦（提案 `state/proposals/20260929-p2-portability-decouple.md`）。去掉 `outbound_registry.py` 写路径的隐式 `joypaas` 兜底：`write_config` 默认 pack 改空、`--pack` 默认空、`_cmd_write_config` 不再兜底 joypaas。无 pilot → 落 generic（不猜产品）；存量 `pilot=joypaas` config 零影响；读路径 `detect_pack` 本就 generic-safe 未改。selfcheck/healthcheck 仍绿。

- 2026-09-29：`SKILL.md` 与 `skill-details.md` 拆分；原硬规则第 4 条中「导体评审 / 再评估禁止输出综合分数或维度打分表」一句已按用户确认删除（提案 `state/proposals/20260929-drop-noscore-compress.md`）；红绿只走 verify、不准第二套测试框架或分数门禁仍有效。
- 2026-09-29：新增 `conventions/canon.md`（T/A/F，Agent 版架构范式）。
- 2026-09-29：非门禁不停规则由 `C1–C6` 改名为 `H1–H6`，避免与 `coding-tables.md` 的代码气味 `C1–C15` 撞号；`references/0011-chat-confirm-signoff.md`（已合并的空壳）删除。
- 2026-09-29：新增 `references/agent-brief.md`、`references/glossary.md`。
