# idev 变更记录（给人看，Agent 无需读取）

- 2026-09-30：workflow 补齐三件套。编排语法的代码形态收进 `scripts/lib/workflow_spec.py`（kind 与落点、顶栏 / 参数 / 策略取值、配方与 run 校验），`workflow-check` 改用它，并开始拒绝未知字段、非法 `from` / `policy` / `risk_tier`。新增驱动器 `scripts/workflow.py`（`resolve` / `start` / `next` / `record` / `status` / `abort`）：按配方写 `run.yaml`，给出下一步与落点页，守跳步、签字原话、失败即停，不替 Agent 执行步骤。无票运行落 `product_sink.py workflow-runs`。自检锁住文档 kind 表与代码一致和驱动规则。`workflow-check` 对齐驱动器：产品配方从扩展根读；产品可有多条配方，但一个 id 或别名只许指向一条生效配方；`--run` 核对步骤与所记配方一致。

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
