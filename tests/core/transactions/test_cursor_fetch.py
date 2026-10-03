"""Keep delayed cursor execution within Django's transaction boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from django.db import DatabaseError, transaction
from django.db.transaction import TransactionManagementError

from tests.core.transactions.test_state_machine import registered_wrapper

pytestmark = pytest.mark.core
FETCH_METHODS = ["fetchone", "fetchmany", "fetchmany_size", "fetchall", "next", "iterate"]
MODES = [
    {"journal_mode": "WAL"},
    {"journal_mode": "MVCC", "transaction_mode": "CONCURRENT"},
]


@pytest.fixture(autouse=True)
def unblock_database_access(django_db_blocker: Any) -> Iterator[None]:
    with django_db_blocker.unblock():
        yield


def fetch(cursor: Any, method: str) -> Any:
    if method == "fetchmany_size":
        return cursor.fetchmany(1)
    if method == "next":
        return next(cursor.cursor)
    if method == "iterate":
        return list(cursor)
    return getattr(cursor, method)()


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize("boundary", ["commit", "rollback"])
@pytest.mark.parametrize("method", FETCH_METHODS)
def test_returning_fetch_rearms_manual_transaction(
    tmp_path: Path, options: dict[str, str], boundary: str, method: str
) -> None:
    with registered_wrapper(NAME=tmp_path / "manual.db", OPTIONS=options) as wrapper:
        wrapper.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY)")
        wrapper.set_autocommit(False)
        with wrapper.cursor() as pending:
            pending.execute("INSERT INTO t VALUES(1) RETURNING id")
            getattr(wrapper, boundary)()
            assert not wrapper.connection.in_transaction

            result = fetch(pending, method)
            assert result == ((1,) if method in {"fetchone", "next"} else [(1,)])
            transaction_active = wrapper.connection.in_transaction

        wrapper.rollback()
        wrapper.set_autocommit(True)
        assert wrapper.cursor().execute("SELECT * FROM t").fetchall() == []
        assert transaction_active


@pytest.mark.parametrize("method", FETCH_METHODS)
@pytest.mark.parametrize("manual", [False, True], ids=["autocommit", "manual"])
@pytest.mark.parametrize("savepoint", [True, False])
def test_returning_fetch_rejects_lost_atomic_transaction(
    tmp_path: Path, method: str, manual: bool, savepoint: bool
) -> None:
    options = MODES[1]
    path = tmp_path / "lost.db"
    callbacks: list[str] = []
    with registered_wrapper(NAME=path, OPTIONS=options) as a, registered_wrapper(
        NAME=path, OPTIONS=options
    ) as b:
        a.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY,n INTEGER)")
        a.cursor().execute("INSERT INTO t VALUES(1,0)")
        if manual:
            b.set_autocommit(False)
            b.rollback()
        with pytest.raises(ValueError, match="abort outer block"):
            with transaction.atomic(using=b.alias, savepoint=savepoint):
                b.cursor().execute("SELECT * FROM t").fetchall()
                with b.cursor() as pending:
                    pending.execute("INSERT INTO t VALUES(3,3) RETURNING id")
                    transaction.on_commit(lambda: callbacks.append("lost"), using=b.alias)
                    with transaction.atomic(using=a.alias):
                        a.cursor().execute("UPDATE t SET n=1 WHERE id=1")
                    with pytest.raises(DatabaseError, match="conflict"):
                        b.cursor().execute("UPDATE t SET n=2 WHERE id=1")
                    assert not b.connection.in_transaction
                    with pytest.raises(TransactionManagementError):
                        fetch(pending, method)
                    assert b.needs_rollback
                    raise ValueError("abort outer block")
        if manual:
            assert not b.connection.in_transaction
            b.rollback()
            b.set_autocommit(True)
        assert callbacks == []
        assert a.cursor().execute("SELECT * FROM t ORDER BY id").fetchall() == [(1, 1)]


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize("method", FETCH_METHODS)
def test_fetch_rejects_django_broken_transaction(
    tmp_path: Path, options: dict[str, str], method: str
) -> None:
    with registered_wrapper(NAME=tmp_path / "broken.db", OPTIONS=options) as wrapper:
        with transaction.atomic(using=wrapper.alias):
            with wrapper.cursor() as pending:
                pending.execute("SELECT 1")
                with pytest.raises(ValueError):
                    with transaction.atomic(using=wrapper.alias, savepoint=False):
                        raise ValueError("abort inner block")
                assert wrapper.connection.in_transaction
                assert wrapper.needs_rollback
                with pytest.raises(TransactionManagementError):
                    fetch(pending, method)


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
def test_iteration_checks_transaction_before_each_row(
    tmp_path: Path, options: dict[str, str]
) -> None:
    with registered_wrapper(NAME=tmp_path / "iteration.db", OPTIONS=options) as wrapper:
        with transaction.atomic(using=wrapper.alias):
            with wrapper.cursor() as pending:
                pending.execute("SELECT 1 UNION ALL SELECT 2")
                iterator = iter(pending)
                assert next(iterator) == (1,)
                with pytest.raises(ValueError):
                    with transaction.atomic(using=wrapper.alias, savepoint=False):
                        raise ValueError("abort inner block")
                with pytest.raises(TransactionManagementError):
                    next(iterator)


@pytest.mark.parametrize("manual", [False, True], ids=["autocommit", "manual"])
@pytest.mark.parametrize("savepoint", [True, False])
def test_caught_atomic_conflict_discards_callbacks_without_more_queries(
    tmp_path: Path, manual: bool, savepoint: bool
) -> None:
    options = MODES[1]
    path = tmp_path / "callbacks.db"
    callbacks: list[str] = []
    with registered_wrapper(NAME=path, OPTIONS=options) as a, registered_wrapper(
        NAME=path, OPTIONS=options
    ) as b:
        a.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY,n INTEGER)")
        a.cursor().execute("INSERT INTO t VALUES(1,0)")
        if manual:
            b.set_autocommit(False)
        with transaction.atomic(using=b.alias, savepoint=savepoint):
            b.cursor().execute("SELECT * FROM t").fetchall()
            transaction.on_commit(lambda: callbacks.append("lost"), using=b.alias)
            with transaction.atomic(using=a.alias):
                a.cursor().execute("UPDATE t SET n=1 WHERE id=1")
            with pytest.raises(DatabaseError, match="conflict"):
                b.cursor().execute("UPDATE t SET n=2 WHERE id=1")
        if manual:
            b.commit()
            b.set_autocommit(True)
        assert callbacks == []
        assert a.cursor().execute("SELECT * FROM t").fetchall() == [(1, 1)]


@pytest.mark.parametrize("manual", [False, True], ids=["autocommit", "manual"])
def test_nested_atomic_conflict_does_not_restart_engine_during_cleanup(
    tmp_path: Path, manual: bool
) -> None:
    path = tmp_path / "nested.db"
    callbacks: list[str] = []
    with registered_wrapper(NAME=path, OPTIONS=MODES[1]) as a, registered_wrapper(
        NAME=path, OPTIONS=MODES[1]
    ) as b:
        a.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY,n INTEGER)")
        a.cursor().execute("INSERT INTO t VALUES(1,0)")
        if manual:
            b.set_autocommit(False)
        with transaction.atomic(using=b.alias):
            transaction.on_commit(lambda: callbacks.append("outer"), using=b.alias)
            with transaction.atomic(using=b.alias):
                b.cursor().execute("SELECT * FROM t").fetchall()
                transaction.on_commit(lambda: callbacks.append("inner"), using=b.alias)
                with transaction.atomic(using=a.alias):
                    a.cursor().execute("UPDATE t SET n=1 WHERE id=1")
                with pytest.raises(DatabaseError, match="conflict"):
                    b.cursor().execute("UPDATE t SET n=2 WHERE id=1")
            assert not b.connection.in_transaction
            assert b.needs_rollback
        assert not b.connection.in_transaction
        if manual:
            b.commit()
            b.set_autocommit(True)
        assert callbacks == []
        if manual:
            b.rollback()
        assert b.cursor().execute("SELECT * FROM t").fetchall() == [(1, 1)]


@pytest.mark.parametrize("method", FETCH_METHODS)
def test_conflict_during_fetch_marks_atomic_transaction_for_rollback(
    tmp_path: Path, method: str
) -> None:
    path = tmp_path / "fetch_conflict.db"
    callbacks: list[str] = []
    with registered_wrapper(NAME=path, OPTIONS=MODES[1]) as a, registered_wrapper(
        NAME=path, OPTIONS=MODES[1]
    ) as b:
        a.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY,n INTEGER)")
        a.cursor().execute("INSERT INTO t VALUES(1,0)")
        with transaction.atomic(using=b.alias):
            b.cursor().execute("SELECT * FROM t").fetchall()
            transaction.on_commit(lambda: callbacks.append("lost"), using=b.alias)
            with b.cursor() as pending:
                pending.execute("UPDATE t SET n=2 WHERE id=1 RETURNING id")
                with transaction.atomic(using=a.alias):
                    a.cursor().execute("UPDATE t SET n=1 WHERE id=1")
                with pytest.raises(DatabaseError, match="conflict"):
                    with b.wrap_database_errors:
                        fetch(pending, method)
                assert not b.connection.in_transaction
                assert b.needs_rollback
                with pytest.raises(TransactionManagementError):
                    fetch(pending, method)
        assert callbacks == []
        assert b.cursor().execute("SELECT * FROM t").fetchall() == [(1, 1)]


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize("boundary", ["commit", "rollback"])
@pytest.mark.parametrize("savepoint", [True, False])
def test_pending_fetch_starts_manual_atomic_after_transaction_boundary(
    tmp_path: Path, options: dict[str, str], boundary: str, savepoint: bool
) -> None:
    with registered_wrapper(NAME=tmp_path / "manual_atomic.db", OPTIONS=options) as wrapper:
        wrapper.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY)")
        wrapper.set_autocommit(False)
        with wrapper.cursor() as pending:
            pending.execute("INSERT INTO t VALUES(1) RETURNING id")
            getattr(wrapper, boundary)()
            with pytest.raises(ValueError):
                with transaction.atomic(using=wrapper.alias, savepoint=savepoint):
                    assert pending.fetchall() == [(1,)]
                    assert wrapper.connection.in_transaction
                    raise ValueError("abort manual atomic")
        wrapper.rollback()
        wrapper.set_autocommit(True)
        assert wrapper.cursor().execute("SELECT * FROM t").fetchall() == []


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize("method", FETCH_METHODS)
def test_autocommit_fetch_preserves_reads_and_returning_writes(
    tmp_path: Path, options: dict[str, str], method: str
) -> None:
    with registered_wrapper(NAME=tmp_path / "autocommit.db", OPTIONS=options) as wrapper:
        wrapper.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY)")
        with wrapper.cursor() as pending:
            pending.execute("INSERT INTO t VALUES(1) RETURNING id")
            result = fetch(pending, method)
            assert result == ((1,) if method in {"fetchone", "next"} else [(1,)])
            pending.fetchall()
        with wrapper.cursor() as cursor:
            cursor.execute("SELECT * FROM t")
            assert fetch(cursor, method) == result
            cursor.fetchall()
        assert wrapper.get_autocommit()
        assert not wrapper.connection.in_transaction
