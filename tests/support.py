"""Small test-only helpers shared by backend surface tests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, cast

import turso
from django.db.backends.utils import CursorWrapper

from django_pyturso._typing import Parameters
from django_pyturso.base import DatabaseWrapper


def wrapper_settings(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
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


def physical_connection(wrapper: DatabaseWrapper) -> turso.Connection:
    connection = wrapper.connection
    assert connection is not None
    return connection


class ParameterCursor(Protocol):
    def execute(self, query: str, params: Parameters | None = None) -> object: ...

    def executemany(self, query: str, params: Iterable[Parameters]) -> object: ...


def parameter_cursor(cursor: CursorWrapper) -> ParameterCursor:
    # Django's stubs exclude parameter iterators supported by this backend.
    return cast(ParameterCursor, cursor)
