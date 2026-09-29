# 提案 P5：清内核残留的产线耦合与门禁盲区

- status: landed (2026-09-30, 人要求「修复所有问题」后确认补记)
- scope: 把逃过 strip 门禁的 joypaas 残留移出内核；补门禁扫描范围与词表。不改识别机制本身（那是 P4）
- created: 2026-09-30

## 对照重构目标（内核对所有产线通用）之后仍成立的问题

1. 入口 `SKILL.md` description 把某一产线的专属配方（UI自动化 / 建设UI自动化 / 自进化UI自动化 / 生命周期自动化 / ui-lifecycle / 多角色协调）当成内核能力宣传。这些配方实际只在产品仓 `.idev/workflows/`，内核 `workflows/` 没有。
2. `core-strip-check.sh` 的 L2 扫描范围是 conventions/references/deliver/verify/ops，**不含根 SKILL.md**；入口页的泄漏无人抓。
3. `scripts/lib/joypaas-root.sh` 是无人引用的兼容 wrapper（`source outbound-root.sh`），文件名本身即产品名泄漏。
4. `references/lite-change-pitfalls.md` 含 `setJoypaasConfig` / `onMicroError` / `requestPrefix` 等某一产线的前端 mock 细节，整页写「真票」。
5. strip-tokens 词表只列符号（`JoypaasAppService` 等），漏了 `setJoypaasConfig`，所以第 4 条的泄漏放行。

## 落地

- description：删产线配方名，改为「内核真实配方清单 + 产线在 `.idev/workflows/` 自定义 UI/启停/多角色等配方」（人协同改定）。
- `core-strip-check.sh`：L2 收集加入 `SKILL.md`，同时排除 `references/changelog.md`（历史记录合法保留）。
- 删除 `scripts/lib/joypaas-root.sh`（零引用，refs-check 未登记）。
- `lite-change-pitfalls.md`：内核版泛化成对所有产线成立的通用坑；JoyPaaS 的具体形状下沉到该仓 `.idev/pack/conventions/frontend.md`（code 阶段已加载），内核只留指针。
- strip-tokens 补 `setJoypaasConfig`，防回归。

## 不改的

- 不把 `joypaas` / `Joypaas` 裸子串加进词表。deliver/verify/ops 的 ADR 里有「`joypaas-verify` 是历史称谓」这类合法记录，加宽会误伤。只封真泄漏符号。历史称谓的彻底清洗是另一轮 ADR 改写，另开票。
- 不动 P4 的识别机制（marker / stage-extensions / extensions.yaml），只清耦合与门禁。

## 验证

- core-strip-check PASS（含新纳入的 SKILL.md 扫描）· refs-check PASS · healthcheck PASS（唯一 WARN 是尚无 lite-change 运行 trace，良性）。
- 内核残留 `setJoypaasConfig` / `joypaas-root` 复查零命中。
