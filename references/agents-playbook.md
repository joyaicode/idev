# skill 与 agent：唤起与配合的最佳实践

[agents.md](agents.md) 讲契约**是什么**，这页讲**怎么用**。职责分离的四条硬依据在那边，
这里只说操作。

---

## 一、什么时候用哪个入口

| 你想做的事 | 怎么起 | 为什么 |
|---|---|---|
| 一张票的端到端交付 | `/idev`，说清诉求 | 导体认票 → 认场景 → 自己决定派给谁 |
| 命中某条配方（跑自测 / 提测包 / 代码审查…） | `/idev` + **说出配方别名** | S8 按原话子串命中 `workflows/<id>`，比你自己挑 agent 准 |
| 只想要某一个专职能力 | `@agent-idev-coder`（Claude Code）/ `/idev-coder`（Cursor） | 跳过路由，直接点执行者 |
| 不确定该走哪条 | `/idev`，直接描述现象 | 决策树会定场景；说不清它会先看 `deliver.yaml` 的 `stage` |

**默认走 `/idev`。** 直接点 agent 是快捷方式，代价是**绕过了认票与路由** —— 它不知道票在
哪个 stage、不知道基线密封了没有，也不会有人替你把签字点守住。

**自动唤起不需要配置。** 两边都按 `description` 匹配，触发词写在 frontmatter 里。你只要
说「这个票要提测」这类话，skill 自己会上来。

---

## 二、导体的一轮长什么样

```
认票 ──→ 认场景 ──→ [S8: workflow.py next] ──→ 读 DELEGATE 行
                                                     │
                            ┌────────────────────────┴───────────┐
                            │                                    │
                     DELEGATE none                        DELEGATE <agent>
                            │                                    │
                     你自己做这一步                        组委派包 → 派出去
                     （human.gate 永远在这边）                     │
                            │                              收回报、核证据
                            └──────────────┬─────────────────────┘
                                           ↓
                              落委派留痕 → record → 一轮一条 trace
```

五个动作，每一个都有不能省的理由：

1. **`next`** —— 别凭记忆猜下一步是谁。配方改过 step 的话，你记的是旧的
2. **读 `DELEGATE`** —— `none` 和 `<agent>` 走两条完全不同的路
3. **组委派包** —— agent 看不到对话历史，这是它唯一的输入
4. **核回报** —— `PASS` 而无证据路径不作数，打回重做
5. **落留痕 + record** —— 留痕是出问题时唯一能回看的东西

---

## 三、委派包：少一项就白跑一趟

subagent 没有对话历史。**委派包不是摘要，是它的全部世界。**

照 [agents.md](agents.md) 的固定格式抄。几个最常漏的：

| 漏了什么 | 后果 |
|---|---|
| `票目录` | 它不知道往哪写，只能 `BLOCKED(brief)` |
| `stage` | `idev-deliver` 会拒绝推进——它不许自己从 `deliver.yaml` 推断 |
| `idev_root` | coder / verifier / ops 跑不了提效脚本，路径是空的 |
| `必读` 落点页 | 它会按自己的理解干，而不是按那一页的规矩 |
| `attempt > 1` 时的 `prior_failure` | 它会重犯上次的错，这一轮白跑 |
| 配方要 `product` 时没点名 | 内核规则：不点名就不启动、不猜 |

**重派时不要凭记忆重组委派包：**

```bash
python3 scripts/delegation.py replay --feature <f> --step <step>
```

它把上次那份原样打印出来（含 `prior_failure`），**但不自动重派** —— 派不派仍是你的决定。

---

## 四、验收回报：三件事必看

1. **`STATUS` 的分类** —— `BLOCKED(brief)` 是**你的锅**（补委派包重派）、`BLOCKED(env)` 是
   产线的锅（修 `.idev/`）、`BLOCKED(logic)` 要问人。不看分类就会去改错的东西
2. **`EVIDENCE` 的路径真的存在** —— `delegation.py` 的 `evidence-present` 会查，但你自己
   也该看一眼。**没有证据路径的 `PASS` 不作数**
3. **`FACTS` 有第一手来源** —— 只写「文档」不算。文档会过时，这是
   [boost.md](boost.md) 第零节的全部要点

另外两行值得扫一眼：`DOC_DRIFT` 非「无」时派一次 `docs.backfill` 去修那页文档；
`SUGGEST` 攒够两次再走提案，不要一次就改定义。

---

## 五、常见搭配

| 场景 | 典型链路 |
|---|---|
| 代码审查 | `/idev` 说「审查当前仓」→ S8 `code-review` → reviewer 出报告 → **人签收 `I*`** → coder 只改已签收项 → verifier 跑用例 |
| 小改 | `/idev` 说「走轻量」→ S8 `lite-change` → coder 改 + 自测 → **人签 plan** → verifier 跑 → 停在提测问 |
| 线上现象 | `/idev` 说现象 → S6 → ops 分类（`kind`）→ 交 verifier 跑 `debug` → ops 定根因 → 回退或修 |
| 查一个说不清的问题 | `/idev` → S4 → ops 走 `evidence.md` 闭环 + 假设台账，**先拿事实再推理** |
| 契约 / 经验回填 | `/idev` 说「回填」→ S5 → deliver 按 setup-agents-docs 的目录落盘 |

注意每条链路里**人签字的位置**：它永远在导体这边，不在 agent 里。

---

## 六、不要这样用

| 不要 | 为什么 |
|---|---|
| 同一轮派两个 agent 「并行省时间」 | `conventions/canon.md:181` 的反模式。先订死接口再并行，否则合并成本比省下的多 |
| 让 agent 去问人 | 它问不到。要停问就 `BLOCKED` 回报，由导体停 |
| 跳过 `next` 直接派你觉得对的 agent | 配方改过 step 你就派错了；而且 trace 里对不上账 |
| 替 agent 写 `FACTS` / `EVIDENCE` | 那是它的交代。你代写就等于没有交代 |
| 回报 `PASS` 但没证据路径仍 `record` | `evidence-present` 会抓，而且下次复盘时你查不到任何东西 |
| 为了让检查过而放宽检查 | 见 [failure-modes.md](failure-modes.md)——这一层的 bug 几乎全是「检查在该报警时沉默」 |

---

## 七、出问题时按这个顺序查

```bash
python3 scripts/delegation.py timeline --feature <f>   # 1 全链路：谁做的、多久、结果、证据
python3 scripts/delegation.py check    --feature <f>   # 2 五项诚实性检查 + §0 + 事实来源
python3 scripts/delegation.py replay   --feature <f> --step <s>   # 3 上次派的到底是什么
python3 scripts/agent-metrics.py --repo <仓>           # 4 跨票：哪个 agent / kind 问题密度最高
```

**第 2 步的责任方归因直接告诉你改哪里**：`brief-complete` 失败 → 改委派包（一处改动影响
全部 agent）；其余四项失败 → 改那个 agent。`agent-metrics` 的「下一刀」一栏按改动面从小到
大排好了。

改之前先扫 [failure-modes.md](failure-modes.md)。
