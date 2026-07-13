"""Mechanical contract for branch-coverage ratchets and mutation scope."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from scripts.check_coverage_floors import check

ROOT = Path(__file__).parents[2]
CRITICAL_MODULES = {
    "src/django_pyturso/base.py",
    "src/django_pyturso/operations.py",
    "src/django_pyturso/schema.py",
}


def test_coverage_is_branch_enabled_and_mutation_scope_is_critical_only() -> None:
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    floors = json.loads((ROOT / "tests" / "coverage-floors.json").read_text())

    assert configuration["tool"]["coverage"]["run"]["branch"] is True
    assert set(configuration["tool"]["mutmut"]["only_mutate"]) == CRITICAL_MODULES
    assert set(floors["critical_module_branch_percent"]) == CRITICAL_MODULES
    assert floors["repository_branch_percent"] >= floors["measurement"][
        "release_target_repository_percent"
    ]


def test_floor_checker_reports_repository_and_critical_module_regressions(
    tmp_path: Path,
) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "totals": {"percent_covered": 49.0},
                "files": {
                    "critical.py": {"summary": {"percent_covered": 74.0}}
                },
            }
        ),
        encoding="utf-8",
    )
    floors = tmp_path / "floors.json"
    floors.write_text(
        json.dumps(
            {
                "repository_branch_percent": 50.0,
                "critical_module_branch_percent": {"critical.py": 75.0},
            }
        ),
        encoding="utf-8",
    )

    assert check(report, floors) == [
        "repository branch coverage 49.00% is below the ratcheting floor 50.00%",
        "critical.py branch coverage 74.00% is below the ratcheting floor 75.00%",
    ]
