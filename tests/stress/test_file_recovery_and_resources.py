"""Bounded process-recovery and local resource-leak stress checks."""

from __future__ import annotations

import gc
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Protocol, cast

# psutil has no installed stubs. The protocol below types the API used here.
import psutil  # type: ignore[import-untyped]
import pytest
from pytest_django.plugin import DjangoDbBlocker

from django_pyturso.base import DatabaseWrapper


class _OpenFile(Protocol):
    @property
    def path(self) -> str: ...


class _Process(Protocol):
    def num_threads(self) -> int: ...

    def open_files(self) -> Sequence[_OpenFile]: ...


CRASH_WRITER = Path(__file__).with_name("_crash_writer.py")


@pytest.fixture(autouse=True)
def unblock_database_access(django_db_blocker: DjangoDbBlocker) -> Iterator[None]:
    with django_db_blocker.unblock():
        yield


def wrapper_settings(database: Path) -> dict[str, object]:
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


def descriptor_count(process: object) -> int:
    count = getattr(process, "num_fds", None) or getattr(process, "num_handles")
    assert callable(count)
    result: object = count()
    assert isinstance(result, int)
    return result


@pytest.mark.stress
@pytest.mark.timeout(10)
def test_repeated_file_connections_do_not_leak_resources(tmp_path: Path) -> None:
    database = tmp_path / "resources.db"
    process = cast(_Process, psutil.Process())

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
@pytest.mark.parametrize(
    ("journal_mode", "transaction_mode"),
    [("WAL", "IMMEDIATE"), ("MVCC", "IMMEDIATE"), ("MVCC", "CONCURRENT")],
)
def test_process_exit_preserves_commits_and_rolls_back_open_transactions(
    tmp_path: Path, journal_mode: str, transaction_mode: str
) -> None:
    database = tmp_path / "recovery.db"
    completed = subprocess.run(
        [sys.executable, str(CRASH_WRITER), str(database), journal_mode, transaction_mode],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 23

    settings = wrapper_settings(database)
    settings["OPTIONS"] = {"journal_mode": journal_mode, "transaction_mode": transaction_mode}
    wrapper = DatabaseWrapper(settings, "stress_recovery")
    try:
        with wrapper.cursor() as cursor:
            cursor.execute("SELECT value FROM recovery_probe")
            assert cursor.fetchall() == [("committed",)]
            cursor.execute("INSERT INTO recovery_probe VALUES (%s)", ("recovered",))
            cursor.execute("SELECT value FROM recovery_probe ORDER BY value")
            assert cursor.fetchall() == [("committed",), ("recovered",)]
    finally:
        wrapper.close()

    reopened = DatabaseWrapper(settings, "stress_reopened")
    try:
        with reopened.cursor() as cursor:
            cursor.execute("SELECT value FROM recovery_probe ORDER BY value")
            assert cursor.fetchall() == [("committed",), ("recovered",)]
    finally:
        reopened.close()
