"""Focused tests for small backend support modules."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import sqlparse
from django.db import DatabaseError, NotSupportedError, connection

from django_pyturso.base import DatabaseWrapper
from django_pyturso.client import DatabaseClient
from django_pyturso.creation import DatabaseCreation
from django_pyturso.features import DatabaseFeatures
from django_pyturso.introspection import DatabaseIntrospection, FlexibleFieldLookupDict
from tests.core.test_connection import wrapper_settings


def _creation(*, name: object = ":memory:", test_name: object = None) -> DatabaseCreation:
    wrapper = DatabaseWrapper(wrapper_settings(NAME=name), "probe")
    wrapper.settings_dict["TEST"]["NAME"] = test_name
    return cast(DatabaseCreation, wrapper.creation)


def test_client_rejects_external_shell() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "probe")
    client = cast(DatabaseClient, wrapper.client)
    with pytest.raises(NotSupportedError, match="doesn't provide dbshell"):
        client.runshell(["--version"])


def test_creation_name_overrides_and_path_shaped_memory(tmp_path: Path) -> None:
    configured = tmp_path / "configured.db"
    creation = _creation(name=tmp_path / "source.db", test_name=configured)
    assert creation._get_test_db_name() == str(configured)
    assert DatabaseCreation.is_in_memory_db(":memory:")
    assert DatabaseCreation.is_in_memory_db(Path(":memory:"))
    assert not DatabaseCreation.is_in_memory_db(object())


def test_creation_fast_paths_and_file_signature(tmp_path: Path) -> None:
    memory = _creation()
    assert memory._create_test_db(verbosity=0, autoclobber=False) == ":memory:"

    source = tmp_path / "app.db"
    file_creation = _creation(name=source)
    expected = str(tmp_path / "test_app.db")
    assert file_creation._create_test_db(verbosity=0, autoclobber=True) == expected
    assert file_creation._create_test_db(verbosity=0, autoclobber=False, keepdb=True) == expected
    assert file_creation.test_db_signature() == (source, expected)


def test_creation_existing_database_prompt_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_database = tmp_path / "test_app.db"
    test_database.write_text("old")
    creation = _creation(name=tmp_path / "app.db")
    messages: list[str] = []
    monkeypatch.setattr(creation, "log", messages.append)

    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(SystemExit) as cancelled:
        creation._create_test_db(verbosity=0, autoclobber=False)
    assert cancelled.value.code == 1
    assert messages == ["Tests cancelled."]

    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert creation._create_test_db(verbosity=0, autoclobber=False) == str(test_database)
    assert not test_database.exists()


def test_creation_remove_failure_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creation = _creation(name=tmp_path / "app.db")
    messages: list[str] = []
    monkeypatch.setattr(creation, "log", messages.append)

    def fail(path: Path) -> None:
        raise OSError("read only")

    monkeypatch.setattr(creation, "_remove_database_artifacts", fail)
    with pytest.raises(SystemExit) as failed:
        creation._create_test_db(verbosity=0, autoclobber=True)
    assert failed.value.code == 2
    assert messages == ["Unable to remove the old test database: read only"]


def test_creation_clone_destroy_and_mirror_branches(tmp_path: Path) -> None:
    memory = _creation()
    with pytest.raises(NotSupportedError, match="parallel"):
        memory.get_test_db_clone_settings("1")
    memory._destroy_test_db(":memory:", verbosity=0)
    memory._destroy_test_db("", verbosity=0)

    source = tmp_path / "primary.db"
    mirror = _creation(name=tmp_path / "mirror.db")
    mirror.set_as_test_mirror({"NAME": source})
    assert mirror.connection.settings_dict["NAME"] == source


def test_remove_database_artifacts_skips_absent_sidecars(tmp_path: Path) -> None:
    database = tmp_path / "database.db"
    database.write_text("content")
    DatabaseCreation._remove_database_artifacts(database)
    assert not database.exists()
    assert not Path(f"{database}-wal").exists()


def test_database_capability_methods_apply_fixed_declarations() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "capabilities")
    features = DatabaseFeatures(wrapper)
    assert features.supports_explaining_query_execution

    managed = SimpleNamespace(_meta=SimpleNamespace(managed=True))
    unmanaged = SimpleNamespace(_meta=SimpleNamespace(managed=False))
    assert not features.allows_group_by_selected_pks_on_model(managed)
    features.allows_group_by_selected_pks = True
    assert features.allows_group_by_selected_pks_on_model(managed)
    assert not features.allows_group_by_selected_pks_on_model(unmanaged)


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

    # Malformed definitions exercise conservative parser exits. They aren't
    # executed as SQL and must never create a false introspection claim.
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
    wrapper = DatabaseWrapper(wrapper_settings(), "probe")
    introspection = DatabaseIntrospection(wrapper)
    monkeypatch.setattr(introspection, "get_primary_key_columns", lambda cursor, table: ["id"])
    rows = [(0, 0, "target", "left", None), (0, 1, "target", "right", None)]
    with pytest.raises(DatabaseError, match="Cannot resolve foreign key target columns"):
        introspection._target_columns(SimpleNamespace(), "target", rows)
