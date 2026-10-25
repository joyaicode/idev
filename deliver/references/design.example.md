# 方案：approval.enabled 为 false 时不建单

给人评审的叙述。机读影响面和用例意图在 `arch.yaml`，可执行用例在 `verify/plan.yaml`。三份对同一批条目。

## 前置

影响面是 `ApprovalMethodInterceptor` 与 `ApprovalAnnotationIT`。两个文件都读过。没有重大缺陷：开关为 true 时的拦截与建单仍与现有契约一致。

本需求要改的是拦截器里 `approval.enabled=false` 的分支，以及锁住 enabled=true 的现有断言，合计 28 行。既有问题 1 条、2 行。2 × 5 < 28，小于 1/5。建议本次不修，只在方案里标明。人还没选。

- `ApprovalMethodInterceptor` 构造处的显式类型参数（规范，2 行）。落在本次要改的同一类型里，随本次改掉，不写成基线新义务。

## 目标

When approval.enabled is false, annotated methods run without creating a ticket.

非目标仍是基线那句：不改 Replay、ticket fields、OMI channels。本方案覆盖 B1、B2、B3，不另加义务。

## 方案

`ApprovalMethodInterceptor` 在 `approval.enabled=false` 时直接 `proceed()`，不调用建单网关。
开关为 true 时保持现有拦截与建单（B2）。Replay 与 ticket field filling 不在这次改动里（B3）。

不新加拦截层，不改注解本身。分支只看已经存在的 `approval.enabled`。

## 契约

无新对外接口、事件或表。调用方仍走 `@RequiresApproval`。行为只由已有配置 `approval.enabled` 决定。

## 影响面

- hop 0：`ApprovalMethodInterceptor`（include）。这是唯一改行为的类型。
- hop 1：`ApprovalAnnotationIT`（include）。用来锁住 enabled=true 的现有行为，不是新功能。

其它调用方不改。`arch.yaml` 的 `impact_candidates` 与这里同一份。

## 回退

把 `approval.enabled` 设回 true，拦截与建单恢复。没有数据迁移，没有第二套开关。降级就是这个配置回退。

## 用例

与 `arch.yaml` 的 `case_intents` 同一批，并落到 `verify/plan.yaml`（先 `UNPROVEN`，跑过才写证据）：

- `disabled-executes`（B1，correctness）：enabled=false 时方法体执行，且没有建单副作用。
- `enabled-still-intercepts`（B2，compat）：enabled=true 仍拦截并建单。
- `replay-untouched`（B3，compat）：Replay 与 ticket field filling 无改动。
