#!/usr/bin/env python3
"""verify-plan when the recipe does not create a baseline.

A recipe with needs_ticket: false does not build deliver.yaml or a sealed
baseline. When the ticket's current run points at such a recipe and
baseline.yaml is absent, verify-plan does not require sealed, and cases
need not carry baseline_item_id. A baseline file that exists is still sealed
or the check fails.
"""
from __future__ import annotations

from pathlib import Path

import safeyaml


def skips_baseline(task_home: Path) -> bool:
    if (task_home / "baseline.yaml").is_file():
        return False
    run = safeyaml.mapping(task_home / "workflow" / "run.yaml")
    if not run:
        return False
    recipe = str(run.get("recipe") or "").strip()
    if not recipe:
        return False
    data = safeyaml.mapping(Path(recipe).expanduser())
    if not data:
        return False
    return data.get("needs_ticket") is False
