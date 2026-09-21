"""MVCC transaction behavior through Django's backend interface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.db import DatabaseError, NotSupportedError, transaction

from tests.core.transactions.test_state_machine import registered_wrapper

pytestmark = pytest.mark.core
OPTIONS = {"journal_mode": "MVCC", "transaction_mode": "CONCURRENT"}


@pytest.fixture(autouse=True)
def unblock_database_access(django_db_blocker: Any) -> Any:
    with django_db_blocker.unblock():
        yield


def test_independent_writers_commit_and_conflicting_writer_can_retry(tmp_path: Path) -> None:
    path = tmp_path / "writers.db"
    with registered_wrapper(NAME=path, OPTIONS=OPTIONS) as a, registered_wrapper(
        NAME=path, OPTIONS=OPTIONS
    ) as b:
        with a.cursor() as cursor:
            cursor.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, n INTEGER)")
            cursor.execute("INSERT INTO t VALUES (1,0),(2,0)")
        with transaction.atomic(using=a.alias):
            with transaction.atomic(using=b.alias):
                a.cursor().execute("UPDATE t SET n=1 WHERE id=1")
                b.cursor().execute("UPDATE t SET n=2 WHERE id=2")
        assert a.cursor().execute("SELECT n FROM t ORDER BY id").fetchall() == [(1,), (2,)]

        callbacks: list[str] = []
        with pytest.raises(DatabaseError, match="conflict"):
            with transaction.atomic(using=b.alias):
                b.cursor().execute("SELECT * FROM t").fetchall()
                transaction.on_commit(lambda: callbacks.append("lost"), using=b.alias)
                with transaction.atomic(using=a.alias):
                    a.cursor().execute("UPDATE t SET n=3 WHERE id=1")
                b.cursor().execute("UPDATE t SET n=4 WHERE id=1")
        assert callbacks == []
        assert b.get_autocommit()
        assert not b.in_atomic_block
        with transaction.atomic(using=b.alias):
            b.cursor().execute("UPDATE t SET n=4 WHERE id=1")
        assert b.cursor().execute("SELECT n FROM t WHERE id=1").fetchone() == (4,)


def test_nested_atomic_and_manual_transactions() -> None:
    with registered_wrapper(OPTIONS=OPTIONS) as wrapper:
        wrapper.cursor().execute("CREATE TABLE t(n INTEGER)")
        with transaction.atomic(using=wrapper.alias):
            wrapper.cursor().execute("INSERT INTO t VALUES(1)")
            with pytest.raises(ValueError):
                with transaction.atomic(using=wrapper.alias):
                    wrapper.cursor().execute("INSERT INTO t VALUES(2)")
                    raise ValueError("rollback savepoint")
        wrapper.set_autocommit(False)
        wrapper.cursor().execute("INSERT INTO t VALUES(3)")
        wrapper.commit()
        wrapper.cursor().execute("INSERT INTO t VALUES(4)")
        wrapper.rollback()
        wrapper.cursor().execute("INSERT INTO t VALUES(5)")
        wrapper.commit()
        wrapper.set_autocommit(True)
        assert wrapper.cursor().execute("SELECT n FROM t ORDER BY n").fetchall() == [
            (1,), (3,), (5,)
        ]


@pytest.mark.parametrize("atomic", [True, False])
def test_schema_editor_uses_regular_transactions_and_restores_mode(atomic: bool) -> None:
    with registered_wrapper(OPTIONS=OPTIONS) as wrapper:
        with wrapper.schema_editor(atomic=atomic) as editor:
            assert wrapper.transaction_mode == "IMMEDIATE"
            editor.execute("CREATE TABLE t(n INTEGER)")
            editor.deferred_sql.append("CREATE INDEX t_n ON t(n)")
        assert wrapper.transaction_mode == "CONCURRENT"
        assert wrapper.cursor().execute("PRAGMA foreign_keys").fetchone() == (1,)
        with transaction.atomic(using=wrapper.alias):
            wrapper.cursor().execute("INSERT INTO t VALUES(1)")
        assert wrapper.cursor().execute("SELECT n FROM t").fetchone() == (1,)


def test_schema_failure_rolls_back_and_restores_mode() -> None:
    with registered_wrapper(OPTIONS=OPTIONS) as wrapper:
        with pytest.raises(DatabaseError):
            with wrapper.schema_editor() as editor:
                editor.execute("CREATE TABLE lost(n INTEGER)")
                editor.deferred_sql.append("CREATE INDEX bad ON missing(n)")
        assert wrapper.transaction_mode == "CONCURRENT"
        assert wrapper.get_autocommit()
        assert wrapper.cursor().execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert "lost" not in wrapper.introspection.table_names()


def test_schema_editor_rejects_active_concurrent_transaction() -> None:
    with registered_wrapper(OPTIONS=OPTIONS) as wrapper:
        with transaction.atomic(using=wrapper.alias):
            with pytest.raises(NotSupportedError, match="outside an active transaction"):
                with wrapper.schema_editor():
                    pass
        assert wrapper.transaction_mode == "CONCURRENT"


def test_commit_conflict_discards_callbacks_and_preserves_committed_data(tmp_path: Path) -> None:
    path = tmp_path / "commit.db"
    with registered_wrapper(NAME=path, OPTIONS=OPTIONS) as a, registered_wrapper(
        NAME=path, OPTIONS=OPTIONS
    ) as b:
        a.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY,n INTEGER UNIQUE)")
        callbacks: list[str] = []
        with pytest.raises(DatabaseError, match="conflict"):
            with transaction.atomic(using=b.alias):
                with transaction.atomic(using=a.alias):
                    a.cursor().execute("INSERT INTO t VALUES(1,10)")
                    b.cursor().execute("INSERT INTO t VALUES(2,10)")
                    transaction.on_commit(lambda: callbacks.append("lost"), using=b.alias)
        assert callbacks == []
        assert b.get_autocommit()
        with transaction.atomic(using=b.alias):
            b.cursor().execute("INSERT INTO t VALUES(2,20)")
    with registered_wrapper(NAME=path, OPTIONS=OPTIONS) as reopened:
        assert reopened.cursor().execute("SELECT * FROM t ORDER BY id").fetchall() == [
            (1, 10), (2, 20)
        ]


def test_schema_entry_failure_restores_transaction_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    with registered_wrapper(OPTIONS=OPTIONS) as wrapper:
        wrapper.ensure_connection()

        def fail_begin() -> None:
            raise DatabaseError("injected begin failure")

        monkeypatch.setattr(wrapper, "_start_transaction_under_autocommit", fail_begin)
        with pytest.raises(DatabaseError, match="injected begin failure"):
            with wrapper.schema_editor():
                pass
        assert wrapper.transaction_mode == "CONCURRENT"
        assert wrapper.cursor().execute("PRAGMA foreign_keys").fetchone() == (1,)
