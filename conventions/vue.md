# Vue 语言尺

权威是内核副本 `skills/vue/`（上游 `vuejs-ai/skills`）。本页说明每一份用来判定什么。该打开哪一份，以脚本打出的路径为准。

产品控制台的页面、路由和身份规约仍在该仓扩展包。本页只管 Vue 语言与框架写法。

## 何时打开

本轮路径、依赖或任务碰到 `.vue`、Vue Router、Pinia，或 Vite 搭配 Vue。与 Vue 无关的 TypeScript 或其它前端，不开本页。

## 怎么用

1. 跑 `python3 $IDEV/scripts/vue-skills.py --repo <仓> --stage <阶段>`。没有输出就不是 Vue 仓，到此为止。`VUE open` 必读。`VUE if` 只在本轮碰到该行主题时打开。`VUE MISSING` 就停。
2. 打开后按该技能自己的工作流做，包括它点名的必读参考。只读到技能首页不算做过。路径在 `skills/vue/<name>/SKILL.md`。
3. 默认栈是 Vue 3 + Composition API + `<script setup lang="ts">`。这是 `vue-best-practices` 的规定。
4. 编码阶段：技能判定出的规范问题和不合理的组件、状态边界，当轮改掉。审查阶段：写成待签收项。根因阶段：技能只解释 Vue 机制，证据闭环仍走 [evidence.md](evidence.md)。

`session-context.py` 和 `coding-scan.sh` 在 Vue 仓上会打出同样的 `VUE` 行。

## 阶段

| 阶段 | 打开 | 用它做什么 |
|---|---|---|
| UI 设计 | `vue-best-practices` | 先定组件边界、状态所有者和数据流，再写界面结构 |
| UI 设计（可复用 composable） | `create-adaptable-composable` | 要做库级别、入参可以是值或 ref 的 composable 时再开 |
| 编码 | `vue-best-practices` | 识别并判定规范，纠正不合理的组件与状态结构 |
| 编码（Options API） | `vue-options-api-best-practices` | 项目明确使用 Options API 时再开 |
| 编码（JSX） | `vue-jsx-best-practices` | 项目明确使用 JSX 时再开 |
| 编码（状态） | `vue-pinia-best-practices` | 本轮碰到 Pinia |
| 编码（路由） | `vue-router-best-practices` | 本轮碰到 Vue Router |
| 自测 | `vue-testing-best-practices` | 组件、composable、store 怎么测。失败签名计数照旧 |
| 测试 | `vue-testing-best-practices` | 用例怎么断言 Vue 行为 |
| UI 自动化 | `vue-testing-best-practices` | Playwright 与组件测试的分工。剧本生命周期仍走 `ui-playbook.py` |
| 根因 | `vue-debug-guides` | 运行时错误、警告、异步失败、水合、响应式。同时打开 `vue-best-practices` 对照写法 |

## 执行者

| 执行者 | 打开的阶段 |
|---|---|
| `idev-deliver` | UI 设计；架构方案里的组件边界 |
| `idev-coder` | 编码、自测 |
| `idev-reviewer` | 编码各行（写成审查项） |
| `idev-verifier` | 测试、UI 自动化 |
| `idev-ops` | 根因 |
