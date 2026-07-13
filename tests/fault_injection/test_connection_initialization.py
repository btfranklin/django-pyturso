"""Post-open connection initialization cleanup fault injection."""

from __future__ import annotations

from typing import Any

import pytest
import turso
from django.db import DatabaseError

from django_pyturso.base import DatabaseWrapper


def wrapper_settings() -> dict[str, Any]:
    return {
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


class InitializationCursor:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.statement = ""
        self.closed = False

    def execute(self, statement: str) -> InitializationCursor:
        self.statement = statement
        if self.scenario == "pragma-write" and statement == "PRAGMA foreign_keys = ON":
            raise turso.OperationalError("injected pragma failure")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        if self.statement == "PRAGMA foreign_keys":
            return (0,) if self.scenario == "pragma-readback" else (1,)
        if self.statement == "SELECT sqlite_version()":
            if self.scenario == "missing-version":
                return None
            if self.scenario == "nontext-version":
                return (350,)
            if self.scenario == "invalid-version":
                return ("invalid",)
            return ("3.50.4",)
        raise AssertionError(f"unexpected fetch for {self.statement!r}")

    def close(self) -> None:
        self.closed = True


class InitializationConnection:
    def __init__(self, scenario: str) -> None:
        self.cursor_instance = InitializationCursor(scenario)
        self.closed = False

    def cursor(self) -> InitializationCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("scenario", "expected_exception"),
    [
        ("pragma-write", turso.OperationalError),
        ("pragma-readback", DatabaseError),
        ("missing-version", DatabaseError),
        ("nontext-version", DatabaseError),
        ("invalid-version", DatabaseError),
    ],
)
def test_post_open_initialization_failure_closes_cursor_and_connection(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_exception: type[BaseException],
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "fault_initialization")
    physical = InitializationConnection(scenario)
    monkeypatch.setattr("django_pyturso.base.Database.connect", lambda **params: physical)

    with pytest.raises(expected_exception):
        wrapper.get_new_connection({"database": ":memory:", "isolation_level": None})

    assert physical.cursor_instance.closed is True
    assert physical.closed is True
    assert wrapper.connection is None


def test_non_driver_open_error_is_not_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "fault_open")

    def fail_open(**params: object) -> None:
        raise RuntimeError("injected non-driver failure")

    monkeypatch.setattr("django_pyturso.base.Database.connect", fail_open)

    with pytest.raises(RuntimeError, match="injected non-driver failure"):
        wrapper.get_new_connection({"database": ":memory:", "isolation_level": None})
