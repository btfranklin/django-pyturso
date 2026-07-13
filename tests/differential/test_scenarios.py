"""Compare the manifest-backed scenario catalog across SQLite and Turso."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "tests" / "manifests" / "differential-scenarios.toml"
FILE_INTEROP_RUNNER = Path(__file__).with_name("file_interop_runner.py")


def _manifest() -> dict[str, dict[str, Any]]:
    with MANIFEST.open("rb") as manifest_file:
        entries = tomllib.load(manifest_file)["scenario"]
    manifest = {entry["id"]: entry for entry in entries}
    assert len(manifest) == len(entries), "Differential scenario identifiers must be unique."
    return manifest


def _run_backend(backend: str, mode: str, database: Path) -> dict[str, Any]:
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


@pytest.mark.differential
@pytest.mark.parametrize("mode", ["memory", "file"])
def test_manifest_scenarios_match_their_classification(mode: str, tmp_path: Path) -> None:
    manifest = _manifest()
    sqlite = _run_backend("sqlite", mode, tmp_path / "sqlite.db")
    turso = _run_backend("turso", mode, tmp_path / "turso.db")

    assert set(sqlite) == set(turso) == set(manifest)
    for scenario_id, entry in manifest.items():
        assert mode in entry["modes"], scenario_id
        classification = entry["classification"]
        if classification in {"parity", "normalized_parity"}:
            if classification == "normalized_parity":
                assert entry.get("normalizer"), scenario_id
            assert sqlite[scenario_id] == turso[scenario_id], scenario_id
        elif classification == "intentional_difference":
            assert entry.get("rationale"), scenario_id
            assert sqlite[scenario_id] == json.loads(entry["sqlite_expected"])
            assert turso[scenario_id] == json.loads(entry["turso_expected"])
            assert sqlite[scenario_id] != turso[scenario_id]
        else:
            pytest.fail(f"Unknown differential classification: {classification}")


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
