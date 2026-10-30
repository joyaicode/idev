#!/usr/bin/env python3
"""Derive a reviewable UI preview from the sealed baseline's ui rules.

    ui-spec.py --feature F [--repo DIR] [--out DIR]
    ui-spec.py --feature F --check        # only validate the ui rules
    ui-spec.py --schema                   # print the ui block schema

Why derive instead of hand-draw: a prototype page is not the requirement,
it is one rendering of it. Hand-drawn pages drift — the page says one thing,
baseline.yaml says another, and whoever is testing believes the page. The
baseline is the measuring stick (deliver-schema.md: 验收尺是基线), so the
preview has to be *generated from* it and regenerated whenever it moves.

So the ui rules live in baseline.yaml under each item, and this produces:

    <ticket home>/ui/<feature>.spec.json   a json-render flat spec
    <ticket home>/ui/<feature>.html        a self-contained preview page

The spec follows vercel-labs/json-render's flat shape (root + elements with
type/props/children), so a product with a json-render catalog can render it
with its own component library. The HTML is a zero-dependency fallback for
review: it opens in a browser with no build step, which is what a
requirements review actually needs.

**What this does not do:** choose your components. The catalog is a product
asset (conventions/cohesion.md: 产线特性写产品仓 .idev/), so the spec names
semantic types — form / field / table / action — and the product maps them
to element-ui, shadcn, or whatever it already uses.

Exit: 0 ok, 1 findings in the ui rules, 2 cannot read the inputs.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import kind_agents  # noqa: E402
import safeyaml  # noqa: E402
import ui_surface  # noqa: E402

sys.path.insert(0, str(kind_agents.kernel_root() / "scripts" / "lib"))
try:
    import doc_home  # noqa: E402
except ImportError:
    print(f"BLOCKED cannot import doc_home from {kind_agents.kernel_root()}", file=sys.stderr)
    raise SystemExit(2) from None

SCHEMA = """\
# baseline.yaml 的 ui 块(每个 item 下可选)
#
# 需求细化到交互层面,但**只说规则,不说实现**:说「必填、失败时留在原页并指出哪一项」,
# 不说「用 el-form 的 rules 属性」。实现是 arch 的事。
#
# items:
#   - id: B1
#     must: 登录失败给出可定位提示
#     acceptance: 3 秒内返回带错误码的提示
#     ui:
#       screen: 登录页                 # 必填:哪个界面
#       intent: 用户输错密码后知道该怎么办   # 必填:用户在这完成什么
#       fields:                        # 输入项,每个带校验与失败表现
#         - name: username
#           label: 用户名
#           type: text                 # text|password|number|select|date|checkbox|textarea
#           required: true
#           rule: 非空,长度 4-32
#           on_invalid: 字段下方红字「用户名需 4-32 字符」,焦点留在该字段
#         - name: password
#           label: 密码
#           type: password
#           required: true
#       actions:                       # 可触发的动作与每种结果的表现
#         - name: 登录
#           primary: true
#           on_success: 跳转工作台,顶部提示「欢迎回来」
#           on_failure: 留在本页,错误码 AUTH_401 显示在表单上方
#           on_pending: 按钮禁用并显示加载态,不允许重复提交
#       states:                        # 这个界面的非常规状态
#         empty: 首次进入时不显示任何错误
#         loading: 骨架屏,不显示空数据文案
#         error: 网络失败显示「网络不可用,请重试」与重试按钮
#       a11y: 错误提示用 aria-live=polite 播报       # 可选
#
# 可机检的部分见 --check:
#   screen / intent 必填 · 每个 field 要 rule 或 required · 必填字段要 on_invalid ·
#   每个 action 要 name、on_success、on_failure、on_pending ·
#   进行中和成功、失败和成功，各是一句不同的话 ·
#   同一 screen、同一 scope 里 action name 只出现一次。scope 可省略，省略就是同一个范围 ·
#   同一 screen 上的 field label 只出现一次 ·
#   有 fields 就要有 action ·
#   规则含主观词(合理/友好/流畅)即不可测 · 不许写实现细节(el-xxx / class / css)
"""

FIELD_TYPES = ("text", "password", "number", "select", "date", "checkbox", "textarea", "radio", "file")
VAGUE = ("合理", "友好", "流畅", "优雅", "良好", "美观", "易用", "方便", "清晰", "尽量", "适当")
# 实现细节不该出现在需求里：说清规则，不替 arch 选控件。
IMPL = re.compile(r"\bel-[a-z-]+|\bv-(?:model|if|for)\b|class\s*=|style\s*=|#[0-9a-fA-F]{6}|\.vue\b|<[a-z]+>")


def vague_hits(text: str) -> list[str]:
    return [w for w in VAGUE if w in text]


def check_ui(items: list, out: list[str]) -> None:
    """The machine-checkable half of a UI rule set."""
    seen_screens: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id", "?"))
        ui = item.get("ui")
        if ui is None:
            continue
        if not isinstance(ui, dict):
            out.append(f"items[{iid}].ui 不是 mapping")
            continue

        screen = str(ui.get("screen") or "").strip()
        intent = str(ui.get("intent") or "").strip()
        if not screen:
            out.append(f"items[{iid}].ui 缺 screen —— 这条交互发生在哪个界面?")
        else:
            seen_screens.add(screen)
        if not intent:
            out.append(f"items[{iid}].ui 缺 intent —— 用户在这完成什么?")

        blob = json.dumps(ui, ensure_ascii=False)
        hits = vague_hits(blob)
        if hits:
            out.append(f"items[{iid}].ui 含主观词 {'/'.join(hits)} —— 两个人读它会得出不同结论")
        impl = IMPL.search(blob)
        if impl:
            out.append(f"items[{iid}].ui 写了实现细节「{impl.group(0)}」—— "
                       "需求说规则,控件选型是 arch 的事")

        fields = safeyaml.as_list(ui.get("fields"))
        actions = safeyaml.as_list(ui.get("actions"))

        for f in fields:
            if not isinstance(f, dict):
                out.append(f"items[{iid}].ui.fields 有非 mapping 条目")
                continue
            fname = str(f.get("name") or f.get("label") or "?")
            ftype = str(f.get("type") or "")
            if ftype and ftype not in FIELD_TYPES:
                out.append(f"items[{iid}].ui.fields[{fname}].type={ftype} 不在 "
                           f"{'/'.join(FIELD_TYPES)} 里")
            if not str(f.get("label") or "").strip():
                out.append(f"items[{iid}].ui.fields[{fname}] 缺 label")
            if not (f.get("required") or str(f.get("rule") or "").strip()):
                out.append(f"items[{iid}].ui.fields[{fname}] 既不必填也没有 rule —— "
                           "那它的输入约束是什么?")
            if f.get("required") and not str(f.get("on_invalid") or "").strip():
                out.append(f"items[{iid}].ui.fields[{fname}] 必填却没写 on_invalid —— "
                           "用户填错了会看到什么?")

        out.extend(ui_surface.action_findings(iid, actions))

        if fields and not actions:
            out.append(f"items[{iid}].ui 有 {len(fields)} 个输入项但没有 action —— "
                       "填完之后呢?")

        # 状态三连最常漏 loading 和 error，而它们正是线上问题的多发地。
        states = ui.get("states") if isinstance(ui.get("states"), dict) else {}
        if actions and not states.get("loading"):
            out.append(f"items[{iid}].ui.states 缺 loading —— "
                       "请求在路上时界面是什么样?(重复提交就在这里发生)")
        if actions and not states.get("error"):
            out.append(f"items[{iid}].ui.states 缺 error —— 请求失败时界面是什么样?")
    out.extend(ui_surface.same_name(items))


def to_spec(feature: str, items: list) -> dict:
    """A json-render flat spec: root + elements{type, props, children}.

    Semantic types only (screen / form / field / action / state-note), so a
    product maps them onto its own catalog — element-ui, shadcn, whatever it
    already ships. Choosing components here would make the kernel carry a
    product asset.
    """
    elements: dict[str, dict] = {}
    screens: dict[str, list[str]] = {}

    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("ui"), dict):
            continue
        iid = str(item.get("id", "?"))
        ui = item["ui"]
        screen = str(ui.get("screen") or "未命名界面")
        sid = "screen_" + re.sub(r"\W+", "_", screen)
        if sid not in elements:
            elements[sid] = {"type": "screen", "props": {"title": screen}, "children": []}
            screens[sid] = elements[sid]["children"]

        gid = f"group_{iid}"
        elements[gid] = {
            "type": "requirement",
            "props": {
                "baseline_item_id": iid,
                "must": str(item.get("must") or ""),
                "acceptance": str(item.get("acceptance") or ""),
                "intent": str(ui.get("intent") or ""),
            },
            "children": [],
        }
        screens[sid].append(gid)

        for n, f in enumerate(safeyaml.as_list(ui.get("fields"))):
            if not isinstance(f, dict):
                continue
            fid = f"field_{iid}_{n}"
            elements[fid] = {
                "type": "field",
                "props": {
                    "name": f.get("name"), "label": f.get("label"),
                    "inputType": f.get("type") or "text",
                    "required": bool(f.get("required")),
                    "rule": f.get("rule") or "",
                    "onInvalid": f.get("on_invalid") or "",
                },
                "children": [],
            }
            elements[gid]["children"].append(fid)

        for n, a in enumerate(safeyaml.as_list(ui.get("actions"))):
            if not isinstance(a, dict):
                continue
            aid = f"action_{iid}_{n}"
            elements[aid] = {
                "type": "action",
                "props": {
                    "name": a.get("name"), "primary": bool(a.get("primary")),
                    "onSuccess": a.get("on_success") or "",
                    "onFailure": a.get("on_failure") or "",
                    "onPending": a.get("on_pending") or "",
                },
                "children": [],
            }
            elements[gid]["children"].append(aid)

        states = ui.get("states") if isinstance(ui.get("states"), dict) else {}
        for key, text in states.items():
            nid = f"state_{iid}_{key}"
            elements[nid] = {"type": "state-note",
                             "props": {"state": key, "describes": str(text)},
                             "children": []}
            elements[gid]["children"].append(nid)

        if ui.get("a11y"):
            nid = f"a11y_{iid}"
            elements[nid] = {"type": "a11y-note",
                             "props": {"describes": str(ui["a11y"])}, "children": []}
            elements[gid]["children"].append(nid)

    root = "root"
    elements[root] = {"type": "document",
                      "props": {"feature": feature, "source": "baseline.yaml#ui"},
                      "children": sorted(screens)}
    return {"format": "json-render/flat@1", "root": root, "elements": elements}


def to_html(feature: str, spec: dict, revision: int) -> str:
    """A zero-dependency preview. No build step, opens in a browser."""
    el = spec["elements"]
    e = html.escape

    def render(nid: str, depth: int = 0) -> str:
        node = el.get(nid) or {}
        t = node.get("type")
        p = node.get("props") or {}
        kids = "".join(render(k, depth + 1) for k in node.get("children") or [])

        if t == "screen":
            return f'<section class="screen"><h2>{e(str(p.get("title")))}</h2>{kids}</section>'
        if t == "requirement":
            acc = f'<div class="acc">验收:{e(str(p.get("acceptance")))}</div>' if p.get("acceptance") else ""
            return (f'<article class="req"><header><code>{e(str(p.get("baseline_item_id")))}</code>'
                    f'<strong>{e(str(p.get("must")))}</strong></header>'
                    f'<div class="intent">用户目的:{e(str(p.get("intent")))}</div>{acc}{kids}</article>')
        if t == "field":
            req = '<span class="req-mark">*</span>' if p.get("required") else ""
            rule = f'<div class="rule">约束:{e(str(p.get("rule")))}</div>' if p.get("rule") else ""
            inv = (f'<div class="invalid">填错时:{e(str(p.get("onInvalid")))}</div>'
                   if p.get("onInvalid") else "")
            return (f'<div class="field"><label>{e(str(p.get("label")))}{req}</label>'
                    f'<input type="{e(str(p.get("inputType")))}" disabled '
                    f'placeholder="{e(str(p.get("inputType")))}">{rule}{inv}</div>')
        if t == "action":
            cls = "btn primary" if p.get("primary") else "btn"
            rows = "".join(
                f'<div class="outcome"><span>{lbl}</span>{e(str(p.get(k)))}</div>'
                for k, lbl in (("onSuccess", "成功"), ("onFailure", "失败"), ("onPending", "进行中"))
                if p.get(k))
            return f'<div class="action"><button class="{cls}" disabled>{e(str(p.get("name")))}</button>{rows}</div>'
        if t == "state-note":
            return (f'<div class="state"><span>{e(str(p.get("state")))}</span>'
                    f'{e(str(p.get("describes")))}</div>')
        if t == "a11y-note":
            return f'<div class="a11y">可达性:{e(str(p.get("describes")))}</div>'
        return kids

    body = render(spec["root"])
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>{e(feature)} — 需求交互预览</title>
<style>
 body{{font:14px/1.7 -apple-system,"PingFang SC",sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1f2328}}
 .banner{{background:#fff8c5;border:1px solid #e9db5d;padding:.75rem 1rem;border-radius:6px;margin-bottom:1.5rem}}
 .screen{{border:1px solid #d0d7de;border-radius:8px;padding:1rem 1.25rem;margin:1.5rem 0}}
 .screen>h2{{margin:0 0 1rem;font-size:1.1rem;border-bottom:1px solid #eaeef2;padding-bottom:.5rem}}
 .req{{border-left:3px solid #0969da;padding:.5rem 0 .5rem 1rem;margin:1rem 0}}
 .req header{{display:flex;gap:.5rem;align-items:baseline;flex-wrap:wrap}}
 .req code{{background:#eaeef2;padding:.1rem .4rem;border-radius:4px;font-size:.85em}}
 .intent{{color:#656d76;font-size:.9em;margin:.25rem 0}}
 .acc{{color:#1a7f37;font-size:.9em;margin:.25rem 0}}
 .field{{margin:.75rem 0;padding:.5rem;background:#f6f8fa;border-radius:6px}}
 .field label{{display:block;font-weight:600;margin-bottom:.25rem}}
 .field input{{width:100%;padding:.4rem;border:1px solid #d0d7de;border-radius:4px;background:#fff}}
 .req-mark{{color:#cf222e;margin-left:.2rem}}
 .rule,.invalid{{font-size:.85em;margin-top:.3rem}}
 .rule{{color:#656d76}} .invalid{{color:#cf222e}}
 .action{{margin:.75rem 0}}
 .btn{{padding:.4rem 1rem;border:1px solid #d0d7de;border-radius:6px;background:#f6f8fa}}
 .btn.primary{{background:#1f883d;color:#fff;border-color:#1f883d}}
 .outcome{{font-size:.85em;color:#656d76;margin:.3rem 0 0 .5rem}}
 .outcome span{{display:inline-block;min-width:3.5em;color:#1f2328;font-weight:600}}
 .state{{font-size:.85em;color:#656d76;margin:.3rem 0}}
 .state span{{display:inline-block;min-width:4.5em;font-weight:600;color:#9a6700}}
 .a11y{{font-size:.85em;color:#8250df;margin:.3rem 0}}
</style></head><body>
<div class="banner"><strong>这是从 baseline.yaml 的 ui 规则生成的预览,不是实现。</strong><br>
验收的尺是 <code>baseline.yaml</code>(revision {revision});这一页只是把它的交互规则画出来便于评审。<br>
基线一变就重新生成 —— 不要手改这个文件,改动会在下次生成时丢失。</div>
{body}
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--feature")
    parser.add_argument("--out", type=Path, help="override the output directory")
    parser.add_argument("--check", action="store_true", help="only validate the ui rules")
    parser.add_argument("--schema", action="store_true", help="print the ui block schema")
    args = parser.parse_args()

    if args.schema:
        print(SCHEMA)
        return 0
    if not args.feature:
        parser.error("--feature is required unless --schema")

    repo = args.repo or (Path(os.environ["IDEV_PRODUCT_REPO"])
                         if os.environ.get("IDEV_PRODUCT_REPO") else Path.cwd())
    home = doc_home.homes(repo.resolve(), args.feature)["task"]
    if not home.is_dir():
        print(f"BLOCKED no ticket home at {home}", file=sys.stderr)
        return 2

    baseline = safeyaml.mapping(home / "baseline.yaml")
    if baseline is None:
        print(f"BLOCKED cannot read {home / 'baseline.yaml'}", file=sys.stderr)
        return 2

    items = safeyaml.as_list(baseline.get("items"))
    with_ui = [i for i in items if isinstance(i, dict) and isinstance(i.get("ui"), dict)]

    findings: list[str] = []
    check_ui(items, findings)

    print(f"# ui-spec  {args.feature}")
    print(f"# {home / 'baseline.yaml'}  revision={safeyaml.as_int(baseline.get('revision'), 0)}")
    print(f"# {len(with_ui)}/{len(items)} 条 item 有 ui 规则")
    print()

    if findings:
        for f in findings:
            print(f"FAIL {f}")
        print()
        print(f"ui-spec FAIL  {len(findings)} 处")
        print()
        print("交互规则要细到「用户填错会看到什么」「请求在路上时界面什么样」这一层 ——")
        print("这些地方说不清,实现阶段就会各自发挥,测试阶段就没有尺可量。")
        print("schema 见 --schema。")
        return 1

    if not with_ui:
        print("ui-spec PASS  没有 item 带 ui 规则")
        print()
        print("涉及界面的需求建议补上 ui 块(--schema 看格式):把交互细到字段校验、")
        print("动作结果、加载与失败状态,评审时才看得见分歧。")
        return 0

    out_dir = (args.out or (home / "ui")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = to_spec(args.feature, items)
    rev = safeyaml.as_int(baseline.get("revision"), 0)

    spec_path = out_dir / f"{args.feature}.spec.json"
    html_path = out_dir / f"{args.feature}.html"
    if not args.check:
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        html_path.write_text(to_html(args.feature, spec, rev), encoding="utf-8")

    screens = sum(1 for v in spec["elements"].values() if v.get("type") == "screen")
    fields = sum(1 for v in spec["elements"].values() if v.get("type") == "field")
    actions = sum(1 for v in spec["elements"].values() if v.get("type") == "action")
    print(f"ui-spec PASS  {screens} 个界面 / {fields} 个输入项 / {actions} 个动作")
    if not args.check:
        print()
        print(f"  {spec_path}")
        print(f"  {html_path}")
        print()
        print("spec 是 json-render 的 flat 格式(root + elements),语义类型为")
        print("screen / requirement / field / action / state-note —— 产线用自己的")
        print("catalog 映射到 element-ui / shadcn 等既有组件库,内核不选组件。")
        print()
        print("**html 是预览,不是实现,也不是尺。** 验收的尺是 baseline.yaml;")
        print("基线一变就重新生成,不要手改那个文件。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
