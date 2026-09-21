"""Explicit MVCC configuration and persistent database mode contracts."""

from pathlib import Path
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured

from django_pyturso.base import DatabaseWrapper
from tests.support import wrapper_settings

pytestmark = pytest.mark.core


@pytest.mark.parametrize("name", [":memory:", "local.db"])
@pytest.mark.parametrize("mode", ["DEFERRED", "IMMEDIATE", "CONCURRENT"])
def test_mvcc_connection_accepts_each_transaction_mode(
    name: str, mode: str, tmp_path: Path, django_db_blocker: Any
) -> None:
    database = name if name == ":memory:" else str(tmp_path / name)
    wrapper = DatabaseWrapper(
        wrapper_settings(
            NAME=database,
            OPTIONS={"journal_mode": "mvcc", "transaction_mode": mode.lower()},
        ),
        "mvcc_configuration",
    )
    assert wrapper.get_connection_params() == {"database": database, "isolation_level": None}
    assert wrapper.journal_mode == "MVCC"
    assert wrapper.transaction_mode == mode
    try:
        with django_db_blocker.unblock(), wrapper.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode")
            assert cursor.fetchone() == ("mvcc",)
            cursor.execute("PRAGMA foreign_keys")
            assert cursor.fetchone() == (1,)
            cursor.execute("CREATE TABLE sample (value INTEGER)")
            wrapper.set_autocommit(False)
            cursor.execute("INSERT INTO sample VALUES (5)")
            wrapper.commit()
            wrapper.set_autocommit(True)
            cursor.execute("SELECT value FROM sample")
            assert cursor.fetchone() == (5,)
    finally:
        wrapper._force_close()


@pytest.mark.parametrize(
    "options",
    [
        {"journal_mode": None},
        {"journal_mode": 1},
        {"journal_mode": True},
        {"journal_mode": []},
        {"journal_mode": {}},
        {"journal_mode": ""},
        {"journal_mode": "DELETE"},
        {"journal_mode": " MVCC"},
        {"transaction_mode": "CONCURRENT"},
        {"transaction_mode": "CONCURRENT", "journal_mode": "WAL"},
        {"transaction_mode": None, "journal_mode": "MVCC"},
        {"transaction_mode": [], "journal_mode": "MVCC"},
    ],
)
def test_invalid_mvcc_settings_are_rejected(options: dict[str, Any]) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(OPTIONS=options), "invalid_mvcc")
    with pytest.raises(ImproperlyConfigured):
        wrapper.get_connection_params()


@pytest.mark.parametrize("mode", [None, "wal"])
def test_default_and_explicit_wal_connections(mode: str | None, django_db_blocker: Any) -> None:
    options = {} if mode is None else {"journal_mode": mode}
    wrapper = DatabaseWrapper(wrapper_settings(OPTIONS=options), "wal_configuration")
    try:
        with django_db_blocker.unblock(), wrapper.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode")
            assert cursor.fetchone() == ("wal",)
            assert wrapper.journal_mode == (None if mode is None else "WAL")
    finally:
        wrapper._force_close()


def test_mvcc_mode_persists_and_omitted_option_preserves_it(
    tmp_path: Path, django_db_blocker: Any
) -> None:
    database = tmp_path / "persistent.db"
    with django_db_blocker.unblock():
        for options in ({"journal_mode": "MVCC"}, {}, {"journal_mode": "MVCC"}):
            wrapper = DatabaseWrapper(
                wrapper_settings(NAME=database, OPTIONS=options), "persistent_mvcc"
            )
            try:
                with wrapper.cursor() as cursor:
                    cursor.execute("PRAGMA journal_mode")
                    assert cursor.fetchone() == ("mvcc",)
                    cursor.execute("CREATE TABLE IF NOT EXISTS sample (value INTEGER)")
                    cursor.execute("INSERT INTO sample VALUES (1)")
            finally:
                wrapper._force_close()
        wrapper = DatabaseWrapper(
            wrapper_settings(NAME=database, OPTIONS={"journal_mode": "WAL"}), "reject_wal"
        )
        with pytest.raises(ImproperlyConfigured, match="cannot change it to WAL"):
            wrapper.ensure_connection()
        assert wrapper.connection is None
        wrapper = DatabaseWrapper(wrapper_settings(NAME=database), "preserved_mvcc")
        try:
            with wrapper.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM sample")
                assert cursor.fetchone() == (3,)
        finally:
            wrapper._force_close()
