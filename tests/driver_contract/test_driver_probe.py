"""Regression tests for the versioned raw-driver evidence probe."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import turso

ROOT = Path(__file__).parents[2]
PROBE = ROOT / "scripts" / "probes" / "driver_contract.py"
SCHEMA_VERSION = 1
PROBE_ID = "django-pyturso.driver-contract"


def _run_probe(*arguments: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(PROBE), "--compact", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, Any], json.loads(completed.stdout))


def test_default_cli_emits_versioned_read_only_json() -> None:
    evidence = _run_probe()

    assert evidence["schema_version"] == SCHEMA_VERSION
    assert evidence["probe_id"] == PROBE_ID
    assert evidence["scope"] == {
        "read_only_private_memory_connection": True,
        "disposable_mutations_included": False,
        "caller_database_accepted": False,
    }
    assert "disposable_mutations" not in evidence
    driver = evidence["driver"]

    connection = turso.connect(":memory:")
    try:
        connected_engine_version = connection.execute("SELECT sqlite_version()").fetchone()[0]
    finally:
        connection.close()

    assert driver["dbapi"]["apilevel"] == "2.0"
    assert driver["dbapi"]["paramstyle"] == "qmark"
    assert driver["dbapi"]["binary_constructor_available"] is False
    assert driver["connected_engine_version"] == connected_engine_version
    assert driver["functions"]["status"] == "ok"
    assert "regexp" in driver["functions"]["distinct_names"]
    assert driver["pragmas"]["foreign_keys"]["status"] == "ok"


def test_disposable_mutations_cover_bindings_transactions_files_and_cleanup() -> None:
    evidence = _run_probe("--include-disposable-mutations")
    mutations = evidence["disposable_mutations"]
    memory = mutations["memory"]
    file = mutations["file"]

    assert memory["bindings"] == {"qmark_result": 5, "named_result": 5}
    assert memory["returning_row"] == [1, "kept"]
    assert memory["transaction_states"] == {
        "initial": False,
        "after_begin": True,
        "after_commit": False,
    }
    assert memory["savepoint_rollback_row_count"] == 1
    assert memory["integrity_error"]["error"]["type"].endswith(".IntegrityError")
    assert memory["closed_connection"]["execute"]["status"] == "error"
    assert memory["closed_connection"]["commit"] == {"status": "ok", "result": None}

    assert file["journal_mode"] == "wal"
    assert file["second_connection_committed_rows"] == [["committed"]]
    assert file["second_connection_during_uncommitted_write"] == [["committed"]]
    assert file["competing_write"]["error"]["type"].endswith(".OperationalError")
    assert file["parameters"]["local_counts"]["999"] == {
        "status": "ok",
        "result": 999,
    }
    assert file["disposable_directory_removed"] is True
