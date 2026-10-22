# 提案：delegation 留痕 YAML 折叠吞换行（机检盲区）+ 两项流程惯例

- status: draft
- 来源：code-review 真票全程跑完（run 01M5F7EKCQ1EK4M5ANY5CRQF70，2026-10-22 done）沉淀的三条反馈
- 委派留痕：fix-2.yaml（首次落痕 6 项机检 FAIL 的根因）/ fix-verify-1.yaml / run-1.yaml
- 证据：`docs/task/code-review/workflow/delegations/`（joypaas 仓）

## P1（建议当轮修）：report.raw 折叠吞换行，行锚定机检全部失明

**现象**：`delegation.py write` 收到的 stdin YAML 里 `report.raw` 是多行回报（FACTS/DOC_DRIFT/SCOPE/RED_FIRST/ASSUMED 各占一行），但落盘后单引号标量把换行折叠成空格。机检全部按 `(?mi)^\s*FIELD:` 行首锚定——折叠后一个都匹配不上，首次落痕报 6 项 FAIL（facts-first / drift-declared / assumption-declared / scope-declared / red-first / s0-declared），责任方全标 agent，实际是存盘格式把 agent 写对的字段弄丢了。

**修复选项**（推荐 a）：
- a. `save_locked` 落盘前把 `report.raw` 规格化为块标量（`|`），保真换行——一处改动，所有既有机检立即恢复视力；
- b. 机检正则改为先 `re.sub(r"[ \t]+", " ", raw)` 再按字段名切分——治标，且 `_paths()` 的整词匹配也会受折叠影响，不如源头保真。

**验收**：`delegation.py write` 落一份含多行 raw 的留痕 → `delegation.py check` 对该留痕零 FAIL。

## P2（惯例）：委派与 review.md 的代码定位统一「方法名锚点」

**现象**：本轮 I1/I3 的行号全部漂移（review.md 记 `BudgetRecognizer.java 101 行` / `validateMapped 1893–1899`，代码实际 122 / 1669–1687——review 与 fix 之间用户有平行会话动了同一文件）。两次委派都靠委派包预判「方法名 + 第 N 个该构造」才定位成功，coder 与 verifier 的 SUGGEST 不约而同指向同一件事。

**落点**：`agents/idev-coder.md` / `agents/idev-reviewer.md` 的回报格式说明加一句：**CHANGED/SCOPE/位置字段用 `file:方法名` 锚点，行号只作辅助**；`deliver/references/review.example.md` 的 I* 模板同步。

## P3（惯例）：selftest plan 的 selector 须指向含断言的测试类

**现象**：plan 的 I1 case selector 写了 `JoypaasAccessLayerPropertiesTest`（38 例配置绑定侧，不断言 `validateMapped`），真正断言在 `BudgetRecognizerTest.roleMappingMustBeStandardSpec`。本轮靠 verifier 识别并跑了覆盖测试才没漏，但「跑了但没断言到点」在别处可能假绿。

**落点**：`verify/references/plan.example.yaml` 注释或 `agents/idev-verifier.md` 加一句：**selector 必须是含该 case `assert` 语句的测试类**；起草 plan 前先确认断言落点。

## 不并入本轮（记录在案）

- `SpringdocBoundaryTest`（3 例，12:46 出现于 joypaas）：UNRELATED 脏文件（mtime 晚于 fix 租约释放、不在围栏 5 文件、untracked），不属 code-review 交付。
