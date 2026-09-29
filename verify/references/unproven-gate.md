# UNPROVEN 面明示门（test / 提测）

verify 允许缺包维度写 `UNPROVEN`，但**禁止沉默**：`mode=test` 时维表六族每个都必须有 case，或出现在 `plan.yaml` / `<票目录>/unproven.md`。只写一份空清单、或只列一维，`check-feature test` FAIL。

## 必检维度（mode=test）

| 维度 | 无 case / 无基线时 |
|------|-------------------|
| correctness | 禁止提测（必须有可执行 case） |
| compat | 可 `UNPROVEN`，须写影响面与为何不跑 |
| boundary / exception | 可 `UNPROVEN`，须写缺哪些边界 |
| concurrency | 可 `UNPROVEN`，禁止写达标 |
| performance | 可 `UNPROVEN`，禁止写达标 |
| ui-prototype / UI | 可 `UNPROVEN`，须写无原型/无登录态等原因 |

## 落盘格式（二选一）

**A. `<票目录>/unproven.md`**

```markdown
# UNPROVEN 面
feature:
plan_revision:
- dimension: concurrency
  reason: 无场景包
  risk: 中
  follow_up: 下轮补
- dimension: ui-prototype
  reason: 无登录态前端对照
  risk: 高
  follow_up: 接当前产品 .idev/handoff.yaml 里的取 Cookie Skill 后再验
```

**B. plan.yaml 顶层**

```yaml
unproven_surfaces:
  - dimension: performance
    reason: 无基线 QPS
    risk: low
```

## 硬规则

1. `correctness` 必须有可执行 case，不得出现在 UNPROVEN 清单里充当「免测」。
2. `status: PASS` 的 case 不得同时挂在 UNPROVEN 面。
3. 人 `aligned` 前须确认：清单已读，接受残留风险。
4. `check-feature <feature> test`：六族（correctness / compat / boundary|exception / concurrency / performance / ui-prototype|ui）缺 case 且未写入 UNPROVEN → FAIL。六族都有 case 时可不建清单。
5. `boundary` 与 `exception` 算同一族；`ui-prototype` 与 `ui` 算同一族。
