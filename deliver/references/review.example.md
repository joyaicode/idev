# Review（对照密封基线，不是对照心情）

feature:
baseline_revision:
by:

## 少做（基线 item 未落地）

- item:
  evidence:

## 多做（基线外行为）

- 路径:
  处理: 删掉 / 标 UNRELATED 不改

## 基线冲突

- 无 / 有（停，等人选基线内修或 reopen）

## 编码规范（对照 `conventions/coding.md`，当轮纠正）

编号只认 `conventions/coding.md` §3.5：`P1–P17`、`C1–C15`、`R1–R6`（全表在 `coding-tables.md`）。仓内票禁止另起表号。
扫描 §1 / §2；结构调整过 §3；再按 §3.8 增强扫描。命中必须改掉，只记账不算过。

- 场景命中: 零命中
- 气味命中: 无（已扫）
- 纠正: 无
- 重构: 无
- 五轴: 正确性过；可读性过；架构过；安全过；性能过
- 栈指南: java8
- 增强扫描: 已跑 coding-scan + 五轴 + 栈指南
- 扫描: Java Problems/Qodana 或 `lint-fix` — 干净 / 未跑

## 本轮允许改的路径

只许 `arch.yaml` 里 `include: true` 的文件。工作区其它脏文件列在下面，**不要动**。

- UNRELATED:

## 填写示例（勿原样提交）

- 场景命中: P1（第三次展开规则 → 静态工厂）
- 气味命中: C2（缺值省略）
- 纠正: `FooService.java` — 缺 platform 改立刻 400；提取 `requirePlatform`
- 重构: 有（预备式）
- 护栏: `FooServiceTest`
- R 条件: R1–R6 均满足
- 五轴: 正确性过；可读性命中已改；架构过；安全过；性能过
- 栈指南: java8
- 增强扫描: 已跑
- 扫描: Problems 干净


## 架构范式（T# / A#，可选节，见 conventions/canon.md §7）

- 本轮命中 `T#`：（如 T4 依赖方向、T8 快速失败；零命中写“已扫 canon §2 信号与 §4 念头，无命中”）
- 所做动作：
- `arch` 阶段 A1–A8（canon §5）：已答 / UNPROVEN 项与补证据动作
