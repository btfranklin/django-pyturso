"""Scheduled hardening workflow and local-command contract."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "hardening.yml"
PYPROJECT = ROOT / "pyproject.toml"
VERSIONED_ACTION = re.compile(r"^\s*- uses: [^\s@]+@v\d+$", re.MULTILINE)


def test_hardening_workflow_is_non_release_scheduled_preparation() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "    schedule:\n" in workflow
    assert "    workflow_dispatch:\n" in workflow
    assert "pull_request:" not in workflow
    assert "    push:" not in workflow
    assert "release:" not in workflow
    assert "permissions:\n    contents: read" in workflow
    assert "timeout-minutes:" in workflow
    assert "HARDENING_SEED" in workflow
    uses_lines = [line for line in workflow.splitlines() if line.lstrip().startswith("- uses:")]
    assert uses_lines
    assert all(VERSIONED_ACTION.match(line) for line in uses_lines)


def test_hardening_workflow_covers_required_independence_lanes() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for job in (
        "  mutation:",
        "  stress:",
        "  repeated-fast:",
        "  dependency-bounds:",
        "  timezones:",
        "  locale:",
        "  ordering:",
    ):
        assert job in workflow
    for command in (
        "pdm run mutation-critical",
        "pdm run test-stress",
        "pdm run hardening-repeated-fast",
        "pdm.min.lock",
        "pdm.latest.lock",
        "pdm run hardening-utc",
        "pdm run hardening-timezones",
        "pdm run hardening-locale",
        "pdm run hardening-django-order",
        "pdm run hardening-random-order",
    ):
        assert command in workflow


def test_local_hardening_commands_and_random_order_dependency_are_declared() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = project["tool"]["pdm"]["scripts"]
    for name in (
        "hardening-utc",
        "hardening-timezones",
        "hardening-locale",
        "hardening-django-order",
        "hardening-random-order",
        "hardening-repeated-fast",
    ):
        assert name in scripts
    assert "pytest-random-order>=1.2.0" in project["dependency-groups"]["dev"]
