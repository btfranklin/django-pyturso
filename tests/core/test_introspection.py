"""Turso-backed schema introspection tests."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
import sqlparse
from django.db import DatabaseError, connection

from django_pyturso.base import DatabaseWrapper
from django_pyturso.introspection import DatabaseIntrospection, FlexibleFieldLookupDict
from tests.support import wrapper_settings


@pytest.mark.core
def test_table_description_type_affinity_and_composite_primary_key(
    django_db_blocker: Any,
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE intro_parent (
                part_a integer,
                part_b text,
                label varchar(40) COLLATE NOCASE,
                payload text CHECK (JSON_VALID(payload) OR payload IS NULL),
                CONSTRAINT uq_intro_label UNIQUE (label),
                CONSTRAINT ck_intro_part CHECK (part_a >= 0),
                PRIMARY KEY (part_a, part_b)
            )
            """
        )
        cursor.execute("CREATE VIEW intro_parent_view AS SELECT part_a, label FROM intro_parent")
        try:
            table_types = {
                info.name: info.type for info in connection.introspection.get_table_list(cursor)
            }
            assert table_types["intro_parent"] == "t"
            assert table_types["intro_parent_view"] == "v"
            assert "sqlite_sequence" not in table_types

            description = {
                info.name: info
                for info in connection.introspection.get_table_description(cursor, "intro_parent")
            }
            assert connection.introspection.get_primary_key_columns(cursor, "intro_parent") == [
                "part_a",
                "part_b",
            ]
            assert not description["part_a"].pk
            assert not description["part_b"].pk
            assert description["label"].display_size == 40
            assert description["label"].collation.casefold() == "nocase"
            assert (
                connection.introspection.get_field_type(
                    description["label"].type_code, description["label"]
                )
                == "CharField"
            )
            assert (
                connection.introspection.get_field_type(
                    description["payload"].type_code, description["payload"]
                )
                == "JSONField"
            )
            assert connection.introspection.get_sequences(cursor, "intro_parent") == []

            constraints = connection.introspection.get_constraints(cursor, "intro_parent")
            assert constraints["__primary__"]["columns"] == ["part_a", "part_b"]
            assert constraints["__primary__"]["primary_key"]
            assert constraints["uq_intro_label"]["columns"] == ["label"]
            assert constraints["uq_intro_label"]["unique"]
            assert constraints["ck_intro_part"]["columns"] == ["part_a"]
            assert constraints["ck_intro_part"]["check"]
        finally:
            cursor.execute("DROP VIEW IF EXISTS intro_parent_view")
            cursor.execute("DROP TABLE IF EXISTS intro_parent")


@pytest.mark.core
def test_relations_sequences_and_index_constraints(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE intro_target (
                part_a integer,
                part_b text,
                PRIMARY KEY (part_a, part_b)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE intro_child (
                id integer PRIMARY KEY AUTOINCREMENT,
                part_a integer,
                part_b text,
                payload text,
                code text UNIQUE,
                CONSTRAINT fk_intro_pair
                    FOREIGN KEY (part_a, part_b)
                    REFERENCES intro_target (part_a, part_b)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE intro_implicit_child (
                part_a integer,
                part_b text,
                FOREIGN KEY (part_a, part_b) REFERENCES intro_target
            )
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX intro_payload_unique
            ON intro_child (payload DESC)
            WHERE payload IS NOT NULL
            """
        )
        cursor.execute("CREATE INDEX intro_payload_expression ON intro_child (LOWER(payload))")
        try:
            assert connection.introspection.get_relations(cursor, "intro_child") == {
                "part_a": ("part_a", "intro_target"),
                "part_b": ("part_b", "intro_target"),
            }
            assert connection.introspection.get_relations(cursor, "intro_implicit_child") == {
                "part_a": ("part_a", "intro_target"),
                "part_b": ("part_b", "intro_target"),
            }
            assert connection.introspection.get_sequences(cursor, "intro_child") == [
                {"table": "intro_child", "column": "id"}
            ]

            description = {
                info.name: info
                for info in connection.introspection.get_table_description(cursor, "intro_child")
            }
            assert description["id"].pk
            assert (
                connection.introspection.get_field_type(
                    description["id"].type_code, description["id"]
                )
                == "AutoField"
            )

            constraints = connection.introspection.get_constraints(cursor, "intro_child")
            foreign_keys = [
                constraint
                for constraint in constraints.values()
                if constraint["foreign_key"] is not None
            ]
            assert foreign_keys == [
                {
                    "columns": ["part_a", "part_b"],
                    "primary_key": False,
                    "unique": False,
                    "foreign_key": ("intro_target", "part_a"),
                    "check": False,
                    "index": False,
                }
            ]
            assert constraints["intro_payload_unique"]["columns"] == ["payload"]
            assert constraints["intro_payload_unique"]["orders"] == ["DESC"]
            assert constraints["intro_payload_unique"]["unique"]
            index_definition = constraints["intro_payload_unique"]["definition"]
            assert index_definition is not None
            assert "WHERE payload IS NOT NULL" in index_definition
            expression_columns = constraints["intro_payload_expression"]["columns"]
            assert len(expression_columns) == 1
            expression_column = expression_columns[0]
            assert expression_column is not None
            assert "lower" in expression_column.casefold()
            assert constraints["intro_payload_expression"]["type"] == "idx"
            assert any(
                constraint["unique"] and constraint["columns"] == ["code"]
                for constraint in constraints.values()
            )
        finally:
            cursor.execute("DROP TABLE IF EXISTS intro_child")
            cursor.execute("DROP TABLE IF EXISTS intro_implicit_child")
            cursor.execute("DROP TABLE IF EXISTS intro_target")


@pytest.mark.core
def test_missing_table_description_is_an_error(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        with pytest.raises(DatabaseError, match="does not exist"):
            connection.introspection.get_table_description(cursor, "intro_missing")


@pytest.mark.core
def test_json_introspection_requires_exact_quoted_and_unquoted_column_names(
    django_db_blocker: Any,
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE intro_json_prefixes (
                a text,
                abc text CHECK (JSON_VALID(abc) OR abc IS NULL),
                "quoted" text,
                "quoted suffix" text CHECK (
                    JSON_VALID("quoted suffix") OR "quoted suffix" IS NULL
                )
            )
            """
        )
        try:
            description = {
                field.name: field
                for field in connection.introspection.get_table_description(
                    cursor, "intro_json_prefixes"
                )
            }
            field_types = {
                name: connection.introspection.get_field_type(field.type_code, field)
                for name, field in description.items()
            }
            assert field_types == {
                "a": "TextField",
                "abc": "JSONField",
                "quoted": "TextField",
                "quoted suffix": "JSONField",
            }
        finally:
            cursor.execute("DROP TABLE intro_json_prefixes")


def test_flexible_type_affinity_fallbacks() -> None:
    types = FlexibleFieldLookupDict()
    assert types["VARCHAR(12)"] == "CharField"
    assert types["UNSIGNED BIG INT"] == "IntegerField"
    assert types["DOUBLE PRECISION"] == "FloatField"
    assert types["CUSTOM TEXT VALUE"] == "TextField"
    assert types[""] == "BinaryField"
    assert types["NUMERIC(10, 2)"] == "DecimalField"


def test_introspection_fallback_and_empty_helper_branches() -> None:
    assert FlexibleFieldLookupDict()["custom_type"] == "DecimalField"
    assert DatabaseIntrospection._parse_table_constraints("", {"value"}) == {}
    assert DatabaseIntrospection._parse_table_constraints("CREATE TABLE sample", {"value"}) == {}
    assert DatabaseIntrospection._get_column_collations(None) == {}
    assert DatabaseIntrospection._get_column_sizes(None) == {}
    assert DatabaseIntrospection._get_json_columns(None, {"value"}) == set()
    assert DatabaseIntrospection._leading_identifier("") is None
    assert DatabaseIntrospection._leading_identifier("   ") is None
    assert DatabaseIntrospection._leading_identifier('"a""b" text') == 'a"b'
    assert DatabaseIntrospection._leading_identifier("`backtick` text") == "backtick"
    assert DatabaseIntrospection._leading_identifier("[bracket] text") == "bracket"
    assert DatabaseIntrospection._leading_identifier("plain text") == "plain"
    assert DatabaseIntrospection._split_table_definitions("CREATE TABLE sample") == []


def test_json_column_detection_is_exact_and_conservative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    quoted_sql = """
        CREATE TABLE sample (
            short text,
            `backtick suffix` text CHECK (JSON_VALID(`backtick suffix`)),
            [bracket suffix] text CHECK (JSON_VALID([bracket suffix]))
        )
    """
    assert DatabaseIntrospection._get_json_columns(
        quoted_sql, {"short", "backtick suffix", "bracket suffix"}
    ) == {"backtick suffix", "bracket suffix"}
    assert (
        DatabaseIntrospection._get_json_columns(
            "CREATE TABLE sample (value text CHECK (JSON_VALID(CAST(value AS TEXT))))",
            {"value"},
        )
        == set()
    )
    assert (
        DatabaseIntrospection._get_json_columns(
            "CREATE TABLE sample (other text CHECK (JSON_VALID(other)))", {"value"}
        )
        == set()
    )

    monkeypatch.setattr("django_pyturso.introspection.sqlparse.parse", lambda sql: [])
    assert DatabaseIntrospection._get_json_columns("malformed", {"value"}) == set()


def test_introspection_definition_splitter_quotes_nesting_and_malformed_sql() -> None:
    sql = """
        CREATE TABLE sample (
            "a""b" text DEFAULT 'x,y',
            `backtick` text,
            [bracket] text,
            nested text CHECK (nested IN ('a,b', 'c')),
            plain text
        )
    """
    definitions = DatabaseIntrospection._split_table_definitions(sql)
    assert len(definitions) == 5
    assert definitions[0] == '"a""b" text DEFAULT \'x,y\''
    assert definitions[2] == "[bracket] text"
    assert "('a,b', 'c')" in definitions[3]
    assert DatabaseIntrospection._split_table_definitions("CREATE TABLE x (a int,, b int)") == [
        "a int",
        "b int",
    ]
    assert DatabaseIntrospection._split_table_definitions("CREATE TABLE x (a int,)") == ["a int"]
    assert DatabaseIntrospection._split_table_definitions("CREATE TABLE x (a int") == []


def test_introspection_constraint_parser_quoted_and_empty_branches() -> None:
    sql = """
        CREATE TABLE sample (
            "quoted field" text UNIQUE,
            other text,
            CONSTRAINT "quoted unique" UNIQUE ("quoted field", other),
        CONSTRAINT "quoted check" CHECK (other <> '' AND other <> '')
        )
    """
    constraints = DatabaseIntrospection._parse_table_constraints(sql, {"quoted field", "other"})
    assert constraints["__unnamed_constraint_1__"]["columns"] == ["quoted field"]
    assert constraints["quoted unique"]["columns"] == ["quoted field", "other"]
    assert constraints["quoted check"]["columns"] == ["other"]

    empty: Iterator[Any] = iter(())
    with pytest.raises(DatabaseError, match="empty table definition"):
        DatabaseIntrospection._parse_column_or_constraint_definition(empty, {"value"})

    unrecognized_constraint_name = iter(
        [
            sqlparse.sql.Token(sqlparse.tokens.Keyword, "CONSTRAINT"),  # type: ignore[no-untyped-call]
            sqlparse.sql.Token(sqlparse.tokens.Punctuation, "@"),  # type: ignore[no-untyped-call]
            sqlparse.sql.Token(sqlparse.tokens.Punctuation, ","),  # type: ignore[no-untyped-call]
        ]
    )
    name, unique, check, _ = DatabaseIntrospection._parse_column_or_constraint_definition(
        unrecognized_constraint_name, {"value"}
    )
    assert (name, unique, check) == (None, None, None)

    assert (
        DatabaseIntrospection._parse_table_constraints(
            "CREATE TABLE x (CONSTRAINT [bad] CHECK (missing))", {"actual"}
        )
        == {}
    )
    assert (
        DatabaseIntrospection._parse_table_constraints(
            "CREATE TABLE x (CONSTRAINT empty UNIQUE ())", {"actual"}
        )
        == {}
    )
    DatabaseIntrospection._parse_table_constraints("CREATE TABLE x (123 UNIQUE)", {"actual"})
    assert (
        DatabaseIntrospection._parse_table_constraints(
            "CREATE TABLE x (actual text CHECK (missing))", {"actual"}
        )
        == {}
    )


def test_leading_identifier_with_only_whitespace_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statement = SimpleNamespace(flatten=lambda: [SimpleNamespace(is_whitespace=True)])
    monkeypatch.setattr(
        "django_pyturso.introspection.sqlparse.parse", lambda definition: [statement]
    )
    assert DatabaseIntrospection._leading_identifier("synthetic") is None


@pytest.mark.core
def test_introspection_no_primary_key_and_constraint_edge_branches(
    django_db_blocker: Any,
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute("CREATE TABLE support_no_pk (value text, other text)")
        cursor.execute("CREATE INDEX support_no_pk_idx ON support_no_pk (value ASC)")
        try:
            assert connection.introspection.get_primary_key_columns(cursor, "support_no_pk") is None
            assert connection.introspection.get_sequences(cursor, "support_no_pk") == []
            constraints = connection.introspection.get_constraints(cursor, "support_no_pk")
            assert "__primary__" not in constraints
            assert constraints["support_no_pk_idx"]["orders"] == ["ASC"]
        finally:
            cursor.execute("DROP TABLE support_no_pk")


def test_introspection_omitted_target_mismatch_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    introspection = DatabaseIntrospection(DatabaseWrapper(wrapper_settings(), "probe"))
    monkeypatch.setattr(introspection, "get_primary_key_columns", lambda cursor, table: ["id"])
    rows = [(0, 0, "target", "left", None), (0, 1, "target", "right", None)]
    with pytest.raises(DatabaseError, match="Cannot resolve foreign key target columns"):
        introspection._resolve_foreign_key_target_columns(SimpleNamespace(), "target", rows)
