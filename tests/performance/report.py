"""Render pytest-benchmark JSON as stable JSON and Markdown reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

SNAPSHOTS = Path(__file__).parents[1] / "snapshots" / "performance"


def load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def normalize_report(raw: dict[str, Any], budgets: dict[str, Any]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for benchmark in raw.get("benchmarks", []):
        extra_info = benchmark.get("extra_info", {})
        case_id = extra_info.get("case_id", benchmark["name"])
        stats = benchmark["stats"]
        budget = budgets.get(case_id)
        median_ms = stats["median"] * 1_000
        mean_ms = stats["mean"] * 1_000
        passed = budget is None or median_ms <= budget["max_median_ms"]
        timing_status = (
            "observation-only" if budget is None else "pass" if passed else "fail"
        )
        cases.append(
            {
                "case_id": case_id,
                "median_ms": round(median_ms, 6),
                "mean_ms": round(mean_ms, 6),
                "rounds": stats["rounds"],
                "observed_queries": extra_info.get("observed_queries"),
                "observed_operations": extra_info.get("observed_operations"),
                "max_queries": extra_info.get("max_queries"),
                "max_operations": extra_info.get("max_operations"),
                "observed_count": extra_info.get("observed_count"),
                "correctness_status": extra_info.get(
                    "correctness_status", "not-reported"
                ),
                "correctness_sha256": extra_info.get("correctness_sha256"),
                "max_median_ms": None if budget is None else budget["max_median_ms"],
                "timing_status": timing_status,
            }
        )
    cases.sort(key=lambda item: item["case_id"])
    return {
        "schema_version": 2,
        "machine_info": raw.get("machine_info", {}),
        "commit_info": raw.get("commit_info", {}),
        "cases": cases,
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# django-pyturso performance report",
        "",
        (
            "| Case | Median ms | Mean ms | Rounds | Queries | Query cap | "
            "Correctness | Timing budget | Timing |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for case in report["cases"]:
        budget = case["max_median_ms"]
        lines.append(
            f"| `{case['case_id']}` | {case['median_ms']:.3f} | {case['mean_ms']:.3f} | "
            f"{case['rounds']} | {case['observed_queries']} | {case['max_queries']} | "
            f"{case['correctness_status']} | "
            f"{'—' if budget is None else f'{budget:.3f} ms'} | {case['timing_status']} |"
        )
    return "\n".join(lines) + "\n"


def render(input_path: Path, output_directory: Path, budgets_path: Path | None) -> bool:
    budgets = {} if budgets_path is None else load_json(budgets_path)["cases"]
    report = normalize_report(load_json(input_path), budgets)
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "performance-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_directory / "performance-report.md").write_text(
        markdown_report(report), encoding="utf-8"
    )
    return all(case["timing_status"] != "fail" for case in report["cases"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--budgets", type=Path, default=SNAPSHOTS / "timing-budgets.json")
    args = parser.parse_args()
    strict = bool(args.strict)
    configured_budgets = cast(Path, args.budgets)
    if strict and not configured_budgets.exists():
        parser.error(f"strict timing budgets do not exist: {configured_budgets}")
    budgets_path = configured_budgets if strict else None
    passed = render(args.input, args.output_directory, budgets_path)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
