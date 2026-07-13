"""Focused mutation tests for supported base-backend behavior."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError

from django_pyturso.base import DatabaseWrapper, _get_varchar_column
from tests.core.test_connection import wrapper_settings

pytestmark = pytest.mark.core


class RecordingConnection:
    def __init__(self) -> None:
        self.in_transaction = False
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


class RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def fetchone(self) -> None:
        return None


def attach(wrapper: DatabaseWrapper, connection: object) -> None:
    wrapper.connection = cast(Any, connection)


@pytest.mark.parametrize(
    ("max_length", "expected"),
    [(None, "varchar"), (0, "varchar(0)"), (32, "varchar(32)")],
)
def test_varchar_mapping_preserves_optional_max_length(
    max_length: int | None,
    expected: str,
) -> None:
    assert _get_varchar_column({"max_length": max_length}) == expected


def test_uppercase_url_scheme_is_rejected() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(NAME="HTTPS://example.com/database"), "url")

    with pytest.raises(ImproperlyConfigured):
        wrapper.get_connection_params()


@pytest.mark.parametrize("setting", ["HOST", "PORT", "USER", "PASSWORD"])
def test_remote_connection_settings_are_rejected(setting: str) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(**{setting: "configured"}), "remote")

    with pytest.raises(ImproperlyConfigured):
        wrapper.get_connection_params()


def test_transaction_mode_option_is_accepted_and_normalized() -> None:
    wrapper = DatabaseWrapper(
        wrapper_settings(OPTIONS={"transaction_mode": "immediate"}),
        "transaction_mode",
    )

    assert wrapper.get_connection_params() == {
        "database": ":memory:",
        "isolation_level": None,
    }
    assert wrapper.transaction_mode == "IMMEDIATE"


@pytest.mark.parametrize("version", ["3.two.1", "3.1"])
def test_database_version_rejects_each_malformed_shape(version: str) -> None:
    with pytest.raises(DatabaseError):
        DatabaseWrapper._parse_database_version(version)


def test_constraint_discovery_passes_the_live_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "constraint_discovery")
    cursor = RecordingCursor()
    received: list[object] = []
    checked: list[str] = []

    def table_names(candidate: object) -> list[str]:
        received.append(candidate)
        return ["child"]

    def foreign_keys(candidate: object, table: str) -> dict[int, list[tuple[Any, ...]]]:
        checked.append(table)
        return {}

    monkeypatch.setattr(wrapper, "cursor", lambda: cursor)
    monkeypatch.setattr(wrapper.introspection, "table_names", table_names)
    monkeypatch.setattr(wrapper, "_foreign_keys_by_id", foreign_keys)

    wrapper.check_constraints()

    assert received == [cursor]
    assert checked == ["child"]


def test_foreign_key_check_uses_quoted_child_and_parent_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "foreign_key_aliases")
    cursor = RecordingCursor()
    rows = [(0, 0, "parent", "parent_id", "id")]

    monkeypatch.setattr(
        wrapper,
        "_resolve_foreign_key_targets",
        lambda candidate, target, candidate_rows: ["id"],
    )
    monkeypatch.setattr(
        wrapper,
        "_source_identity",
        lambda candidate, table, alias: ([f'{alias}."id"'], ["id"]),
    )

    wrapper._check_foreign_key(cursor, "child", rows)

    assert cursor.statements == [
        'SELECT "django_pyturso_child"."id", '
        '"django_pyturso_child"."parent_id" FROM "child" AS '
        '"django_pyturso_child" WHERE '
        '"django_pyturso_child"."parent_id" IS NOT NULL AND NOT EXISTS '
        '(SELECT 1 FROM "parent" AS "django_pyturso_parent" WHERE '
        '"django_pyturso_parent"."id" = '
        '"django_pyturso_child"."parent_id") LIMIT 1'
    ]


def test_healthy_connection_executes_probe_and_is_usable() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "usable")
    physical = RecordingConnection()
    attach(wrapper, physical)

    assert wrapper.is_usable() is True
    assert physical.statements == ["SELECT 1"]


@pytest.mark.parametrize(
    ("has_connection", "health_check_enabled", "health_check_done"),
    [(False, True, False), (True, False, False), (True, True, True)],
)
def test_health_check_guards_skip_the_probe(
    monkeypatch: pytest.MonkeyPatch,
    has_connection: bool,
    health_check_enabled: bool,
    health_check_done: bool,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "health_guard")
    if has_connection:
        attach(wrapper, RecordingConnection())
    wrapper.health_check_enabled = health_check_enabled
    wrapper.health_check_done = health_check_done

    def unexpected_probe() -> bool:
        pytest.fail("guarded health check attempted a usability probe")

    monkeypatch.setattr(wrapper, "is_usable", unexpected_probe)

    wrapper.close_if_health_check_failed()

    assert wrapper.health_check_done is health_check_done


def test_memory_lifecycle_resets_health_check_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(CONN_MAX_AGE=None), "memory_lifecycle")
    physical = RecordingConnection()
    attach(wrapper, physical)
    wrapper.autocommit = True
    wrapper.health_check_done = True
    wrapper.errors_occurred = False
    wrapper.close_at = None
    monkeypatch.setattr(wrapper, "get_autocommit", lambda: True)

    wrapper.close_if_unusable_or_obsolete()

    assert wrapper.health_check_done is False
    assert wrapper.connection is physical


def test_named_parameters_execute_and_executemany_through_driver(
    django_db_blocker: Any,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "named_parameters")
    try:
        with django_db_blocker.unblock(), wrapper.cursor() as cursor:
            cursor.execute(
                "SELECT %(left)s + %(right)s",
                {"left": 2, "right": 3},
            )
            assert cursor.fetchone() == (5,)

            cursor.execute("CREATE TABLE sample (value TEXT)")
            cursor.executemany(
                "INSERT INTO sample VALUES (%(value)s)",
                ({"value": "first"}, {"value": "second"}),
            )
            empty_result = cursor.executemany(
                "INSERT INTO sample VALUES (%(value)s)",
                [],
            )
            assert empty_result is cursor.cursor
            cursor.execute("SELECT value FROM sample ORDER BY value")
            assert cursor.fetchall() == [("first",), ("second",)]
    finally:
        wrapper._force_close()
