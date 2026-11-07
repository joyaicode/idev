- [隐形字符文件的编辑与验证方式](feedback_editing_invisible_chars.md) — 本仓库编辑含转义/隐形字符的文件（如 cases.yaml）时必须用终端+Python heredoc，且码点分析只能靠 Python，不能信终端渲染

- [Go 迁移 golden 安全网机制](project_go_migration_golden.md) — Python→Go 迁移期间，cases.yaml 双端共享 + 50 个 golden 快照 + record.sh PYTHONUNBUFFERED 确定性锁定的验证机制（2026-10-19 全链验证通过）

- [idev 设计文档 v3 位置与验收提案结构](reference_design_doc_v3.md) — 重构设计文档已入仓 design/idev-refactor-design-v3.md（提交 b96b6c9，2026-10-19）；验收提案 state/proposals/ 下 20261016（A/B/C/D 四组）与 20261019（签字按信号，切片 1–3 已落）

- [工作期间直接运行命令不询问](feedback_run_without_asking.md) — 用户要求任务执行中不要反复征求许可，直接运行命令、接受变更、自动重试；禁止使用提问类工具

- [DDD精读笔记忠实性抽查结果](project_ddd_notes_spotcheck.md) — Ch10-12 与 Ch13-14 精读笔记于 2026-11-02 完成忠实性抽查，12/12 全部通过，无需修改

- [书籍精读七批全部落地收口](project_ddd_gaps_proposal.md) — 2026-11-05 七批书籍精读缺口全部落 conventions/ 真源收口（C22–C31、R7、P18/P19、T/C 增补）；wangwei794 的持续授权 quote 覆盖后续「打磨各阶段经验指导」

- [微服务设计精读全书收口](project_microservices_notes.md) — 《微服务设计》第 1–11 章十批精读全部完成（2026-11-05 第十批收口，缺口1–17），conventions/ 真源与提案、缺口报告、精读表三处同步完毕

- [修改代码的艺术精读收口](project_legacycode_notes.md) — 《修改代码的艺术》（Feathers）第 9 本精读于 2026-11-06 全流程收口，真缺口 1 条落 R1「不满足时」列增补
- [代码大全精读收口](project_codecomplete_notes.md) — 《代码大全》第一版中译全书第 1–33 章于 2026-11-07 完成第 10 本精读，真缺口 1 条落 C2 default 未列值快速失败
- [GoF设计模式精读收口](project_gof_notes.md) — 《设计模式：可复用面向对象软件的基础》全书于 2026-11-07 完成第 11 本精读，真缺口 0
- [测试驱动开发精读收口](project_tdd_notes.md) — 《测试驱动开发》全书于 2026-11-07 完成第 12 本精读，真缺口 0
- [程序员修炼之道精读收口](project_pragmatic_programmer_notes.md) — 《程序员修炼之道》70 条 tip 于 2026-11-07 完成第 13 本精读，真缺口 3 条均落阶段页（估算迭代 / 架构工作流并发 / 复现测试红一次）
- [程序员的职业素养精读收口](project_cleancoder_notes.md) — 《程序员的职业素养》第 1–14 章与附录于 2026-11-07 完成第 14 本精读，真缺口 1 条落 req-quality §5（预估不是承诺 / 延迟风险当轮暴露）
- [Python C9 存量清理收口](project_c9_cleanup.md) — 2026-11-07 清理 84 处真实嵌套并修正 7 处表达式 if 误报，当前全仓 Python C9=0；C7/C12 另算
- [阶段入口已过闸经验注入](project_stage_prior_art.md) — 2026-11-07 已过闸经验/程序同时进入阶段入口与委派包，候选不进执行上下文；PyYAML 缺失时安静降级
- [全量精读可达审计与测试阶段落点](project_deep_read_all_books.md) — 2026-11-07 `deep-read-audit --all-books` 只收缺口报告；C26/C28–C30 进入 verifier 起草步骤，不新增插件
- [精读可达审计阶段范围口径](project_deep_read_stage_ranges.md) — 2026-11-07 阶段页全表范围展开为 staged；F2/F5/F6 进入自然阶段，不逐个复制 C/P/R
- [idev 效率根因与删除预算收口](project_efficiency_root_cause.md) — 2026-11-07 删除重复参考页，删除预算与自建期退出条件唯一真源收敛到 self-evolution
