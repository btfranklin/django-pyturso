"""Reject incomplete parameter rows before the driver can store NULL values."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from django.db import ProgrammingError, transaction

from tests.core.transactions.test_cursor_fetch import MODES
from tests.core.transactions.test_state_machine import registered_wrapper

pytestmark = pytest.mark.core


@pytest.fixture(autouse=True)
def unblock_database_access(django_db_blocker: Any) -> Iterator[None]:
    with django_db_blocker.unblock():
        yield


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
def test_missing_named_parameter_in_later_row_rolls_back_batch(
    tmp_path: Path, options: dict[str, str]
) -> None:
    with registered_wrapper(NAME=tmp_path / "bindings.db", OPTIONS=options) as wrapper:
        cursor = wrapper.cursor()
        cursor.execute("CREATE TABLE t(a INTEGER, b INTEGER)")
        with pytest.raises(KeyError, match="b"), transaction.atomic(using=wrapper.alias):
            cursor.executemany(
                "INSERT INTO t VALUES(%(a)s,%(b)s)", [{"a": 1, "b": 2}, {"a": 3}]
            )
        assert cursor.execute("SELECT * FROM t").fetchall() == []


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize("params", [(), (1,), (1, 2, 3)], ids=["empty", "short", "long"])
@pytest.mark.parametrize("many", [False, True], ids=["execute", "executemany"])
def test_positional_parameter_count_error_rolls_back_transaction(
    tmp_path: Path, options: dict[str, str], params: tuple[int, ...], many: bool
) -> None:
    with registered_wrapper(NAME=tmp_path / "bindings.db", OPTIONS=options) as wrapper:
        cursor = wrapper.cursor()
        cursor.execute("CREATE TABLE t(a INTEGER, b INTEGER)")
        with pytest.raises(ProgrammingError), transaction.atomic(using=wrapper.alias):
            cursor.execute("INSERT INTO t VALUES(%s,%s)", (5, 6))
            if many:
                cursor.executemany("INSERT INTO t VALUES(%s,%s)", [(1, 2), params])
            else:
                cursor.execute("INSERT INTO t VALUES(%s,%s)", params)
        assert cursor.execute("SELECT * FROM t").fetchall() == []


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
def test_parameter_requirements_ignore_quoted_text_and_comments(
    tmp_path: Path, options: dict[str, str]
) -> None:
    with registered_wrapper(NAME=tmp_path / "bindings.db", OPTIONS=options) as wrapper:
        cursor = wrapper.cursor()
        cursor.execute('CREATE TABLE t("%s ?" INTEGER, "%(unused)s" INTEGER, note TEXT)')
        cursor.execute(
            'INSERT INTO t("%s ?", "%(unused)s", note) '
            "VALUES(%s, %s, '%s ? %(unused)s') /* %s ? %(unused)s */ -- %s ?\n",
            (1, None),
        )
        cursor.executemany(
            'INSERT INTO t("%s ?", "%(unused)s", note) '
            "VALUES(%(value)s, %(value)s, '%(unused)s ?') /* %(unused)s */ -- %(unused)s\n",
            [{"value": 2, "extra": 9}, {"value": None, "different": 8}],
        )
        cursor.executemany("INSERT INTO t VALUES(%s, %s, %s)", cast(Any, iter(())))
        cursor.executemany("INSERT INTO t VALUES(%(a)s, %(b)s, %(c)s)", cast(Any, iter(())))
        assert cursor.execute('SELECT "%s ?", "%(unused)s", note FROM t').fetchall() == [
            (1, None, "%s ? %(unused)s"),
            (2, 2, "%(unused)s ?"),
            (None, None, "%(unused)s ?"),
        ]


def test_native_placeholders_remain_usable() -> None:
    with registered_wrapper() as wrapper:
        cursor = wrapper.cursor()
        assert cursor.execute("SELECT ?2, ?1, ?2, '?'", (1, 2)).fetchall() == [(2, 1, 2, "?")]
        assert cursor.execute("SELECT :value, :value", {"value": 3}).fetchall() == [(3, 3)]
        assert cursor.execute("SELECT ?2, %s, ?1", (1, 2, 3)).fetchall() == [(2, 3, 1)]
        assert cursor.execute(
            "SELECT :native, %(value)s", {"native": 1, "value": 2}
        ).fetchall() == [(1, 2)]


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize("named", [False, True], ids=["positional", "named"])
def test_invalid_later_row_is_not_written_in_autocommit(
    tmp_path: Path, options: dict[str, str], named: bool
) -> None:
    with registered_wrapper(NAME=tmp_path / "bindings.db", OPTIONS=options) as wrapper:
        cursor = wrapper.cursor()
        cursor.execute("CREATE TABLE t(a INTEGER, b INTEGER)")
        query = "INSERT INTO t VALUES(%(a)s,%(b)s)" if named else "INSERT INTO t VALUES(%s,%s)"
        params = [{"a": 1, "b": 2}, {"a": 3}] if named else [(1, 2), (3,)]
        with pytest.raises(KeyError if named else ProgrammingError):
            cursor.executemany(query, params)
        assert cursor.execute("SELECT * FROM t").fetchall() == [(1, 2)]


def test_positional_parameter_iterators_are_checked_one_row_at_a_time() -> None:
    with registered_wrapper() as wrapper:
        cursor = wrapper.cursor()
        cursor.execute("CREATE TABLE t(a INTEGER, b INTEGER)")
        cursor.execute("INSERT INTO t VALUES(%s,%s)", cast(Any, iter((1, 2))))
        cursor.executemany(
            "INSERT INTO t VALUES(%s,%s)", cast(Any, (iter((3, 4)), iter((5, 6))))
        )
        with pytest.raises(ProgrammingError):
            cursor.execute("INSERT INTO t VALUES(%s,%s)", cast(Any, iter((7,))))
        with pytest.raises(ProgrammingError):
            cursor.executemany("INSERT INTO t VALUES(%s,%s)", cast(Any, [iter((7,))]))
        assert cursor.execute("SELECT * FROM t").fetchall() == [(1, 2), (3, 4), (5, 6)]
