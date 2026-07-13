"""Database NAME behavior for filesystem edge cases.

These tests enforce the documented Django-style path contract. They do not
claim that the backend confines database files to an application directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from django.db import OperationalError

from django_pyturso.base import DatabaseWrapper
from tests.core.test_connection import wrapper_settings


def _round_trip(wrapper: DatabaseWrapper) -> None:
    try:
        with wrapper.cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS path_probe (value text)")
            cursor.execute("DELETE FROM path_probe")
            cursor.execute("INSERT INTO path_probe(value) VALUES (%s)", ("ok",))
            cursor.execute("SELECT value FROM path_probe")
            assert cursor.fetchone() == ("ok",)
    finally:
        wrapper.close()


@pytest.mark.core
def test_traversal_shaped_relative_path_is_a_normal_django_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, django_db_blocker: Any
) -> None:
    (tmp_path / "nested").mkdir()
    monkeypatch.chdir(tmp_path)
    wrapper = DatabaseWrapper(wrapper_settings(NAME=Path("nested/../local.db")), "probe")
    with django_db_blocker.unblock():
        _round_trip(wrapper)
    assert (tmp_path / "local.db").is_file()


@pytest.mark.core
def test_symlink_database_name_follows_filesystem_semantics(
    tmp_path: Path, django_db_blocker: Any
) -> None:
    target = tmp_path / "target.db"
    with django_db_blocker.unblock():
        _round_trip(DatabaseWrapper(wrapper_settings(NAME=target), "target"))
        link = tmp_path / "linked.db"
        link.symlink_to(target)
        _round_trip(DatabaseWrapper(wrapper_settings(NAME=link), "linked"))
    assert link.is_symlink()
    assert target.is_file()


@pytest.mark.core
def test_non_regular_database_name_is_rejected_by_driver(
    tmp_path: Path, django_db_blocker: Any
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(NAME=tmp_path), "probe")
    with (
        django_db_blocker.unblock(),
        pytest.raises(
            OperationalError, match="Unable to open Turso database: open: IsADirectory"
        ) as captured,
    ):
        wrapper.ensure_connection()
    assert captured.value.__cause__ is not None
    assert type(captured.value.__cause__).__module__ == "turso"
    assert type(captured.value.__cause__).__name__ == "IoError"
    assert wrapper.connection is None


@pytest.mark.core
@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="POSIX permission probe")
def test_permission_failure_does_not_leave_a_connection(
    tmp_path: Path, django_db_blocker: Any
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    wrapper = DatabaseWrapper(wrapper_settings(NAME=locked / "database.db"), "probe")
    try:
        with django_db_blocker.unblock():
            with pytest.raises(
                OperationalError,
                match="Unable to open Turso database: open: PermissionDenied",
            ) as captured:
                wrapper.ensure_connection()
        assert captured.value.__cause__ is not None
        assert type(captured.value.__cause__).__module__ == "turso"
        assert type(captured.value.__cause__).__name__ == "IoError"
        assert wrapper.connection is None
    finally:
        locked.chmod(0o700)
