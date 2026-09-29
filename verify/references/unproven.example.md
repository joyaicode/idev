# UNPROVEN 面

feature: example-feature
plan_revision: 1

- dimension: boundary
  reason: 无额外边界包
  risk: 低
  follow_up: 下轮补 exception 用例
- dimension: concurrency
  reason: 无场景包
  risk: 中
  follow_up: 下轮补压测场景
- dimension: performance
  reason: 无基线 QPS
  risk: 低
  follow_up: 有基线后再验
- dimension: ui-prototype
  reason: 无登录态前端对照
  risk: 高
  follow_up: 安装当前产品 .idev/handoff.yaml 里的取 Cookie Skill 后复验

# 禁止：dimension: correctness
