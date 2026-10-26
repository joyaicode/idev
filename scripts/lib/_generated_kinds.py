#!/usr/bin/env python3
"""The kind table, generated. Edit registry/kinds.yaml instead.

Kept as Python so the migration-era scripts keep one import shape while
the Go side reads the same registry/kinds.yaml directly.
"""
from __future__ import annotations

# Generated from registry/kinds.yaml by scripts/gen-kinds.py. Do not edit.

KINDS: dict[str, str] = {
    "preflight.inputs": "scripts/s8-preflight.sh",
    "human.gate": "references/chat-confirm-signoff.md",
    "shell.confirmed": "-",
    "tool.step": "references/workflow-schema.md",
    "ui.clean_pass_loop": "-",
    "ui.product_batch": "-",
    "route.s4": "conventions/SKILL.md",
    "deliver.advance": "deliver/SKILL.md",
    "deliver.code_pass": "deliver/SKILL.md",
    "docs.backfill": "docs/SKILL.md",
    "docs.changelog": "docs/SKILL.md",
    "review.report": "conventions/coding.md",
    "review.fix": "conventions/coding.md",
    "verify.plan": "verify/SKILL.md",
    "verify.run": "verify/SKILL.md",
    "ops.classify": "ops/SKILL.md",
    "localdev.start": "workflow-defaults.yaml commands.start",
    "localdev.stop": "workflow-defaults.yaml commands.stop",
    "localdev.approval_off": "workflow-defaults.yaml commands.approval_off",
    "ui.lifecycle_run": "workflow-defaults.yaml commands.lifecycle",
    "ui.surface_scan": "scripts/ui-surface-scan.py",
    "ui.coverage_lock": "scripts/ui-coverage-check.py",
    "ui.playbook_sync": "conventions/coding.md",
    "ui.fix_deposit": "conventions/evidence.md",
    "frontend.lint_fix": "workflow-defaults.yaml commands.lint_fix",
    "java.build": "-",
    "git.replace_check": "-",
    "git.sensitive_shield": "references/workflow-repo-commit.md",
    "git.sensitive_restore": "references/workflow-repo-commit.md",
    "git.commit_push": "references/workflow-repo-commit.md",
}

KIND_AGENTS: dict[str, str] = {
    "preflight.inputs": "-",
    "human.gate": "-",
    "shell.confirmed": "-",
    "tool.step": "-",
    "ui.clean_pass_loop": "-",
    "ui.product_batch": "-",
    "route.s4": "idev-ops",
    "deliver.advance": "idev-deliver",
    "deliver.code_pass": "idev-coder",
    "docs.backfill": "idev-deliver",
    "docs.changelog": "idev-deliver",
    "review.report": "idev-reviewer",
    "review.fix": "idev-coder",
    "verify.plan": "idev-verifier",
    "verify.run": "idev-verifier",
    "ops.classify": "idev-ops",
    "localdev.start": "idev-verifier",
    "localdev.stop": "idev-verifier",
    "localdev.approval_off": "idev-verifier",
    "ui.lifecycle_run": "idev-verifier",
    "ui.surface_scan": "idev-verifier",
    "ui.coverage_lock": "idev-verifier",
    "ui.playbook_sync": "idev-coder",
    "ui.fix_deposit": "idev-ops",
    "frontend.lint_fix": "idev-coder",
    "java.build": "idev-coder",
    "git.replace_check": "idev-coder",
    "git.sensitive_shield": "idev-coder",
    "git.sensitive_restore": "idev-coder",
    "git.commit_push": "idev-coder",
}

KIND_COMMANDS: dict[str, str] = {
    "ui.clean_pass_loop": "commands.lifecycle",
    "localdev.start": "commands.start",
    "localdev.stop": "commands.stop",
    "localdev.approval_off": "commands.approval_off",
    "ui.lifecycle_run": "commands.lifecycle",
    "frontend.lint_fix": "commands.lint_fix",
}

# Leases: write touches product code, verify only ticket artefacts.
KIND_LEASE: dict[str, str] = {
    "preflight.inputs": "none",
    "human.gate": "none",
    "shell.confirmed": "none",
    "tool.step": "none",
    "ui.clean_pass_loop": "none",
    "ui.product_batch": "none",
    "route.s4": "verify",
    "deliver.advance": "write",
    "deliver.code_pass": "write",
    "docs.backfill": "write",
    "docs.changelog": "write",
    "review.report": "verify",
    "review.fix": "write",
    "verify.plan": "verify",
    "verify.run": "verify",
    "ops.classify": "verify",
    "localdev.start": "verify",
    "localdev.stop": "verify",
    "localdev.approval_off": "verify",
    "ui.lifecycle_run": "verify",
    "ui.surface_scan": "verify",
    "ui.coverage_lock": "verify",
    "ui.playbook_sync": "write",
    "ui.fix_deposit": "verify",
    "frontend.lint_fix": "write",
    "java.build": "write",
    "git.replace_check": "write",
    "git.sensitive_shield": "write",
    "git.sensitive_restore": "write",
    "git.commit_push": "write",
}

# A PASS here needs a second agent's confirmation (design I-2).
KIND_VERIFIER: dict[str, str] = {
    "deliver.code_pass": "idev-reviewer",
    "review.fix": "idev-reviewer",
    "ui.playbook_sync": "idev-reviewer",
    "frontend.lint_fix": "idev-reviewer",
    "git.replace_check": "idev-reviewer",
}

FORBIDDEN: set[str] = {'auto.accepted', 'auto.seal', 'multi.module.load', 'skip.signoff'}
LEGACY_KINDS: set[str] = {'ui.product_batch'}
GATE_KINDS: set[str] = {'human.gate'}
REQUIRES_GATE_BEFORE: set[str] = {'git.commit_push'}

AGENTS: tuple = (
    "idev-deliver",
    "idev-coder",
    "idev-reviewer",
    "idev-verifier",
    "idev-ops",
)

FACTS_AGENTS: tuple = ('idev-coder', 'idev-reviewer', 'idev-verifier', 'idev-ops')
BOOST_AGENTS: tuple = ('idev-coder', 'idev-verifier', 'idev-ops')
S0_AGENTS: tuple = ('idev-coder',)

# coding.md §0 is written for one agent. Kept singular because four
# call sites compare against a name, not a membership.
S0_AGENT = 'idev-coder'

READONLY_BREAKS: dict[str, str] = {
    "idev-deliver": "写票 YAML、规格与产线文档",
    "idev-coder": "改代码、跑构建与 git commit",
    "idev-reviewer": "写 review.md",
    "idev-verifier": "写 plan.yaml、report.md,启停本地服务",
    "idev-ops": "写 ops.yaml、假设台账与 lessons",
}
