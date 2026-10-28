---
module: conventions
parent: idev
---

# 公共规约

由 `idev` 按场景对类：S1 / S4 / S6 **先读本页**再开执行模块；S2 / S3 / S5 能定类则**只开该类一页**，定不了再读本页一次。不要每轮强制先读本页。本目录不是独立 Skill。

**通用排查闭环的真源在本模块**（[evidence.md](evidence.md)）。  
idev 不依赖任何一个产品。先走内核。进入阶段用 `scripts/session-context.py` 列出要打开的 `.idev` 页，只打开 `OPEN` 行。还没有标记就只读下面的核心类。分工见 [scope.md](scope.md)。

## 核心类（所有产品）

| 类 | 何时 | 本模块 | 产品仓 |
|----|------|--------|--------|
| 排查闭环 | 分析 / 论证 / 推测 / 查问题 | [evidence.md](evidence.md)（**通用真源**） | 只许指针 |
| 编码规范 | 改任何代码或写 Review | [coding.md](coding.md) §0；扫表再开 [coding-tables.md](coding-tables.md) | 不要把 23 模式名录抄进仓 |
| 架构范式 | `arch` 阶段、任何“加一层 / 拆分 / 缓存 / 队列 / 重写”的念头 | [canon.md](canon.md) §1 协议 + §5（T1–T12 / A1–A8） | 只留指针，不抄原则表 |
| 领域建模 | 涉及新领域概念 / 跨模块术语 / 通用语言 | [domain-modeling.md](domain-modeling.md)（arch 阶段调起的透镜） | 术语表随票走，不进核心 |
| Java 领域 | 改 Java | [java.md](java.md) 按**该仓**语言级别 | 四准则在该仓。核心不默认某一语言级别 |
| Vue | 改 `.vue` / Vue Router / Pinia / Vite+Vue | [vue.md](vue.md) 按阶段打开 vuejs-ai 技能 | 不抄技能正文。产品控制台规约仍在该仓扩展包 |
| 文档治理 | 契约 / 回填 / 票 | [docs/SKILL.md](../docs/SKILL.md) | 目录认 setup-agents-docs，问句认 grilling。还没有这套文档时阶段状态在 `.idev/task/` |

当前任务落在哪一类，只深读那一页。违反硬规则 = 拒过。

## 硬规则

1. **先对类再改。** 不准把某个产品的页面/分类器写成 idev 核心契约。
2. **通用与产品不两写。** 排查闭环只改 [evidence.md](evidence.md)。试点摘要打架 → 改该仓真源，再回填叠加页。**从试点沉淀到核心之前，先剔除专有逻辑**（见 [scope.md](scope.md)）；剥不干净不要进核心。
3. **专项不膨胀。** 审批 / 拓扑 / 巡检 / 角色列表只留取值。
4. **样板间不是其他产品的业务源。** 工程形态可参考该产品自己的样板间；服务码、协议、页面不要当其它产品的默认。
5. **不要**为本模块再开顶层 Skill。
6. **编码规范**入口只改 [coding.md](coding.md)；全表只改 [coding-tables.md](coding-tables.md)。
7. **P/C/R 编号只认 coding.md**（§3.5，全表在 coding-tables.md）。仓内 review 禁止第二套表号。
8. **T/A/F 编号只认 canon.md**（原则 T1–T12、架构出门 A1–A8、失败模式 F1–F7）。它是 P/C/R 的上游原则层：不新增第二套严重度，不新增强门禁。
