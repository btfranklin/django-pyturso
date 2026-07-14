"""Connection and settings contract tests."""

from pathlib import Path
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from django_pyturso.base import DatabaseWrapper, TursoCursorWrapper


class BytesPath:
    def __fspath__(self) -> bytes:
        return b"local.db"


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


@pytest.mark.core
def test_memory_connection_uses_turso_and_enables_foreign_keys(
    django_db_blocker: Any,
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute("SELECT sqlite_version(), 1")
        version, value = cursor.fetchone()
        cursor.execute("PRAGMA foreign_keys")
        foreign_keys = cursor.fetchone()[0]
    assert version.startswith("3.")
    assert value == 1
    assert foreign_keys == 1
    assert connection.connection.__class__.__module__ == "turso.lib"


@pytest.mark.core
def test_file_connection_round_trip(tmp_path: Path, django_db_blocker: Any) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(NAME=tmp_path / "local.db"), "probe")
    try:
        with django_db_blocker.unblock(), wrapper.cursor() as cursor:
            cursor.execute("CREATE TABLE sample (value text)")
            cursor.execute("INSERT INTO sample VALUES (%s)", ("ok",))
            cursor.execute("SELECT value FROM sample")
            assert cursor.fetchone() == ("ok",)
    finally:
        wrapper.close()


def test_pathlike_memory_name_uses_memory_connection_and_lifecycle_semantics() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(NAME=Path(":memory:")), "probe")

    assert wrapper.get_connection_params()["database"] == ":memory:"
    assert wrapper.is_in_memory_db()
    assert not DatabaseWrapper(wrapper_settings(NAME=object()), "invalid").is_in_memory_db()


@pytest.mark.parametrize(
    "overrides",
    [
        {"NAME": ""},
        {"NAME": object()},
        {"NAME": BytesPath()},
        {"NAME": "file:local.db"},
        {"NAME": "https://example.com/db"},
        {"HOST": "localhost"},
        {"OPTIONS": {"check_same_thread": False}},
        {"OPTIONS": {"transaction_mode": "EXCLUSIVE"}},
    ],
)
def test_invalid_settings_are_rejected(overrides: dict[str, Any]) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(**overrides), "probe")
    with pytest.raises(ImproperlyConfigured):
        wrapper.get_connection_params()


def test_cursor_parameter_conversion() -> None:
    assert TursoCursorWrapper.convert_query("SELECT %s, '%%'") == "SELECT ?, '%'"
    assert (
        TursoCursorWrapper.convert_query("SELECT %(value)s", param_names=["value"])
        == "SELECT :value"
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            'INSERT INTO "%s" ("%%") VALUES (%s)',
            'INSERT INTO "%s" ("%%") VALUES (?)',
        ),
        (
            "SELECT '%s', 'it''s %%', %s",
            "SELECT '%s', 'it''s %', ?",
        ),
        (
            "SELECT 'prefix_%s', status, %s / 2, 2 * %s",
            "SELECT 'prefix_%s', status, ? / 2, 2 * ?",
        ),
        (
            "SELECT `%s`, [%%], \"escaped\"\"%s\", %s",
            "SELECT `%s`, [%%], \"escaped\"\"%s\", ?",
        ),
        (
            'SELECT "prefix_%s", `prefix_%s`, [prefix_%s], %s',
            'SELECT "prefix_%s", `prefix_%s`, [prefix_%s], ?',
        ),
        (
            "SELECT %s -- %s and %%\r\n, %s /* * / %s and %% */ , %s",
            "SELECT ? -- %s and %%\r\n, ? /* * / %s and %% */ , ?",
        ),
        ("SELECT %%%% AS remainder, %%%s", "SELECT %% AS remainder, %?"),
    ],
)
def test_positional_conversion_respects_sql_lexical_boundaries(
    query: str, expected: str
) -> None:
    assert TursoCursorWrapper.convert_query(query) == expected


def test_named_conversion_respects_sql_lexical_boundaries() -> None:
    query = (
        'SELECT "%(value)s", `%s`, [%%], \'%(value)s %%\', %(value)s '
        "-- %(value)s\n/* %(value)s */"
    )
    expected = (
        'SELECT "%(value)s", `%s`, [%%], \'%(value)s %\', :value '
        "-- %(value)s\n/* %(value)s */"
    )

    assert TursoCursorWrapper.convert_query(query, param_names=["value"]) == expected
    with pytest.raises(KeyError, match="missing"):
        TursoCursorWrapper.convert_query("SELECT %(missing)s", param_names=["value"])


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ('SELECT "unterminated %s', 'SELECT "unterminated %s'),
        ("SELECT 'unterminated %s %%", "SELECT 'unterminated %s %"),
        ("SELECT 1 /* unterminated %s %%", "SELECT 1 /* unterminated %s %%"),
        ("SELECT %(broken)q, %(value", "SELECT %(broken)q, %(value"),
    ],
)
def test_conversion_does_not_bind_unterminated_sql_regions(
    query: str, expected: str
) -> None:
    assert TursoCursorWrapper.convert_query(query, param_names=["value"]) == expected


def test_malformed_named_placeholder_does_not_consume_a_later_binding() -> None:
    query = "SELECT %(broken)q, %(outer %(value)s"

    assert (
        TursoCursorWrapper.convert_query(query, param_names=["value"])
        == "SELECT %(broken)q, %(outer :value"
    )
