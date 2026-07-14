"""SQL parameter and identifier safety at the backend boundary."""

from typing import Any

import pytest
from django.db import DatabaseError, connection


@pytest.mark.core
def test_bound_values_and_literal_percent_are_never_sql_text(django_db_blocker: Any) -> None:
    payload = "value'); DROP TABLE security_values; -- 100%"
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute("CREATE TABLE security_values (value text)")
        cursor.execute("INSERT INTO security_values(value) VALUES (%s)", (payload,))
        cursor.execute(
            "SELECT %s, '100%%', '%s' /* %s / * stays inert */, %s -- %s\n, %s",
            (payload, "after-block", "after-line"),
        )
        assert cursor.fetchone() == (payload, "100%", "%s", "after-block", "after-line")
        cursor.execute("SELECT value FROM security_values")
        assert cursor.fetchone() == (payload,)


@pytest.mark.core
def test_named_parameters_and_executemany_remain_bound(django_db_blocker: Any) -> None:
    values = ["plain", "x'); DELETE FROM security_named; --", "100%_literal"]
    table_name = "security_named_%s_%%"
    column_name = "value_%(value)s_%s_%%"
    quote = connection.ops.quote_name
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE {quote(table_name)} ({quote(column_name)} text)")
        cursor.executemany(
            f"INSERT INTO {quote(table_name)}({quote(column_name)}) VALUES (%(value)s)",
            [{"value": value} for value in values],
        )
        cursor.execute(
            f"SELECT {quote(column_name)} FROM {quote(table_name)} "
            f"WHERE {quote(column_name)} = %(value)s",
            {"value": values[1]},
        )
        assert cursor.fetchone() == (values[1],)
        cursor.execute(f"SELECT COUNT(*) FROM {quote(table_name)}")
        assert cursor.fetchone() == (3,)


@pytest.mark.core
def test_regexp_input_is_bound_and_fts_is_not_an_exposed_surface(django_db_blocker: Any) -> None:
    injection_shaped_pattern = r"^safe'; DROP TABLE security_regex; --$"
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute("CREATE TABLE security_regex (value text)")
        cursor.execute("INSERT INTO security_regex(value) VALUES (%s)", ("safe",))
        cursor.execute(
            "SELECT COUNT(*) FROM security_regex WHERE value REGEXP %s",
            (injection_shaped_pattern,),
        )
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT COUNT(*) FROM security_regex")
        assert cursor.fetchone() == (1,)

        # The audited embedded engine doesn't expose FTS5, so v1 has no FTS
        # query-input boundary. Re-probe this before exposing any FTS API.
        with pytest.raises(DatabaseError, match="no such module: fts5"):
            cursor.execute("CREATE VIRTUAL TABLE security_fts USING fts5(body)")


@pytest.mark.core
def test_metadata_identifiers_are_quoted_as_single_identifiers(django_db_blocker: Any) -> None:
    # Keep the corpus casefold-stable because pyturso 0.7.0 normalizes quoted
    # identifiers; that separate driver boundary is documented and probed by
    # the property suite.
    table_name = 'metadata"; create table injected(value); --'
    column_name = 'column"; drop table injected; --'
    quote = connection.ops.quote_name
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE {quote(table_name)} ({quote(column_name)} text)")
        cursor.execute(
            f"INSERT INTO {quote(table_name)} ({quote(column_name)}) VALUES (%s)",
            ("preserved",),
        )
        cursor.execute(f"SELECT {quote(column_name)} FROM {quote(table_name)}")
        assert cursor.fetchone() == ("preserved",)
        assert table_name in connection.introspection.table_names(cursor)
        assert "injected" not in connection.introspection.table_names(cursor)
