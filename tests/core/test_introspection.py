"""Turso-backed schema introspection tests."""

from typing import Any

import pytest
from django.db import DatabaseError, connection

from django_pyturso.introspection import FlexibleFieldLookupDict


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
