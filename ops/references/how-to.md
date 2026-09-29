# 运维排障（分类 → 复现 → 回退或交出去）

投产之后（或交付中途）出现现象：先分类，再取证。尺仍是密封基线。红绿走 verify 模块。

> 模块：`~/.cursor/skills/idev/ops/SKILL.md`（入口 `idev`）  
> 分类：[classify.md](classify.md) · 契约：[ops-schema.md](ops-schema.md)  
> 决策：[0010](0010-ops-conductor.md)

本机实验。接入坑走当前产品 `.idev/handoff.yaml` 的接入 Skill。集群现场走其中的事故 Skill。

## 何时用

| 场景 | 做法 |
|------|------|
| 已交付能力与基线不符 | 本模块，`kind=feature` + verify `debug` |
| 人要抽查回归 | `kind=patrol`，无包拒跑 |
| 登录 / PIN / CORS / webpack | `kind=onboard`，handoff 后换 Skill |
| 某实例集群告警 / 水位 / raft | `kind=runtime`，handoff 后换 Skill |
| 只要跑已有 case 的红绿 | 入口路由到 verify 模块 |

## 产物

| 产物 | 路径 | 人签字 |
|------|------|--------|
| 排障单 | `<票目录>/ops.yaml` | 分类后继续；关闭时 `resolved` + `by` |
| debug / patrol | `<票目录>/verify/plan.yaml` | plan `accepted` |
| 回退 | `deliver.yaml.stage` + `defect_origin` | 人确认 origin |

## 能 / 不能

| 能 | 不能 |
|----|------|
| 复现后回退 `code` / `arch` / `req` | 用线上现象倒逼改 goal |
| handoff 给已有排障 Skill | 把对方的 Confirm 表抄进本模块 |
| 人 promote 本次 debug case | Agent 自动晋升巡检包 / 自动修生产 |
