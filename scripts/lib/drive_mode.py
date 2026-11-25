"""Resolve and persist idev drive_mode (assisted | auto).

Priority: session override → product workflow-defaults → default assisted.
Session file is execution residue (untracked). Product default is durable.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from pathlib import Path
from typing import Any

MODES = ("assisted", "auto")
DEFAULT_MODE = "assisted"

# Never auto-decide these. Same words as process-eval hard holds.
HARD_HOLDS = (
    "解封",
    "解除密封",
    "启封",
    "开封",
    "unseal",
    "打开基线",
    "重新打开基线",
    "打開基線",  # traditional
    "重新打開基線",
    "reopen",
    "回退",
    "回滚",  # synonym of 回退
    "rollback",
    "roll back",
    "promote",  # case-insensitive via hard_held
    # Align with chat-confirm「生产写」— bare「生产」误伤「非生产」。
    "生产写",
    "写入生产",
    "写生产",
    "上生产",
    "上线生产",
    "生产发布",
    "发布到生产",
    "生产变更",
    "write to production",
    "production write",
    "deploy to production",
    "生產寫",  # traditional
    "寫入生產",
    "寫生產",
    "上生產",
    "上線生產",
    "生產發布",
    "發布到生產",
    "生產變更",
    "git push",
    "经验入库",
    "經驗入庫",  # traditional
)

# Unseal/reopen words, a named subset of HARD_HOLDS. Under solo_e2e the
# person already said reopen needs no ask, so these may be auto-decided
# with a recommendation. Everything else in HARD_HOLDS stays held.
SOLO_RELAXABLE_HOLDS = (
    "解封",
    "解除密封",
    "启封",
    "开封",
    "unseal",
    "打开基线",
    "重新打开基线",
    "打開基線",  # traditional
    "重新打開基線",
    "reopen",
)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def _load_yaml(path: Path) -> dict:
    if yaml is None or not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return data if isinstance(data, dict) else {}


def _dump_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is None:
        # Minimal writer when PyYAML is absent.
        lines = [f"{k}: {data[k]}\n" for k in data]
        path.write_text("".join(lines), encoding="utf-8")
        return
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _as_product_repo(repo: Path | None) -> Path | None:
    """None when there is no product, or when repo is the idev kernel itself."""
    if repo is None:
        return None
    from roots import inside, kernel_root  # noqa: WPS433

    try:
        resolved = repo.expanduser().resolve()
    except OSError:
        return None
    if inside(resolved, kernel_root()):
        return None
    return resolved


def session_path(repo: Path | None, kernel_state: Path | None = None) -> Path:
    product = _as_product_repo(repo)
    if product is not None:
        return product / ".idev" / "drive-mode.yaml"
    if kernel_state is None:
        from roots import kernel_root  # noqa: WPS433

        kernel_state = kernel_root() / "state"
    return kernel_state / "drive-mode.yaml"


def defaults_path(repo: Path | None) -> Path | None:
    product = _as_product_repo(repo)
    if product is None:
        return None
    from product_marker import resolve_extension_repo  # noqa: WPS433

    pages, _err = resolve_extension_repo(product)
    if pages is None:
        return None
    path = pages / ".idev" / "workflow-defaults.yaml"
    return path if path.is_file() else None


def normalize(mode: str) -> str:
    text = _normalize_text(mode).strip().lower()
    if text in {"on", "automatic", "自动", "自动模式", "自動", "自動模式"}:
        return "auto"
    if text in {"off", "manual", "assisted", "非自动", "非自動", "协助", "協助"}:
        return "assisted"
    if text not in MODES:
        raise ValueError(f"drive_mode must be assisted|auto, got {mode!r}")
    return text


# Longest first — multi-char phrases before single 不/无/没/….
_CJK_NEGATION_PREFIXES = (
    "不涉及",
    "不需要",
    "无需再",
    "永不再",
    "并不是",
    "没办法",
    "沒辦法",  # traditional
    "用不着",
    "犯不着",
    "不至于",
    "不至於",
    "禁止",
    "避免",
    "拒绝",
    "反对",
    "取消",
    "跳过",
    "忽略",
    "切莫",
    "莫要",
    "暂缓",
    "推迟",
    "延后",
    "无法",
    "無法",  # traditional
    "无需",
    "無需",
    "无须",
    "無須",
    "毋须",
    "毋庸",
    "未尝",
    "不用",
    "不必",
    "不要",
    "不会",
    "不會",
    "不再",
    "不是",
    "不该",
    "不該",
    "不应",
    "不應",
    "不宜",
    "不可",
    "未能",
    "未曾",
    "未有",
    "没有",
    "沒有",
    "没法",
    "沒法",
    "永不",
    "不",
    "无",
    "無",
    "勿",
    "别",
    "別",
    "非",
    "未",
    "没",
    "沒",
    "莫",
    "慎",
    "拒",
)
_ASCII_NEGATION_PREFIX = (
    r"(?:do\s+not|does\s+not|doesn't|doesnt|did\s+not|didn't|didnt|"
    r"won't|wont|cannot|can't|cant|without|never|avoid|no|not)"
)
# ASCII-only edges so「准备git push」still matches (Unicode \b treats CJK as \w).
_ASCII_EDGE_L = r"(?<![A-Za-z0-9_])"
_ASCII_EDGE_R = r"(?![A-Za-z0-9_])"
# ZWSP / ZWNJ / ZWJ / word-joiner / BOM / soft hyphen — break glued CJK otherwise.
_FORMAT_CHARS = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
# Trad → simp for hold/quote tokens so mixed「生产寫」「打开基線」still match.
_TRAD_TO_SIMP = str.maketrans({
    "開": "开", "線": "线", "產": "产", "寫": "写", "發": "发",
    "經": "经", "驗": "验", "庫": "库", "衝": "冲", "決": "决",
    "議": "议", "無": "无", "沒": "没", "該": "该", "應": "应",
    "別": "别", "於": "于", "會": "会", "辦": "办", "絕": "绝",
    "對": "对", "啟": "启", "關": "关", "閉": "闭", "動": "动",
    "協": "协", "聽": "听", "這": "这", "個": "个", "薦": "荐",
    "暫": "暂", "緩": "缓", "遲": "迟", "後": "后", "過": "过",
    "並": "并", "與": "与", "為": "为", "從": "从", "當": "当",
    "麼": "么", "見": "见", "貝": "贝", "頁": "页", "風": "风",
    "滾": "滚",
})


def _normalize_text(blob: str) -> str:
    """NFKC, drop zero-width chars, map trad→simp for hold/quote matching."""
    text = unicodedata.normalize("NFKC", str(blob or ""))
    text = _FORMAT_CHARS.sub("", text)
    return text.translate(_TRAD_TO_SIMP)


def _squeeze_cjk_spaces(blob: str) -> str:
    """Drop whitespace that only sits between non-ASCII chars (生产 写 → 生产写)."""
    return re.sub(r"(?<=[^\x00-\x7F])\s+(?=[^\x00-\x7F])", "", str(blob or ""))


def _strip_cjk_phrase(cleaned: str, phrase: str, prefix: str) -> str:
    """Remove phrase occurrences, keeping A不A embeds (要不要回退 / 会不会…)."""
    if phrase not in cleaned:
        return cleaned
    # Prefixes starting with 不 can sit inside「X不X…」(要不要回退).
    # When the char before 不 equals the char after 不, keep that hit.
    if not (prefix.startswith("不") and len(prefix) >= 2):
        return cleaned.replace(phrase, "")
    parts: list[str] = []
    idx = 0
    while True:
        pos = cleaned.find(phrase, idx)
        if pos < 0:
            parts.append(cleaned[idx:])
            break
        if (
            pos > 0
            and pos + 1 < len(cleaned)
            and cleaned[pos - 1] == cleaned[pos + 1]
        ):
            parts.append(cleaned[idx : pos + len(phrase)])
            idx = pos + len(phrase)
            continue
        parts.append(cleaned[idx:pos])
        idx = pos + len(phrase)
    return "".join(parts)


def _strip_cjk_negations(blob: str, marks: tuple[str, ...] | list[str]) -> str:
    """Remove CJK negation+mark phrases (longest marks/prefixes first)."""
    cleaned = blob
    prefixes = sorted(_CJK_NEGATION_PREFIXES, key=len, reverse=True)
    for mark in sorted(
        (m for m in marks if not str(m).isascii()),
        key=len,
        reverse=True,
    ):
        for prefix in prefixes:
            cleaned = _strip_cjk_phrase(cleaned, prefix + mark, prefix)
    return cleaned


def _strip_cjk_before_ascii(blob: str, marks: tuple[str, ...] | list[str]) -> str:
    """Remove CJK negation before ASCII marks (不必 promote / 不要reopen)."""
    cleaned = blob
    prefixes = sorted(_CJK_NEGATION_PREFIXES, key=len, reverse=True)
    for mark in (m for m in marks if str(m).isascii()):
        mark_pat = re.escape(str(mark)).replace(r"\ ", r"\s+")
        for prefix in prefixes:
            pattern = re.compile(
                rf"{re.escape(prefix)}\s*{mark_pat}{_ASCII_EDGE_R}",
                re.I,
            )
            parts: list[str] = []
            idx = 0
            for match in pattern.finditer(cleaned):
                pos = match.start()
                if (
                    prefix.startswith("不")
                    and len(prefix) >= 2
                    and pos > 0
                    and pos + 1 < len(cleaned)
                    and cleaned[pos - 1] == cleaned[pos + 1]
                ):
                    continue
                parts.append(cleaned[idx:pos])
                idx = match.end()
            parts.append(cleaned[idx:])
            cleaned = "".join(parts)
    return cleaned


def _ascii_mark_pattern(mark: str) -> str:
    """Case-insensitive ASCII mark with ASCII-only word edges and flexible spaces."""
    mark_pat = re.escape(str(mark)).replace(r"\ ", r"\s+")
    return rf"(?i){_ASCII_EDGE_L}{mark_pat}{_ASCII_EDGE_R}"


def _strip_ascii_negations(blob: str, marks: tuple[str, ...] | list[str]) -> str:
    """Remove English negation+mark phrases (no promote / do not reopen / …)."""
    cleaned = blob
    for mark in (m for m in marks if str(m).isascii()):
        mark_pat = re.escape(str(mark)).replace(r"\ ", r"\s+")
        cleaned = re.sub(
            rf"(?i){_ASCII_EDGE_L}{_ASCII_NEGATION_PREFIX}\s+{mark_pat}{_ASCII_EDGE_R}",
            "",
            cleaned,
        )
    return cleaned


def _strip_hold_negations(blob: str, marks: tuple[str, ...] | list[str]) -> str:
    cleaned = _squeeze_cjk_spaces(_normalize_text(blob))
    cleaned = _strip_cjk_negations(cleaned, marks)
    cleaned = _strip_cjk_before_ascii(cleaned, marks)
    return _strip_ascii_negations(cleaned, marks)


def hard_held(*parts: str, relax_solo: bool = False) -> bool:
    """True when any part contains an irreversible hold marker.

    ASCII markers (promote, reopen, git push, …) match as whole phrases,
    case-insensitively with ASCII-only edges — so Promote/Reopen /
    ｐｒｏｍｏｔｅ / 「准备git push」hard-stop, but promotion /
    「no promote」do not. CJK markers stay exact substring after NFKC,
    dropping zero-width chars, squeezing CJK-internal spaces, and
    stripping negation+mark phrases (不​回退 / 生产 写 / 不必 promote).

    relax_solo=True drops the SOLO_RELAXABLE_HOLDS (unseal/reopen) marks
    from matching — used only when solo_e2e() already said the person
    holds every role and chose drive_mode=auto. The rest of HARD_HOLDS
    (回退/promote/生产写/push/经验入库) never relax.
    """
    blob = "\n".join(str(p or "") for p in parts)
    marks = HARD_HOLDS
    if relax_solo:
        marks = tuple(m for m in HARD_HOLDS if m not in SOLO_RELAXABLE_HOLDS)
    cleaned = _strip_hold_negations(blob, marks)
    for mark in marks:
        if not mark.isascii():
            if mark in cleaned:
                return True
            continue
        if re.search(_ascii_mark_pattern(mark), cleaned):
            return True
    return False


def hard_held_signal(signal: str, relax_solo: bool = False) -> bool:
    """True when one signal is an irreversible hold (not a [承重] assumption)."""
    text = _normalize_text(signal).strip()
    if not text or text.startswith("[承重]"):
        return False
    return hard_held(text, relax_solo=relax_solo)


def hard_held_signals(signals: list[str], relax_solo: bool = False) -> bool:
    """True when any non-[承重] signal contains an irreversible hold keyword.

    Load-bearing assumptions often mention 生产/回退 as domain context; those
    are decided via recommend, not blocked by substring hard holds.
    """
    return any(hard_held_signal(s, relax_solo=relax_solo) for s in signals)


def resolve(repo: Path | None, kernel_state: Path | None = None) -> tuple[str, str]:
    """Return (mode, source) where source is session|product|default."""
    sess = session_path(repo, kernel_state)
    data = _load_yaml(sess)
    raw = data.get("mode")
    if raw:
        try:
            return normalize(str(raw)), "session"
        except ValueError:
            pass
    defaults = defaults_path(repo)
    if defaults is not None:
        payload = _load_yaml(defaults)
        raw = payload.get("drive_mode")
        if raw:
            try:
                return normalize(str(raw)), "product"
            except ValueError:
                pass
    return DEFAULT_MODE, "default"


def set_mode(repo: Path | None, mode: str, by: str = "", kernel_state: Path | None = None) -> Path:
    path = session_path(repo, kernel_state)
    payload: dict[str, Any] = {
        "mode": normalize(mode),
        "set_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if by.strip():
        payload["set_by"] = by.strip()
    _dump_yaml(path, payload)
    return path


def clear(repo: Path | None, kernel_state: Path | None = None) -> Path | None:
    path = session_path(repo, kernel_state)
    if path.is_file():
        path.unlink()
        return path
    return None


def format_line(mode: str, source: str) -> str:
    return f"DRIVE mode={mode} source={source}"


def solo_e2e(repo: Path | None = None, kernel_state: Path | None = None) -> bool:
    """True when one person holds every role and chose drive_mode=auto.

    The solo end-to-end lane: the person said stage confirmations are not
    stops, so mid-chain gates record AUTO under the same machine checks
    and only the FINAL_REVIEW after done still asks. Both axes are
    existing pieces — staffing.mode and drive_mode — so this adds no
    third mode. Anything else (collaborative, unassigned, assisted)
    keeps the current rules.
    """
    try:
        import staffing  # noqa: WPS433

        staff = staffing.resolve(repo, git_name=staffing.git_user())
        if staff.mode != "solo":
            return False
    except Exception:
        return False
    mode, _source = current(repo, kernel_state)
    return mode == "auto"


def current(repo: Path | None = None, kernel_state: Path | None = None) -> tuple[str, str]:
    """Resolve against cwd product when repo is omitted."""
    if repo is None:
        try:
            from product_sink import product_repo  # noqa: WPS433

            repo = product_repo()
        except Exception:
            repo = None
    if kernel_state is None:
        from roots import kernel_root  # noqa: WPS433

        kernel_state = kernel_root() / "state"
    return resolve(repo, kernel_state)


def signal_guide(mode: str | None = None, step: str = "", feature: str = "") -> str:
    """One-line next action after a SIGNAL / unanswered hold."""
    if mode is None:
        mode, _source = current()
    if mode == "auto":
        decide = "workflow.py decide"
        if step:
            decide += f" {step}"
        decide += " --all-open --source auto --recommend <档>"
        if feature and feature != "-":
            decide += f" --feature {feature}"
        return (
            "drive=auto: stamp RECOMMEND (or PASS+[承重] defaults to 1), then "
            f"process-eval stop --recommend <档> and {decide} "
            "(by=staffed human; hard holds still ask)"
        )
    return "ask the person; record the answer with workflow.py decide"


def decide_hint(step: str, feature: str = "") -> str:
    """Ready CLI skeleton for auto-adopting open signals on a step."""
    line = f"workflow.py decide {step} --all-open --source auto --recommend <档>"
    if feature and feature != "-":
        line += f" --feature {feature}"
    return line


# Report stamps for settle. Bare「建议:」is only for process-eval stop inference
# (loose=True); prose tips must not become auto-decide answers.
# Leading horizontal space matches workflow line_field / indented reports.
_RECOMMEND_LINE = (
    r"(?mi)^[^\S\n]*(?:RECOMMEND|AI_RECOMMEND|AI\s*建[议議])\s*[:：=＝]\s*(\S+)\s*$"
)
_RECOMMEND_LINE_LOOSE = (
    r"(?mi)^[^\S\n]*(?:RECOMMEND|AI_RECOMMEND|AI\s*建[议議]|建[议議])\s*[:：=＝]\s*(\S+)\s*$"
)
_RECOMMEND_INLINE = (
    r"(?i)(?:\bRECOMMEND\b|\bAI_RECOMMEND\b|AI\s*建[议議])\s*[=:：＝]\s*(\S+)"
)
# ASCII colon only — same contract as workflow REPORT_STATUS / line_field.
_STATUS_LINE = r"(?mi)^[^\S\n]*STATUS:\s*(\S+)"


def _report_blob(raw: str) -> str:
    """Drop zero-width/BOM. No NFKC — STATUS colon stays ASCII-only like workflow."""
    return _FORMAT_CHARS.sub("", str(raw or "")).lstrip("\ufeff")


def _clean_recommend(value: str) -> str:
    """Normalize a stamped recommend token (quotes, notes, trailing punct)."""
    text = _normalize_text(value).strip()
    while text and text[0] in "=":
        text = text[1:].strip()
    for _ in range(2):
        if len(text) < 2:
            break
        paired = (
            (text[0] == text[-1] and text[0] in "\"'`")
            or (text[0] == "“" and text[-1] == "”")
            or (text[0] == "‘" and text[-1] == "’")
            or (text[0] == "（" and text[-1] == "）")
            or (text[0] == "(" and text[-1] == ")")
            or (text[0] == "【" and text[-1] == "】")
        )
        if not paired:
            break
        text = text[1:-1].strip()
    for sep in ("，", ",", ";", "；", "／", "/", "、", "|", "｜"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
    for opener in ("（", "("):
        if opener in text:
            text = text.split(opener, 1)[0].strip()
    while text and text[-1] in "，,;；)）。!?？！…`":
        text = text[:-1].rstrip()
    while text.endswith("..."):
        text = text[:-3].rstrip()
    while text.endswith("."):
        # Option tokens do not end with a period; decimals like 1.0 end in a digit.
        text = text[:-1].rstrip()
    if text.lower() in {"-", "none", "null", "n/a", ""}:
        return ""
    return text


def report_recommend(raw: str, *, loose: bool = False) -> str:
    """Extract a stamped recommend from a report / stop blob, or ''.

    loose=True also accepts a bare「建议:」/「建議:」line (process-eval stop inference).
    Settle keeps loose=False so prose tips do not auto-decide signals.
    """
    text = _report_blob(raw)
    pattern = _RECOMMEND_LINE_LOOSE if loose else _RECOMMEND_LINE
    match = re.search(pattern, text)
    if match is None:
        match = re.search(_RECOMMEND_INLINE, text)
    if match is None:
        return ""
    return _clean_recommend(match.group(1))


def report_status(raw: str) -> str:
    """STATUS token from a report blob (PASS/FAIL/…); strips trailing (notes).

    Colon stays ASCII-only (workflow line_field). Token itself is NFKC'd so
    fullwidth ＰＡＳＳ still settles as PASS.
    """
    match = re.search(_STATUS_LINE, _report_blob(raw))
    if match is None:
        return ""
    token = _normalize_text(match.group(1).split("(", 1)[0]).strip().upper()
    return token


def resolve_signal_recommend(
    raw: str,
    signals: list[str],
    status: str = "",
) -> tuple[str, str]:
    """Return (recommend, quote) for auto-settling open signals.

    Only settles under an explicit PASS (STATUS: line or structured
    report.status). quote is auto:recommend when stamped (RECOMMEND /
    AI 建议 only), auto:default-accept when every open signal is a [承重]
    assumption, else ''. BLOCKED / ARTIFACT / mixed signals still need an
    explicit stamp (and PASS).
    """
    structured = _normalize_text(status).split("(", 1)[0].strip().upper()
    effective = report_status(raw) or structured
    if effective != "PASS":
        return "", ""
    stamped = report_recommend(raw, loose=False)
    if stamped:
        return stamped, "auto:recommend"
    cleaned = [
        item
        for item in (_normalize_text(s).strip() for s in signals)
        if item
    ]
    if not cleaned:
        return "", ""
    if all(item.startswith("[承重]") for item in cleaned):
        return "1", "auto:default-accept"
    return "", ""


def default_signal_recommend(raw: str, signals: list[str], status: str = "") -> str:
    """Recommend value only; see resolve_signal_recommend for the quote tag."""
    return resolve_signal_recommend(raw, signals, status=status)[0]


# Whole-reply phrases that toggle drive_mode. Longer phrases first.
DRIVE_ON = (
    "开启自动模式", "開啟自動模式", "打开自动模式", "打開自動模式",
    "启用自动模式", "啟用自動模式", "自动模式开启", "自動模式開啟",
    "drive auto", "auto on", "开启自动", "開啟自動", "打开自动", "打開自動",
)
DRIVE_OFF = (
    "关闭自动模式", "關閉自動模式", "关掉自动模式", "關掉自動模式",
    "停用自动模式", "停用自動模式", "自动模式关闭", "自動模式關閉",
    "drive assisted", "auto off", "关闭自动", "關閉自動", "关掉自动", "關掉自動",
)


def quote_mode(quote: str) -> str | None:
    """Return auto|assisted when the whole reply only toggles drive_mode."""
    raw = _normalize_text(quote).strip()
    if not raw:
        return None
    text = raw.lower()
    for phrase in DRIVE_ON:
        if raw == phrase or text == phrase.lower():
            return "auto"
    for phrase in DRIVE_OFF:
        if raw == phrase or text == phrase.lower():
            return "assisted"
    return None


def settle_verify_feedback(repo: Path, feature: str) -> Path | None:
    """Write verify/feedback.yaml status:none under drive=auto when still open."""
    mode, _source = current(repo)
    feat = str(feature or "").strip()
    if mode != "auto" or not feat or feat == "-":
        return None
    from doc_home import homes  # noqa: WPS433
    from workflow_spec import is_human  # noqa: WPS433

    try:
        import staffing as staff_mod  # noqa: WPS433
    except Exception:
        staff_mod = None

    ticket = homes(repo, feat)["task"]
    # Do not invent feedback for a ticket that does not exist yet.
    if not ticket.is_dir():
        return None
    path = ticket / "verify" / "feedback.yaml"
    if path.is_file():
        data = _load_yaml(path)
        status = str(data.get("status") or "").strip().lower()
        if status in ("received", "none"):
            return None
        tags = data.get("tags") or []
        if isinstance(tags, list) and any(str(t).strip() for t in tags):
            return None
    by = ""
    if staff_mod is not None:
        name = str(staff_mod.git_user() or "").strip()
        if name and is_human(name):
            by = name
    payload = {
        "schema_version": 1,
        "feature": feat,
        "status": "none",
        "tags": [],
        "by": by,
        "note": "auto:drive-mode; trial feedback deferred",
    }
    wrote = {"ok": False}

    def mutate(data: dict) -> dict:
        status = str(data.get("status") or "").strip().lower()
        if status in ("received", "none"):
            return data
        tags = data.get("tags") or []
        if isinstance(tags, list) and any(str(t).strip() for t in tags):
            return data
        wrote["ok"] = True
        return dict(payload)

    try:
        import safeyaml  # noqa: WPS433

        safeyaml.save_locked(path, mutate)
    except Exception:
        _dump_yaml(path, payload)
        wrote["ok"] = True
    return path if wrote["ok"] else None


_SCOPE_DECISIONS = ("mark", "fix-first")


def settle_scope_debt(repo: Path, feature: str) -> Path | None:
    """Under drive=auto, adopt scope_debt.recommend when decision is still pending.

    Only mark|fix-first. Leaves pending alone when recommend is missing or
    unknown. Does not invent a child ticket id for fix-first. Skips the write
    entirely when there is nothing to adopt (does not rewrite arch.yaml).
    """
    mode, _source = current(repo)
    feat = str(feature or "").strip()
    if mode != "auto" or not feat or feat == "-":
        return None
    from doc_home import homes  # noqa: WPS433

    path = homes(repo, feat)["task"] / "arch.yaml"
    if not path.is_file():
        return None
    preview = _load_yaml(path)
    debt = preview.get("scope_debt") if isinstance(preview, dict) else None
    if not isinstance(debt, dict):
        return None
    decision = str(debt.get("decision") or "").strip().lower()
    recommend = str(debt.get("recommend") or "").strip().lower()
    if decision != "pending" or recommend not in _SCOPE_DECISIONS:
        return None

    adopted = {"ok": False}

    def mutate(data: dict) -> dict:
        current_debt = data.get("scope_debt")
        if not isinstance(current_debt, dict):
            return data
        cur_decision = str(current_debt.get("decision") or "").strip().lower()
        cur_recommend = str(current_debt.get("recommend") or "").strip().lower()
        if cur_decision != "pending" or cur_recommend not in _SCOPE_DECISIONS:
            return data
        updated = dict(current_debt)
        updated["decision"] = cur_recommend
        updated["note"] = "auto:drive-mode; adopted recommend"
        data["scope_debt"] = updated
        adopted["ok"] = True
        return data

    try:
        import safeyaml  # noqa: WPS433

        safeyaml.save_locked(path, mutate)
    except Exception:
        data = _load_yaml(path)
        data = mutate(data if isinstance(data, dict) else {})
        if adopted["ok"]:
            _dump_yaml(path, data)
    return path if adopted["ok"] else None
