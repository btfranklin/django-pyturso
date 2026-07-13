"""Enforce measured repository and critical-module branch-coverage floors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

DEFAULT_REPORT = Path("artifacts/coverage/coverage.json")
DEFAULT_FLOORS = Path("tests/coverage-floors.json")


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def check(report_path: Path, floors_path: Path) -> list[str]:
    report = load_json(report_path)
    floors = load_json(floors_path)
    failures: list[str] = []

    repository_actual = float(report["totals"]["percent_covered"])
    repository_floor = float(floors["repository_branch_percent"])
    if repository_actual < repository_floor:
        failures.append(
            f"repository branch coverage {repository_actual:.2f}% is below "
            f"the ratcheting floor {repository_floor:.2f}%"
        )

    files = report["files"]
    for filename, floor in floors["critical_module_branch_percent"].items():
        if filename not in files:
            failures.append(f"critical coverage module is missing from the report: {filename}")
            continue
        actual = float(files[filename]["summary"]["percent_covered"])
        if actual < float(floor):
            failures.append(
                f"{filename} branch coverage {actual:.2f}% is below "
                f"the ratcheting floor {float(floor):.2f}%"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--floors", type=Path, default=DEFAULT_FLOORS)
    args = parser.parse_args()
    failures = check(args.report, args.floors)
    if failures:
        for failure in failures:
            print(f"coverage floor failure: {failure}")
        return 1
    print("Coverage ratcheting floors passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
