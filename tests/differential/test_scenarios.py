"""Compare focused Django scenarios across SQLite and Turso."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

import pytest

ROOT = Path(__file__).parents[2]
FILE_INTEROP_RUNNER = Path(__file__).with_name("file_interop_runner.py")

PARITY_SCENARIOS = (
    "crud",
    "scalars_and_nulls",
    "ordering",
    "joins",
    "subqueries",
    "json",
    "transactions",
    "schema",
    "introspection",
)
class IntentionalDifference(NamedTuple):
    scenario_id: str
    sqlite_expected: dict[str, str | int]
    turso_expected: dict[str, str | int]


INTENTIONAL_DIFFERENCES = (
    IntentionalDifference(
        scenario_id="backend_identity",
        sqlite_expected={"display_name": "SQLite", "engine": "django.db.backends.sqlite3"},
        turso_expected={"display_name": "Turso", "engine": "django_pyturso"},
    ),
    IntentionalDifference(
        scenario_id="random_function",
        sqlite_expected={"count": 4, "status": "supported"},
        turso_expected={"exception": "NotSupportedError", "status": "rejected"},
    ),
)


def _run_backend(backend: str, mode: str, database: Path | None = None) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "tests.differential.runner",
        "--backend",
        backend,
        "--mode",
        mode,
    ]
    if mode == "file":
        assert database is not None
        command.extend(("--database", str(database)))
    environment = os.environ.copy()
    environment.pop("DJANGO_SETTINGS_MODULE", None)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        pytest.fail(
            f"{backend}/{mode} differential runner failed ({completed.returncode}).\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return cast(dict[str, Any], json.loads(completed.stdout))


@pytest.fixture(scope="module", params=("memory", "file"))
def backend_observations(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[dict[str, Any], dict[str, Any]]:
    mode = cast(str, request.param)
    directory = tmp_path_factory.mktemp(f"differential-{mode}")
    return (
        _run_backend("sqlite", mode, directory / "sqlite.db" if mode == "file" else None),
        _run_backend("turso", mode, directory / "turso.db" if mode == "file" else None),
    )


@pytest.mark.differential
def test_differential_runner_reports_the_direct_scenario_set(
    backend_observations: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    sqlite, turso = backend_observations
    scenario_ids = set(PARITY_SCENARIOS) | {
        difference.scenario_id for difference in INTENTIONAL_DIFFERENCES
    }
    assert set(sqlite) == set(turso) == scenario_ids


@pytest.mark.differential
@pytest.mark.parametrize("scenario_id", PARITY_SCENARIOS)
def test_differential_parity(
    backend_observations: tuple[dict[str, Any], dict[str, Any]], scenario_id: str
) -> None:
    sqlite, turso = backend_observations
    assert sqlite[scenario_id] == turso[scenario_id]


@pytest.mark.differential
@pytest.mark.parametrize(
    "difference", INTENTIONAL_DIFFERENCES, ids=lambda difference: difference.scenario_id
)
def test_intentional_differential_differences(
    backend_observations: tuple[dict[str, Any], dict[str, Any]],
    difference: IntentionalDifference,
) -> None:
    sqlite, turso = backend_observations
    assert sqlite[difference.scenario_id] == difference.sqlite_expected
    assert turso[difference.scenario_id] == difference.turso_expected
    assert sqlite[difference.scenario_id] != turso[difference.scenario_id]


@pytest.mark.differential
def test_offline_shared_file_interoperability(tmp_path: Path) -> None:
    database = tmp_path / "shared-file.db"

    def stage(backend: str, name: str) -> dict[str, Any]:
        environment = os.environ.copy()
        environment.pop("DJANGO_SETTINGS_MODULE", None)
        completed = subprocess.run(
            [
                sys.executable,
                str(FILE_INTEROP_RUNNER),
                "--backend",
                backend,
                "--stage",
                name,
                "--database",
                str(database),
            ],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return cast(dict[str, Any], json.loads(completed.stdout))

    seeded = stage("sqlite", "sqlite_seed")
    assert seeded["rows"] == [
        [1, "alpha", 1, {"source": "sqlite"}],
        [2, "beta", None, {"source": "sqlite"}],
    ]
    assert seeded["has_rank_index"]

    migrated = stage("turso", "turso_migrate_write")
    assert migrated["before"] == seeded["rows"]
    assert migrated["after"][0][-1] == "migrated"
    assert migrated["after"][2] == [
        3,
        "gamma",
        3,
        {"source": "turso"},
        "created",
    ]

    sqlite_again = stage("sqlite", "sqlite_verify_write")
    assert sqlite_again["before"] == migrated["after"]
    assert sqlite_again["after"][1] == [
        2,
        "beta",
        2,
        {"source": "sqlite-again"},
        "updated",
    ]

    final = stage("turso", "turso_final_verify")
    assert final["rows"] == sqlite_again["after"]
    assert final["columns"] == ["id", "title", "rank", "payload", "status"]
    assert final["has_rank_index"]
