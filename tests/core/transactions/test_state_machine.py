"""Django/Turso transaction and connection-lifecycle state-machine tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from itertools import count
from pathlib import Path
from typing import Any, cast

import pytest
import turso
from django.db import connections, transaction
from django.db.transaction import TransactionManagementError

from django_pyturso.base import DatabaseWrapper

ALIASES = count()


@pytest.fixture(autouse=True)
def unblock_database_access(django_db_blocker: Any) -> Iterator[None]:
    with django_db_blocker.unblock():
        yield


def wrapper_settings(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "ENGINE": "django_pyturso",
        "NAME": ":memory:",
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
    values.update(overrides)
    return values


@contextmanager
def registered_wrapper(**settings: Any) -> Iterator[DatabaseWrapper]:
    alias = f"phase_0c_{next(ALIASES)}"
    wrapper = DatabaseWrapper(wrapper_settings(**settings), alias)
    connections[alias] = wrapper
    try:
        yield wrapper
    finally:
        if wrapper.connection is not None:
            wrapper._force_close()
        del connections[alias]


def rows(wrapper: DatabaseWrapper) -> list[tuple[Any, ...]]:
    with wrapper.cursor() as cursor:
        cursor.execute("SELECT value FROM state_probe ORDER BY id")
        return cast(list[tuple[Any, ...]], cursor.fetchall())


@pytest.mark.core
def test_manual_autocommit_rearms_after_commit_and_rollback_for_cte_writes() -> None:
    with registered_wrapper() as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE state_probe (id INTEGER PRIMARY KEY, value TEXT)"
            )

        wrapper.set_autocommit(False)
        assert wrapper.autocommit is False
        assert wrapper.connection.in_transaction is True

        with wrapper.cursor() as cursor:
            cursor.execute(
                "WITH pending(value) AS (VALUES (%s)) "
                "INSERT INTO state_probe(value) SELECT value FROM pending",
                ("committed",),
            )
        with pytest.raises(TransactionManagementError):
            wrapper.set_autocommit(True)

        wrapper.commit()
        assert wrapper.autocommit is False
        assert wrapper.connection.in_transaction is False

        with wrapper.cursor() as cursor:
            cursor.execute("INSERT INTO state_probe(value) VALUES (%s)", ("rolled-back",))
        assert wrapper.connection.in_transaction is True
        wrapper.rollback()
        assert wrapper.connection.in_transaction is False

        with wrapper.cursor() as cursor:
            cursor.execute("INSERT INTO state_probe(value) VALUES (%s)", ("rearmed",))
        wrapper.commit()
        wrapper.set_autocommit(True)

        assert wrapper.autocommit is True
        assert wrapper.connection.in_transaction is False
        assert rows(wrapper) == [("committed",), ("rearmed",)]


@pytest.mark.core
def test_outer_and_nested_atomic_manage_savepoints_and_on_commit_callbacks() -> None:
    callbacks: list[str] = []
    with registered_wrapper() as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE state_probe (id INTEGER PRIMARY KEY, value TEXT)"
            )

        with transaction.atomic(using=wrapper.alias):
            with wrapper.cursor() as cursor:
                cursor.execute("INSERT INTO state_probe(value) VALUES (%s)", ("outer",))
            transaction.on_commit(
                lambda: callbacks.append("outer"), using=wrapper.alias
            )
            try:
                with transaction.atomic(using=wrapper.alias):
                    with wrapper.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO state_probe(value) VALUES (%s)", ("inner",)
                        )
                    transaction.on_commit(
                        lambda: callbacks.append("inner"), using=wrapper.alias
                    )
                    raise ValueError("roll back the savepoint")
            except ValueError:
                pass
            assert callbacks == []
            assert wrapper.in_atomic_block is True
            assert wrapper.connection.in_transaction is True

        assert callbacks == ["outer"]
        assert wrapper.autocommit is True
        assert wrapper.in_atomic_block is False
        assert wrapper.connection.in_transaction is False
        assert rows(wrapper) == [("outer",)]


@pytest.mark.core
def test_atomic_after_manual_commit_or_rollback_lazily_rearms_transaction() -> None:
    with registered_wrapper() as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE state_probe (id INTEGER PRIMARY KEY, value TEXT)"
            )
        wrapper.set_autocommit(False)

        wrapper.commit()
        assert wrapper.connection.in_transaction is False
        with transaction.atomic(using=wrapper.alias):
            assert wrapper.commit_on_exit is False
            assert wrapper.connection.in_transaction is True
            with wrapper.cursor() as cursor:
                cursor.execute("INSERT INTO state_probe(value) VALUES (%s)", ("first",))
        wrapper.commit()

        wrapper.rollback()
        assert wrapper.connection.in_transaction is False
        with transaction.atomic(using=wrapper.alias):
            assert wrapper.connection.in_transaction is True
            with wrapper.cursor() as cursor:
                cursor.execute("INSERT INTO state_probe(value) VALUES (%s)", ("second",))
        wrapper.commit()
        wrapper.set_autocommit(True)

        assert rows(wrapper) == [("first",), ("second",)]


@pytest.mark.core
def test_atomic_rolls_back_ddl_and_dml_together() -> None:
    with registered_wrapper() as wrapper:
        with pytest.raises(RuntimeError, match="abort"):
            with transaction.atomic(using=wrapper.alias):
                with wrapper.cursor() as cursor:
                    cursor.execute("CREATE TABLE rollback_probe (value TEXT)")
                    cursor.execute("INSERT INTO rollback_probe VALUES (%s)", ("lost",))
                raise RuntimeError("abort")

        with wrapper.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'table' AND name = 'rollback_probe'"
            )
            assert cursor.fetchone() == (0,)


@pytest.mark.core
def test_memory_close_rolls_back_active_work_but_preserves_database() -> None:
    with registered_wrapper() as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE state_probe (id INTEGER PRIMARY KEY, value TEXT)"
            )
        physical = wrapper.connection
        wrapper.set_autocommit(False)
        with wrapper.cursor() as cursor:
            cursor.execute("INSERT INTO state_probe(value) VALUES (%s)", ("lost",))
        wrapper.run_on_commit = cast(Any, [(set(), lambda: None, False)])

        wrapper.close()

        assert wrapper.connection is physical
        assert wrapper.connection.in_transaction is False
        assert wrapper.autocommit is False
        assert wrapper.run_on_commit == []
        assert rows(wrapper) == []
        assert wrapper.connection.in_transaction is True
        wrapper.rollback()
        wrapper.set_autocommit(True)


@pytest.mark.core
def test_file_close_rolls_back_active_work_and_detaches_connection(tmp_path: Path) -> None:
    with registered_wrapper(NAME=tmp_path / "state.db") as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE state_probe (id INTEGER PRIMARY KEY, value TEXT)"
            )
        physical = wrapper.connection
        wrapper.set_autocommit(False)
        with wrapper.cursor() as cursor:
            cursor.execute("INSERT INTO state_probe(value) VALUES (%s)", ("lost",))

        wrapper.close()

        assert wrapper.connection is None
        with pytest.raises(turso.DatabaseError, match="Connection closed"):
            physical.execute("SELECT 1").fetchone()
        assert rows(wrapper) == []
        assert wrapper.autocommit is True


@pytest.mark.core
def test_close_inside_atomic_rolls_back_and_forcibly_loses_memory_database() -> None:
    callbacks: list[str] = []
    with registered_wrapper() as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE state_probe (id INTEGER PRIMARY KEY, value TEXT)"
            )

        with transaction.atomic(using=wrapper.alias):
            transaction.on_commit(
                lambda: callbacks.append("unexpected"), using=wrapper.alias
            )
            with wrapper.cursor() as cursor:
                cursor.execute("INSERT INTO state_probe(value) VALUES (%s)", ("lost",))
            wrapper.close()
            assert wrapper.closed_in_transaction is True
            assert wrapper.needs_rollback is True
            assert wrapper.connection.in_transaction is False

        assert wrapper.connection is None
        assert callbacks == []
        with wrapper.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'table' AND name = 'state_probe'"
            )
            assert cursor.fetchone() == (0,)


@pytest.mark.core
def test_memory_health_failure_forces_disposal(monkeypatch: pytest.MonkeyPatch) -> None:
    with registered_wrapper(CONN_HEALTH_CHECKS=True) as wrapper:
        wrapper.cursor().close()
        physical = wrapper.connection
        wrapper.health_check_enabled = True
        wrapper.health_check_done = False
        monkeypatch.setattr(wrapper, "is_usable", lambda: False)

        wrapper.close_if_health_check_failed()

        assert wrapper.connection is None
        with pytest.raises(turso.DatabaseError, match="Connection closed"):
            physical.execute("SELECT 1").fetchone()


@pytest.mark.core
def test_healthy_memory_age_expiry_preserves_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    with registered_wrapper(CONN_MAX_AGE=0) as wrapper:
        wrapper.cursor().close()
        physical = wrapper.connection
        assert wrapper.close_at is not None
        monkeypatch.setattr("django_pyturso.base.time.monotonic", lambda: wrapper.close_at)

        wrapper.close_if_unusable_or_obsolete()

        assert wrapper.connection is physical
        assert wrapper.health_check_done is True


@pytest.mark.core
def test_memory_autocommit_mismatch_rolls_back_and_forces_disposal() -> None:
    with registered_wrapper() as wrapper:
        wrapper.cursor().close()
        physical = wrapper.connection
        wrapper.set_autocommit(False)
        assert physical.in_transaction is True

        wrapper.close_if_unusable_or_obsolete()

        assert physical.in_transaction is False
        assert wrapper.connection is None


@pytest.mark.core
def test_fatal_memory_error_forces_disposal(monkeypatch: pytest.MonkeyPatch) -> None:
    with registered_wrapper() as wrapper:
        wrapper.cursor().close()
        physical = wrapper.connection
        wrapper.errors_occurred = True
        monkeypatch.setattr(wrapper, "is_usable", lambda: False)

        wrapper.close_if_unusable_or_obsolete()

        assert wrapper.connection is None
        with pytest.raises(turso.DatabaseError, match="Connection closed"):
            physical.execute("SELECT 1").fetchone()


@pytest.mark.core
def test_engine_state_drift_rolls_back_and_forces_disposal() -> None:
    with registered_wrapper() as wrapper:
        wrapper.cursor().close()
        physical = wrapper.connection
        physical.execute("BEGIN")
        assert wrapper.autocommit is True
        assert physical.in_transaction is True

        wrapper.close_if_unusable_or_obsolete()

        assert physical.in_transaction is False
        assert wrapper.connection is None


class FailingRollbackConnection:
    """Minimal fault-injection connection for the explicit close path."""

    in_transaction = True

    def __init__(self) -> None:
        self.closed = False

    def rollback(self) -> None:
        raise turso.OperationalError("injected rollback failure")

    def close(self) -> None:
        self.closed = True


@pytest.mark.core
def test_rollback_failure_forces_disposal_and_clears_callbacks() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "rollback_failure")
    physical = FailingRollbackConnection()
    wrapper.connection = physical
    wrapper.autocommit = False
    wrapper.run_on_commit = cast(Any, [(set(), lambda: None, False)])

    with pytest.raises(turso.OperationalError, match="injected rollback failure"):
        wrapper.close()

    assert physical.closed is True
    assert wrapper.connection is None
    assert wrapper.run_on_commit == []
