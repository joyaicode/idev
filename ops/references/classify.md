# 现象先分类（不准猜完就改）

只定 `kind` + `handoff`。分类不是根因。对不上就 `unknown`，停问。

| kind | 你看到的 | 去做 | 不要做 |
|------|----------|------|--------|
| `onboard` | 登录/接入/嵌套控制台起不来 | `handoff` 填当前产品 `.idev/handoff.yaml` 的接入 Skill | 在 idev 里另写一套 PIN / CORS |
| `runtime` | 产品集群/实例运行时事故 | `handoff` 填当前产品 `.idev/handoff.yaml` 的事故 Skill | 把 Release 健康当成运行时；自动重启 |
| `feature` | 已交付（或交付中）能力与**密封基线**不符；同一环境/产物上能指到 item | 本 Skill + verify `debug` | 口头加一条新 must |
| `patrol` | 人要重放已登记回归包 | verify `patrol`；无包拒跑 | 现编巡检用例 |
| `unknown` | 环境/产物/层说不清 | 停，要齐现场四件 | 写结论或回退 |

## 现场四件（缺一就停）

1. **现象** — 用户屏幕上的原话，不是「接口 500」。
2. **环境** — 本机 webpack / 本机 jar / 测试域名 / 生产。
3. **产物** — 哪次发布、哪份包；禁止对着源码修、让用户在旧包上验收。
4. **可观察物** — 一条请求/响应、一段日志、一个监控点。

## 和基线的关系

- 有密封 `baseline.yaml`：怀疑的 item 写入 `suspect_item_ids`。没有对应 item → 先问是不是 `baseline-conflict`，不要发明 item。
- 无基线（纯接入/集群）：不要伪造 `<票目录>/baseline.yaml` 来「方便排障」。
