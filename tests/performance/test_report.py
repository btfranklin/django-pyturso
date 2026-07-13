"""Report rendering contract for the performance lane."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .report import render

pytestmark = pytest.mark.performance


def test_non_strict_report_is_observation_only(tmp_path: Path) -> None:
    raw = {
        "machine_info": {"machine": "test"},
        "commit_info": {"id": "test"},
        "benchmarks": [
            {
                "name": "test_case",
                "extra_info": {
                    "case_id": "case",
                    "max_queries": 1,
                    "observed_queries": 1,
                    "observed_count": 500,
                    "correctness_status": "pass",
                    "correctness_sha256": "abc123",
                },
                "stats": {"median": 0.001, "mean": 0.0012, "rounds": 5},
            }
        ],
    }
    source = tmp_path / "benchmark.json"
    source.write_text(json.dumps(raw), encoding="utf-8")

    assert render(source, tmp_path / "report", None) is True

    report = json.loads((tmp_path / "report" / "performance-report.json").read_text())
    case = report["cases"][0]
    assert report["schema_version"] == 2
    assert case["timing_status"] == "observation-only"
    assert case["observed_queries"] == 1
    assert case["observed_count"] == 500
    assert case["correctness_status"] == "pass"
    assert case["correctness_sha256"] == "abc123"
    markdown = (tmp_path / "report" / "performance-report.md").read_text()
    assert "| `case` | 1.000 | 1.200 | 5 | 1 | 1 | pass | — | observation-only |" in markdown


def test_strict_report_fails_a_budget_overrun(tmp_path: Path) -> None:
    raw = {
        "benchmarks": [
            {
                "name": "test_case",
                "extra_info": {"case_id": "case", "max_queries": 1},
                "stats": {"median": 0.002, "mean": 0.002, "rounds": 5},
            }
        ]
    }
    source = tmp_path / "benchmark.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    budgets = tmp_path / "budgets.json"
    budgets.write_text(
        json.dumps({"cases": {"case": {"max_median_ms": 1.0}}}), encoding="utf-8"
    )

    assert render(source, tmp_path / "report", budgets) is False
