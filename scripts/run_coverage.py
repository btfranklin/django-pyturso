"""Run the offline branch-coverage profile and emit durable artifacts."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ARTIFACTS = Path("artifacts/coverage")


def run(*arguments: str, check: bool = True) -> int:
    completed = subprocess.run([sys.executable, "-m", *arguments], check=check)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--measure-only",
        action="store_true",
        help="emit reports without enforcing checked-in ratcheting floors",
    )
    args = parser.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    run("coverage", "erase")
    test_exit_code = run(
        "coverage",
        "run",
        "-m",
        "pytest",
        "-m",
        "not upstream and not performance",
        check=False,
    )
    run("coverage", "report")
    run("coverage", "json")
    run("coverage", "xml")
    run("coverage", "html")
    if test_exit_code != 0:
        print(
            "Coverage artifacts were written, but the test profile failed; "
            "ratcheting floors were not evaluated."
        )
        return test_exit_code
    if not args.measure_only:
        run("scripts.check_coverage_floors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
