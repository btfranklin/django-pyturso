"""MVCC initialization must fail closed and release open resources."""

from typing import Any

import pytest
import turso
from django.db import DatabaseError

from django_pyturso.base import DatabaseWrapper
from tests.support import wrapper_settings


class JournalCursor:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.statements: list[str] = []
        self.closed = False
        self.read_count = 0

    def execute(self, statement: str) -> None:
        self.statements.append(statement)
        if self.scenario == "write" and statement == "PRAGMA journal_mode = MVCC":
            raise turso.OperationalError("injected journal write failure")

    def fetchone(self) -> tuple[object, ...] | None:
        assert self.statements[-1] == "PRAGMA journal_mode"
        self.read_count += 1
        if self.scenario == "missing" or (
            self.scenario == "missing-readback" and self.read_count == 2
        ):
            return None
        if self.scenario == "nontext":
            return (3,)
        if self.scenario == "unknown":
            return ("delete",)
        return ("wal",)

    def fetchall(self) -> list[tuple[str]]:
        if self.scenario == "drain":
            raise turso.OperationalError("injected journal completion failure")
        return [("mvcc",)]

    def close(self) -> None:
        self.closed = True


class JournalConnection:
    def __init__(self, scenario: str) -> None:
        self.cursor_instance = JournalCursor(scenario)
        self.closed = False

    def cursor(self) -> JournalCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("scenario", "exception"),
    [
        ("missing", DatabaseError),
        ("nontext", DatabaseError),
        ("unknown", DatabaseError),
        ("write", turso.OperationalError),
        ("drain", turso.OperationalError),
        ("missing-readback", DatabaseError),
        ("unchanged-readback", DatabaseError),
    ],
)
def test_journal_initialization_failure_closes_resources(
    monkeypatch: pytest.MonkeyPatch, scenario: str, exception: type[Exception]
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(OPTIONS={"journal_mode": "MVCC"}), "failed_mvcc")
    physical = JournalConnection(scenario)
    received: list[dict[str, Any]] = []

    def connect(**params: Any) -> JournalConnection:
        received.append(params)
        return physical

    monkeypatch.setattr("django_pyturso.base.Database.connect", connect)
    with pytest.raises(exception):
        wrapper.get_new_connection(wrapper.get_connection_params())
    assert received == [{"database": ":memory:", "isolation_level": None}]
    assert physical.closed
    assert physical.cursor_instance.closed
    assert not any("foreign_keys" in sql for sql in physical.cursor_instance.statements)
    assert wrapper.connection is None
