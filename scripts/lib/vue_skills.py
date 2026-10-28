"""Vendored vuejs-ai skills. Session entry prints which ones to open."""
from __future__ import annotations

import os
import re
from pathlib import Path

from roots import kernel_root

# open: read for this stage. if: read only when this round touches that subject.
STAGE_SKILLS: dict[str, tuple[tuple[str, str], ...]] = {
    "req-review": (
        ("open", "vue-best-practices"),
        ("if", "create-adaptable-composable"),
    ),
    "req": (
        ("open", "vue-best-practices"),
        ("if", "create-adaptable-composable"),
    ),
    "arch": (
        ("open", "vue-best-practices"),
        ("if", "create-adaptable-composable"),
    ),
    "code": (
        ("open", "vue-best-practices"),
        ("open", "vue-testing-best-practices"),
        ("if", "vue-pinia-best-practices"),
        ("if", "vue-router-best-practices"),
        ("if", "vue-options-api-best-practices"),
        ("if", "vue-jsx-best-practices"),
        ("if", "create-adaptable-composable"),
    ),
    "test": (("open", "vue-testing-best-practices"),),
    "verify-plan": (("open", "vue-testing-best-practices"),),
    "ops": (
        ("open", "vue-debug-guides"),
        ("open", "vue-best-practices"),
    ),
}

_SKIP = {"node_modules", ".git", "dist", "target", "vendor", "build", "out"}
_VUE_DEP = re.compile(r'"vue"|"@vue/')


def router_page() -> Path:
    return kernel_root() / "conventions" / "vue.md"


def skill_file(name: str) -> Path | None:
    """Kernel copy first. A machine-local install is only a fallback."""
    vendored = kernel_root() / "skills" / "vue" / name / "SKILL.md"
    if vendored.is_file():
        return vendored
    home = Path.home()
    for base in (home / ".cursor" / "skills", home / ".agents" / "skills"):
        alt = base / name / "SKILL.md"
        if alt.is_file():
            return alt
    return None


def is_vue_repo(repo: Path) -> bool:
    """True when the tree has a Vue dependency or a .vue file. Depth is capped."""
    root = repo.resolve()
    if not root.is_dir():
        return False
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if rel.parts and rel.parts[0] == "skills":
            dirnames[:] = []
            continue
        depth = len(rel.parts)
        if depth > 6:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _SKIP]
        if any(name.endswith(".vue") for name in filenames):
            return True
        if "package.json" in filenames:
            try:
                text = (Path(dirpath) / "package.json").read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _VUE_DEP.search(text):
                return True
    return False


def lines(repo: Path, stage: str) -> list[str]:
    """Printable VUE lines. Empty when this repo is not a Vue tree."""
    if not is_vue_repo(repo):
        return []
    out = ["VUE router %s" % router_page()]
    rows = STAGE_SKILLS.get(stage.strip())
    if not rows:
        out.append("VUE stage NONE")
        return out
    for mode, name in rows:
        path = skill_file(name)
        if path is None:
            out.append("VUE MISSING %s" % name)
        else:
            out.append("VUE %s %s %s" % (mode, name, path))
    return out
