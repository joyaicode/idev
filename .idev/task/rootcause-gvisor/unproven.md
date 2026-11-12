# UNPROVEN 面

feature: rootcause-gvisor
plan_revision: 1

- dimension: concurrency
  reason: 基线只要求一次 rootcause 探针。没有并发调用契约。
  risk: 低
  follow_up: 若以后进共享 CI，由 wangwei794 记一次并发 1 的计时
- dimension: performance
  reason: 本地命令，没有时延或吞吐基线。120 秒只是探针超时。
  risk: 低
  follow_up: 有时延基线后再验
- dimension: ui-prototype
  reason: 没有界面。能力是 repl 的 --step rootcause。
  risk: 低
  follow_up: 无
