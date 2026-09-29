# 提案 P2：可移植性解耦（把 joypaas 从核心默认里拔出来）

- status: landed (2026-09-29, 人授权「按建议」)
- scope: 导体入口 / outbound registry / selfcheck
- created: 2026-09-29
- signal: 人工审计（用户要求「验证接第二个产品只改一处」）；非 HARD/inbox 触发

## 诊断（证据，非主观）

SKILL.md / cheatsheet 反复声明「JoyPaaS 是试点叠加，不是导体本体」，但实现层把 `joypaas` 当**隐式默认兜底**，与该声明冲突：

1. `scripts/lib/outbound_registry.py:221` — `requested = (pack_id or existing_pilot or "joypaas").strip()`：未指定 pilot 时静默落到 joypaas。
2. `outbound_registry.py:208,278,325,336` — 多处 `pack_id="joypaas"` / `default="joypaas"` 作为函数与 argparse 默认。
3. `state/outbound-config.json` — 重置后仍写死 `"joypaas_root"` / `product_root=/Users/.../joypaas` / `required:[joypaas-onboard-diagnose, jmiss-incident]`。
4. `outbound_registry.py:236-237` — `if pack_id=="joypaas": data["joypaas_root"]=...` 特判键名，产品名进了数据结构字段。

**注意（据实）：** 解耦机制**已大部分就位**——`IDEV_PILOT` 环境变量、`--pack` 参数、`packs/joypaas` 目录、selfcheck 已有 generic-repo 对照（`IDEV_PILOT` 未设 → 不要求 pack）。所以这不是「焊死」，而是「默认值偏向单一试点」。修复面比预期小。

## 要改什么

1. **去掉隐式 joypaas 兜底**：`(pack_id or existing_pilot or "joypaas")` → 无 pilot 时返回 generic（不 require 任何 pack），不猜产品。
2. **字段名去产品化**：`joypaas_root` → 统一用已存在的 `product_root`；保留 `joypaas_root` 仅作读取时的向后兼容别名（读，不写）。
3. **argparse 默认改为必填或 generic**：`--pack default="joypaas"` → 无默认，未传则 generic。
4. **写一个可移植性验收脚本**（或扩 selfcheck 一个 case）：模拟「接产品 X」，断言只需 `bootstrap-outbound.sh <root> --pack X` 一条命令、不改任何 .py/.sh 源。

## 不改什么

- `packs/joypaas/` 内容（试点包本身合法，是叠加）。
- selfcheck 里 `IDEV_PILOT=joypaas` 的正例（作为「已选试点」路径的回归，保留）。
- outbound handoff 的整体机制（S7 交出口设计正确）。

## Grill 要点（land 前必答）

1. 去掉兜底后，**存量** JoyPaaS 环境首次跑会不会因「无 pilot」误判 generic 而漏掉 required skill 检查？迁移脚本是否需要一次性把现有 outbound-config 标记为显式 pilot=joypaas？
2. `joypaas_root` 兼容别名保留多久、何时删？还是本轮直接迁移干净？
3. 「只改一处」的验收，一处指的是 outbound-config 还是一条 bootstrap 命令？边界订死。

## 验收

- selfcheck / healthcheck 仍绿。
- 新增可移植性 case 通过：generic 产品接入零源码改动。
- `grep -rn '"joypaas"' scripts/lib/outbound_registry.py` 不再出现「默认兜底」用法（特判/别名可留但注释说明）。
- SKILL.md「JoyPaaS 是叠加不是本体」声明与实现不再矛盾。

## LAND 记录（2026-09-29）

**实际修复面比提案更小**——深读后确认隐式兜底只在**写路径** `write_config`；读路径 `detect_pack`（resolve 用）本就 generic-safe（第158-176行），无需改。

改了 3 处（均在 `scripts/lib/outbound_registry.py`）：
1. `write_config(pack_id="joypaas")` → `pack_id=""`，兜底链 `(pack_id or existing_pilot or "joypaas")` → `(pack_id or existing_pilot)`，加注释说明「空=generic」。
2. `_cmd_write_config` 里 `args.pack or "joypaas"` → `args.pack or ""`。
3. `write-config` 子命令 `--pack default="joypaas"` → `default=""` + help 说明。

**未改**（据实缩小范围，符合 T1/YAGNI）：
- `joypaas_root` 兼容别名保留（`if pack_id=="joypaas"` 特判仍写该键，供旧读取方兼容）——存量不破坏，删除留待有第二产品时再做。
- `pack-link` 子命令 `--pack default="joypaas"`：只读用途、有显式调用方（`link-outbound-skills.sh:78`），本轮不动，最小化风险。

**验证证据**：
- 新行为：`write-config --product-root /tmp/generic-x`（无 --pack）→ `pilot='' required=[] joypaas_root不出现`。
- 存量兼容：已有 `pilot=joypaas` 的 config → 仍 `pilot=joypaas` + required 含 onboard-diagnose。
- selfcheck PASS（两个 write-config 测试均显式传 `--pack joypaas`，不受默认值变更影响）、healthcheck PASS。

**grill 卡点1 的答案（据证据，非推测）**：存量 `state/outbound-config.json` 已显式含 `"pilot":"joypaas"`，去掉隐式兜底走的是显式 pilot 路径，存量零影响——无需迁移脚本。
