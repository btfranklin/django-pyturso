"""RETURNING writes must finish before their transaction boundary."""

from pathlib import Path
from typing import Any

import pytest
from django.db import transaction

from tests.core.transactions.test_cursor_fetch import MODES
from tests.core.transactions.test_state_machine import registered_wrapper

pytestmark = pytest.mark.core


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize("boundary", ["commit", "rollback", "savepoint"])
@pytest.mark.parametrize("partial_fetch", [False, True])
def test_returning_write_obeys_original_atomic_boundary(
    django_db_blocker: Any,
    tmp_path: Path,
    options: dict[str, str],
    boundary: str,
    partial_fetch: bool,
) -> None:
    with django_db_blocker.unblock(), registered_wrapper(
        NAME=tmp_path / "returning.db", OPTIONS=options
    ) as wrapper:
        wrapper.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY)")
        observed: list[list[tuple[int]]] = []
        with wrapper.cursor() as pending:
            with transaction.atomic(using=wrapper.alias):
                transaction.on_commit(
                    lambda: observed.append(
                        wrapper.cursor().execute("SELECT id FROM t ORDER BY id").fetchall()
                    ),
                    using=wrapper.alias,
                )
                with transaction.atomic(using=wrapper.alias):
                    pending.execute("INSERT INTO t VALUES(1),(2),(3) RETURNING id")
                    if partial_fetch:
                        assert pending.fetchone() == (1,)
                    if boundary == "savepoint":
                        transaction.set_rollback(True, using=wrapper.alias)
                if boundary == "rollback":
                    transaction.set_rollback(True, using=wrapper.alias)
            expected = [(1,), (2,), (3,)] if boundary == "commit" else []
            assert wrapper.cursor().execute("SELECT id FROM t ORDER BY id").fetchall() == expected
            assert observed == ([] if boundary == "rollback" else [expected])
            assert pending.fetchall() == ([(2,), (3,)] if partial_fetch else [(1,), (2,), (3,)])
            assert wrapper.cursor().execute("SELECT id FROM t ORDER BY id").fetchall() == expected


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("; /* write */ INSERT INTO t VALUES(3),(4) RETURNING id", [(1,), (2,), (3,), (4,)]),
        ("WITH ids AS (SELECT 3) INSERT INTO t SELECT * FROM ids RETURNING id", [(1,), (2,), (3,)]),
        ("UPDATE t SET id=id+10 RETURNING id", [(11,), (12,)]),
        ("DELETE FROM t RETURNING id", []),
        ("REPLACE INTO t VALUES(2),(3) RETURNING id", [(1,), (2,), (3,)]),
    ],
)
def test_returning_write_is_complete_before_fetch(
    django_db_blocker: Any, tmp_path: Path, options: dict[str, str], sql: str,
    expected: list[tuple[int]],
) -> None:
    with django_db_blocker.unblock(), registered_wrapper(
        NAME=tmp_path / "returning.db", OPTIONS=options
    ) as wrapper:
        wrapper.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY)")
        wrapper.cursor().execute("INSERT INTO t VALUES(1),(2)")
        with wrapper.cursor() as pending:
            pending.execute(sql)
            assert wrapper.cursor().execute("SELECT id FROM t ORDER BY id").fetchall() == expected


def test_returning_results_follow_cursor_fetch_and_reuse_rules(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), registered_wrapper() as wrapper:
        wrapper.cursor().execute("CREATE TABLE t(id INTEGER PRIMARY KEY)")
        cursor = wrapper.cursor()
        cursor.execute("INSERT INTO t VALUES(1),(2),(3) RETURNING id")
        assert cursor.description[0][0] == "id"
        assert cursor.fetchmany(0) == []
        with pytest.raises(ValueError, match="non-negative"):
            cursor.fetchmany(-1)
        cursor.cursor.arraysize = 2
        assert cursor.fetchmany() == [(1,), (2,)]
        assert cursor.fetchone() == (3,)
        assert cursor.fetchone() is None
        assert cursor.fetchall() == []
        cursor.execute("UPDATE t SET id=id+10 RETURNING id")
        cursor.execute("SELECT 99")
        assert cursor.fetchall() == [(99,)]
        cursor.execute("DELETE FROM t RETURNING id")
        cursor.executemany("INSERT INTO t VALUES(%s)", [(4,), (5,)])
        assert cursor.fetchall() == []
        cursor.execute("DELETE FROM t RETURNING id")
        cursor.close()
        with pytest.raises(wrapper.Database.ProgrammingError, match="closed cursor"):
            cursor.cursor.fetchone()


def test_large_select_does_not_require_sql_grouping(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), registered_wrapper() as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute("SELECT 1 WHERE 1 IN (" + ",".join(["%s"] * 6000) + ")", [1] * 6000)
            assert cursor.fetchall() == [(1,)]
