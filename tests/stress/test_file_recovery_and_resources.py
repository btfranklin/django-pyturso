"""Bounded process-recovery and local resource-leak stress checks."""

from __future__ import annotations

import gc
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import psutil  # type: ignore[import-untyped]
import pytest

from django_pyturso.base import DatabaseWrapper

CRASH_WRITER = Path(__file__).with_name("_crash_writer.py")


@pytest.fixture(autouse=True)
def unblock_database_access(django_db_blocker: Any) -> Iterator[None]:
    with django_db_blocker.unblock():
        yield


def wrapper_settings(database: Path) -> dict[str, Any]:
    return {
        "ENGINE": "django_pyturso",
        "NAME": database,
        "OPTIONS": {},
        "HOST": "",
        "PORT": "",
        "USER": "",
        "PASSWORD": "",
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "TIME_ZONE": None,
        "TEST": {"NAME": None},
    }


def open_and_close(database: Path, alias: str) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(database), alias)
    try:
        with wrapper.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    finally:
        wrapper.close()


def descriptor_count(process: psutil.Process) -> int:
    if hasattr(process, "num_fds"):
        return cast(int, process.num_fds())
    return cast(int, process.num_handles())


@pytest.mark.stress
@pytest.mark.timeout(10)
def test_repeated_file_connections_do_not_leak_resources(tmp_path: Path) -> None:
    database = tmp_path / "resources.db"
    process = psutil.Process()

    open_and_close(database, "stress_warmup")
    gc.collect()
    baseline_descriptors = descriptor_count(process)
    baseline_threads = process.num_threads()

    for index in range(40):
        open_and_close(database, f"stress_{index}")

    gc.collect()
    assert descriptor_count(process) <= baseline_descriptors + 2
    assert process.num_threads() <= baseline_threads + 1
    open_paths = {Path(item.path) for item in process.open_files()}
    assert database not in open_paths
    assert Path(f"{database}-wal") not in open_paths


@pytest.mark.stress
@pytest.mark.timeout(10)
def test_process_exit_rolls_back_wal_and_file_remains_writable(tmp_path: Path) -> None:
    database = tmp_path / "recovery.db"
    completed = subprocess.run(
        [sys.executable, str(CRASH_WRITER), str(database)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 23

    wrapper = DatabaseWrapper(wrapper_settings(database), "stress_recovery")
    try:
        with wrapper.cursor() as cursor:
            cursor.execute("SELECT value FROM recovery_probe")
            assert cursor.fetchall() == []
            cursor.execute("INSERT INTO recovery_probe VALUES (%s)", ("recovered",))
            cursor.execute("SELECT value FROM recovery_probe")
            assert cursor.fetchall() == [("recovered",)]
    finally:
        wrapper.close()
