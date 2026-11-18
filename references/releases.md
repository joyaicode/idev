# idev 发版记录

按提交点切片的发版摘要（changelog 按日期记工程细目，本页按版本给人看升级面）。
无版本号体系（无 tag / 无 ldflags），版本名取当日主线首个提交的日期——
`git describe` 不可用是如实状态；发版内容以提交区间为准。

## v2026.11.18 — abe4a2b（发版提交）

**主线：agent 能力增强五件套 + 打包部署三件套 + 基础修复**

升级方式：`bash scripts/idev-update.sh`（本版起可用）。

### 新能力

- **双层 agent loop 观测统一**（提案 `20261117-agent-loop-enhancement.md`，拷问十题全过）：
  - 新权威页 `references/agent-loop.md`——13 枚举统一停靠表（DELEGATE / PARALLEL-WAVE / SIGNAL / HUMAN-GATE / CAP-REACHED…）、循环上限总表（fanout 8 片 / react 16 跳 / drive 8 步 / clean_pass 5 轮一处可查）、探针规约、反模式表
  - `DOCK reason=<枚举>` 停靠行接入三种内层循环（drive / fanout / land），「为什么停」四个循环说同一种话
  - `CLEAN attempt=n/cap` 整轮重试计数（从 revisions 派生，不建第二账本）
- **上下文压缩**：HANDOFF@100 轮自动落 `<票>/workflow/resume.yaml` 结构化恢复包（open 步骤 / PROGRESS / prior_failures / reads 指针 / timeline 指针——全为既有落盘的拼装，零 LLM 生成文本）；新会话按 `open:` 行接着跑，不再整票重读
- **AST 差分剪枝**：`scripts/lib/symbol_diff.py` 四档（ast/brace/file/none）；attempt>1 重放仅 python ast 档剪除改动函数邻域外的区间（`上下文剪除:` 行永远可见、需要时 load）；coding-scan「改动邻域」段给审查者提名（4 块/4000 字封顶）
- **Read 回填**：整文件 `Read` 经转录派生自动进 `workflow/reads.yaml`（只记事实 span+sha256、只补空、票内）
- **治理登记**：新权威页 `references/governance.md`——G1–G18 登记表把四层治理点（prompt/机检/go强制/观测）一处看全；对照 Claude hooks/permission 的差距分析（裁量分类器明确不引入）
- **打包部署三件套**（提案 `20261117-init-update-packaging.md`，人四选定案）：
  - `scripts/idev-init.sh`：全新机器引导（clone 指引 / 依赖只报不装 / 构建 bin/idev / 同伴技能来源提示 / 复用一键安装 / 重启生效收尾）
  - `scripts/idev-update.sh`：升级通道（脏区拒绝 → behind 计数 → ff-only pull → 重建二进制 → 幂等重装 → LaunchAgent heal → 更新摘要）
  - 落伍提示：会话开场与 `install --verify` 在 fetch 缓存显示落后时打 `KERNEL behind=N`（不联网、如实标缓存）
  - 子 agent 挂载验证：五执行者双宿主（claude+cursor）解析齐全一行确认
- **skill-up 评测接入**：`evals/` 规则断言套件 + `skill-up-eval.py`（FORBIDDEN 反 LLM 评分自检）+ 停止钩子后台拉起 + CI 接线

### 修复

- pre_tool hook deny 理由双通道：此前 Claude Code 下被拦只见「No stderr output」不知道撞了哪条；deny 理由现同时进 stderr（exit 2 语义不变）
- golden 13 例既有漂移归因收口（b7a5ae3 drive-mode 在途快照，`record.sh --accept` 带理由重录，verify 53/0）
- 若干测试脚本补可执行位

### 验证基线

agent-smoke 490/0（终态复跑）· healthcheck warns=0 · selfcheck PASS（378s）· 冷启动 21843≤24000 ·
golden verify 53/0 · 新测试 19 例（symbol_diff 6 / merge_reads 5 / resume_pack 4 / +2 扩展）·
CI 七 job 全绿。两份提案均走 propose → 拷问 → 人签 → 落地全程。

### 已知缺口（如实记录）

idevd 无 staleness 守护；unlink 不完整（companion/别名/codegraph hooks 不在列）；
无版本号/tag 体系（本页版本名是日期约定非 semver）。

### 本版提交区间

b924e64..abe4a2b（5 个主线提交：080bdbf 五件套+skill-up / dd35b66 golden 收口 / 8dab16c 打包三件套 / abe4a2b hook 修复）
