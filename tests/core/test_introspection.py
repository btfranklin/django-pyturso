"""Turso-backed schema introspection tests."""

from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlparse
from django import VERSION as DJANGO_VERSION
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import DatabaseError, connection, models
from django.test.utils import isolate_apps

from django_pyturso.base import DatabaseWrapper
from django_pyturso.introspection import DatabaseIntrospection, FlexibleFieldLookupDict
from tests.core.transactions.test_state_machine import registered_wrapper
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
@pytest.mark.parametrize(
    "options",
    [{"journal_mode": "WAL"}, {"journal_mode": "MVCC", "transaction_mode": "CONCURRENT"}],
    ids=["wal", "mvcc"],
)
def test_table_list_and_inspectdb_hide_turso_autoincrement_metadata(
    django_db_blocker: Any, tmp_path: Path, options: dict[str, str]
) -> None:
    with django_db_blocker.unblock(), registered_wrapper(
        NAME=tmp_path / "introspection.db", OPTIONS=options
    ) as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE intro_autoincrement ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT)"
            )
            cursor.execute("INSERT INTO intro_autoincrement (value) VALUES ('present')")
            near_prefix_table = (
                "XXtursoXinternalXseqXXXtursoXinternalXautoincrementXuser"
            )
            cursor.execute(f'CREATE TABLE "{near_prefix_table}" (value TEXT)')
            cursor.execute(
                "CREATE VIEW intro_autoincrement_view AS "
                "SELECT value FROM intro_autoincrement"
            )

            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE name GLOB '__turso_internal_*'"
            )
            internal_names = {row[0] for row in cursor.fetchall()}
            assert (
                "__turso_internal_seq___turso_internal_autoincrement_intro_autoincrement"
                in internal_names
            )
            assert internal_names

            table_names = set(wrapper.introspection.table_names(cursor))
            assert internal_names.isdisjoint(table_names)
            assert "intro_autoincrement" in table_names
            assert near_prefix_table.lower() in table_names
            table_types = {
                info.name: info.type for info in wrapper.introspection.get_table_list(cursor)
            }
            assert table_types["intro_autoincrement_view"] == "v"

        output = StringIO()
        call_command("inspectdb", stdout=output, database=wrapper.alias)
        generated_models = output.getvalue()
        assert "class IntroAutoincrement(models.Model):" in generated_models
        assert f"db_table = '{near_prefix_table.lower()}'" in generated_models
        assert all(name not in generated_models for name in internal_names)


@pytest.mark.core
@pytest.mark.parametrize(
    "options",
    [{"journal_mode": "WAL"}, {"journal_mode": "MVCC", "transaction_mode": "CONCURRENT"}],
    ids=["wal", "mvcc"],
)
def test_sqlite_like_user_tables_remain_visible_and_cascade_flush(
    django_db_blocker: Any, tmp_path: Path, options: dict[str, str]
) -> None:
    with django_db_blocker.unblock(), registered_wrapper(
        NAME=tmp_path / "table_prefixes.db", OPTIONS=options
    ) as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute("CREATE TABLE prefix_parent (id INTEGER PRIMARY KEY AUTOINCREMENT)")
            cursor.execute(
                "CREATE TABLE sqlitereports_entry (id INTEGER PRIMARY KEY, parent_id INTEGER "
                "REFERENCES prefix_parent(id) DEFERRABLE INITIALLY DEFERRED)"
            )
            cursor.execute("CREATE VIEW sqlitereports_view AS SELECT id FROM sqlitereports_entry")
            cursor.execute("INSERT INTO prefix_parent DEFAULT VALUES")
            cursor.execute("INSERT INTO sqlitereports_entry VALUES(1, 1)")
            tables = wrapper.introspection.table_names(cursor)
            assert "sqlitereports_entry" in tables
            assert "sqlite_sequence" not in tables
            assert not any(name.startswith("__turso_internal_") for name in tables)
            assert "sqlitereports_view" in wrapper.introspection.table_names(
                cursor, include_views=True
            )

        output = StringIO()
        call_command("inspectdb", stdout=output, database=wrapper.alias)
        assert "db_table = 'sqlitereports_entry'" in output.getvalue()
        statements = wrapper.ops.sql_flush(no_style(), ["prefix_parent"], allow_cascade=True)
        wrapper.ops.execute_sql_flush(statements)
        with wrapper.cursor() as cursor:
            for table in ("prefix_parent", "sqlitereports_entry"):
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                assert cursor.fetchone() == (0,)


@pytest.mark.core
@pytest.mark.parametrize(
    "options",
    [{"journal_mode": "WAL"}, {"journal_mode": "MVCC", "transaction_mode": "CONCURRENT"}],
    ids=["wal", "mvcc"],
)
def test_inspectdb_foreign_keys_use_the_installed_django_relation_interface(
    django_db_blocker: Any, tmp_path: Path, options: dict[str, str]
) -> None:
    with django_db_blocker.unblock(), registered_wrapper(
        NAME=tmp_path / "relation_interface.db", OPTIONS=options
    ) as wrapper:
        with wrapper.cursor() as cursor:
            cursor.execute("CREATE TABLE relation_parent (id INTEGER PRIMARY KEY)")
            cursor.execute(
                "CREATE TABLE relation_child (id INTEGER PRIMARY KEY, parent_id INTEGER "
                "REFERENCES relation_parent(id) ON DELETE CASCADE)"
            )
            relation = wrapper.introspection.get_relations(cursor, "relation_child")["parent_id"]
            assert relation[:2] == ("id", "relation_parent")
            if DJANGO_VERSION >= (6, 1):
                assert len(relation) == 3
                assert str(relation[2]) == "DB_CASCADE"
            else:
                assert len(relation) == 2

        output = StringIO()
        call_command("inspectdb", stdout=output, database=wrapper.alias)
        source = output.getvalue()
        assert "parent = models.ForeignKey(" in source
        if DJANGO_VERSION >= (6, 1):
            assert ", models.DB_CASCADE" in source
        else:
            assert "models.DO_NOTHING" in source


@pytest.mark.core
@pytest.mark.parametrize("table_name", ["intro_sizes", "size(table", 'size")table', "size,table"])
def test_declared_character_lengths_reach_introspection_and_inspectdb(
    django_db_blocker: Any, table_name: str
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        table_sql = connection.ops.quote_name(table_name)
        cursor.execute(
            f"CREATE TABLE {table_sql} ("
            "id INTEGER PRIMARY KEY, "
            "value VARCHAR(20), "
            '"varchar(999)" VARCHAR /* char(500) */ (30), '
            "unlimited VARCHAR DEFAULT 'varchar(200)', "
            "checked VARCHAR CHECK(checked <> 'char(400)'), "
            "nested VARCHAR DEFAULT ('char(600)'), "
            "commented VARCHAR /* char(300) ( , ) */, "
            "escaped VARCHAR DEFAULT 'can''t char(700)', "
            "simple CHAR(17), "
            'quoted_type "VARCHAR(18)", '
            "`backtick` CHAR(21), [bracket] CHAR(22), 'single quote' CHAR(23), "
            '"escaped""column" CHAR(24))'
        )
        try:
            sizes = {
                field.name: field.display_size
                for field in connection.introspection.get_table_description(cursor, table_name)
            }
            assert sizes == {
                "id": None,
                "value": 20,
                "varchar(999)": 30,
                "unlimited": None,
                "checked": None,
                "nested": None,
                "commented": None,
                "escaped": None,
                "simple": 17,
                "quoted_type": 18,
                "backtick": 21,
                "bracket": 22,
                "single quote": 23,
                'escaped"column': 24,
            }
            output = StringIO()
            call_command("inspectdb", table_name, stdout=output)
            model_source = output.getvalue()
            assert "value = models.CharField(max_length=20," in model_source
            assert "db_column='varchar(999)', max_length=30," in model_source
            assert "simple = models.CharField(max_length=17," in model_source
            for name in ("unlimited", "checked", "nested", "commented", "escaped"):
                field_line = next(
                    line for line in model_source.splitlines() if line.startswith(f"    {name} = ")
                )
                assert "max_length=" not in field_line
        finally:
            cursor.execute(f"DROP TABLE {table_sql}")


@pytest.mark.core
@pytest.mark.parametrize(
    "options",
    [{"journal_mode": "WAL"}, {"journal_mode": "MVCC", "transaction_mode": "CONCURRENT"}],
    ids=["wal", "mvcc"],
)
def test_table_constraint_names_cannot_set_column_lengths(
    django_db_blocker: Any, tmp_path: Path, options: dict[str, str]
) -> None:
    with django_db_blocker.unblock(), isolate_apps(), registered_wrapper(
        NAME=tmp_path / "constraint_sizes.db", OPTIONS=options
    ) as wrapper:
        class ConstraintSizes(models.Model):
            value = models.CharField(max_length=20, db_column="CONSTRAINT")
            checked = models.CharField(max_length=21, db_column="CHECK")
            unique_value = models.CharField(max_length=22, db_column="UNIQUE")
            primary_value = models.CharField(max_length=23, db_column="PRIMARY KEY")
            foreign_value = models.CharField(max_length=24, db_column="FOREIGN KEY")

            class Meta:
                app_label = "intro_constraint_sizes"
                db_table = "intro_constraint_sizes"
                constraints = [
                    models.UniqueConstraint(fields=["value"], name="VARCHAR(999)"),
                    models.CheckConstraint(condition=models.Q(value__gte=""), name="CHAR(888)"),
                ]

        with wrapper.schema_editor() as editor:
            editor.create_model(ConstraintSizes)
        with wrapper.cursor() as cursor:
            sizes = {
                field.name: field.display_size
                for field in wrapper.introspection.get_table_description(
                    cursor, "intro_constraint_sizes"
                )
            }
            assert sizes == {
                "id": None,
                "CONSTRAINT": 20,
                "CHECK": 21,
                "UNIQUE": 22,
                "PRIMARY KEY": 23,
                "FOREIGN KEY": 24,
            }
            constraints = wrapper.introspection.get_constraints(cursor, "intro_constraint_sizes")
            assert constraints["VARCHAR(999)"]["unique"]
            assert constraints["CHAR(888)"]["check"]

        output = StringIO()
        call_command("inspectdb", "intro_constraint_sizes", stdout=output, database=wrapper.alias)
        source = output.getvalue()
        assert "db_column='CONSTRAINT', unique=True, max_length=20" in source
        assert "max_length=999" not in source
        assert "max_length=888" not in source


@pytest.mark.core
@pytest.mark.parametrize(
    ("column_sql", "column_name", "collation_sql"),
    [
        ('"a""b"', 'a"b', '"NOCASE"'),
        ("`a``b`", "a`b", "`NOCASE`"),
        ("[quoted column]", "quoted column", "[NOCASE]"),
        ("'quoted column'", "quoted column", "'NOCASE'"),
        ("plain", "plain", "NOCASE"),
    ],
)
def test_only_column_collations_reach_introspection_and_inspectdb(
    django_db_blocker: Any, column_sql: str, column_name: str, collation_sql: str
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE intro_column_collations ("
            "id INTEGER PRIMARY KEY, "
            "literal TEXT DEFAULT 'COLLATE NOCASE', "
            "escaped TEXT DEFAULT 'can''t COLLATE RTRIM', "
            "commented TEXT /* COLLATE RTRIM ( , ) */, "
            "simple_comment TEXT /* COLLATE RTRIM */, "
            "line_comment TEXT -- COLLATE RTRIM\n, "
            "checked TEXT CHECK(checked COLLATE NOCASE <> ''), "
            "nested_default TEXT DEFAULT ('COLLATE RTRIM' COLLATE RTRIM), "
            f"{column_sql} TEXT DEFAULT 'COLLATE RTRIM' COLLATE /* actual */ {collation_sql}, "
            "after_check TEXT CHECK(after_check COLLATE RTRIM <> '') COLLATE NOCASE)"
        )
        try:
            collations = {
                field.name: field.collation
                for field in connection.introspection.get_table_description(
                    cursor, "intro_column_collations"
                )
            }
            assert collations == {
                "id": None,
                "literal": None,
                "escaped": None,
                "commented": None,
                "simple_comment": None,
                "line_comment": None,
                "checked": None,
                "nested_default": None,
                column_name: "NOCASE",
                "after_check": "NOCASE",
            }
            output = StringIO()
            call_command("inspectdb", "intro_column_collations", stdout=output)
            assert output.getvalue().count("db_collation='NOCASE'") == 2
            assert output.getvalue().count("db_collation=") == 2
        finally:
            cursor.execute("DROP TABLE intro_column_collations")


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
            assert {
                name: relation[:2]
                for name, relation in connection.introspection.get_relations(
                    cursor, "intro_child"
                ).items()
            } == {
                "part_a": ("part_a", "intro_target"),
                "part_b": ("part_b", "intro_target"),
            }
            assert {
                name: relation[:2]
                for name, relation in connection.introspection.get_relations(
                    cursor, "intro_implicit_child"
                ).items()
            } == {
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


@pytest.mark.core
@pytest.mark.parametrize("constraint_prefix", ["", "CONSTRAINT pair_unique "])
def test_table_unique_constraints_preserve_columns_and_inspectdb_output(
    django_db_blocker: Any,
    constraint_prefix: str,
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE intro_table_unique ("
            "id INTEGER PRIMARY KEY, a INTEGER, b TEXT, code TEXT UNIQUE, "
            f"{constraint_prefix}UNIQUE (a, b))"
        )
        try:
            constraints = connection.introspection.get_constraints(cursor, "intro_table_unique")
            unique_columns = [
                constraint["columns"]
                for constraint in constraints.values()
                if constraint["unique"]
            ]
            assert unique_columns == [["code"], ["a", "b"]]
            output = StringIO()
            call_command("inspectdb", "intro_table_unique", stdout=output)
            generated_model = output.getvalue()
            assert "unique_together = (('a', 'b'),)" in generated_model
            assert "code = models.TextField(unique=True" in generated_model
        finally:
            cursor.execute("DROP TABLE intro_table_unique")


@pytest.mark.core
@pytest.mark.parametrize(
    ("column_sql", "column_name", "constraint_sql", "constraint_name"),
    [
        ('"a""b"', 'a"b', '"ck""quoted"', 'ck"quoted'),
        ("`a``b`", "a`b", "`ck``quoted`", "ck`quoted"),
        ("[quoted column]", "quoted column", "[quoted check]", "quoted check"),
    ],
)
def test_quoted_constraints_preserve_identifiers_and_inspectdb_uniqueness(
    django_db_blocker: Any,
    column_sql: str,
    column_name: str,
    constraint_sql: str,
    constraint_name: str,
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE intro_quoted_constraints ("
            f"id INTEGER PRIMARY KEY, {column_sql} TEXT UNIQUE, "
            f"CONSTRAINT {constraint_sql} CHECK ({column_sql} <> ''))"
        )
        try:
            constraints = connection.introspection.get_constraints(
                cursor, "intro_quoted_constraints"
            )
            assert any(
                constraint["unique"] and constraint["columns"] == [column_name]
                for constraint in constraints.values()
            )
            assert constraints[constraint_name]["check"]
            assert constraints[constraint_name]["columns"] == [column_name]
            output = StringIO()
            call_command("inspectdb", "intro_quoted_constraints", stdout=output)
            assert "unique=True" in output.getvalue()
        finally:
            cursor.execute("DROP TABLE intro_quoted_constraints")


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [('"a""b"', 'a"b'), ("`a``b`", "a`b"), ("[quoted column]", "quoted column")],
)
def test_quoted_table_unique_constraints_preserve_column_order(
    identifier: str, expected: str
) -> None:
    constraints = DatabaseIntrospection._parse_table_constraints(
        f"CREATE TABLE sample ({identifier} TEXT, other TEXT, UNIQUE ({identifier}, other))",
        {expected, "other"},
    )
    assert next(iter(constraints.values()))["columns"] == [expected, "other"]


@pytest.mark.core
def test_constraint_references_use_declared_column_names(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            'CREATE TABLE intro_constraint_case (id INTEGER PRIMARY KEY, "Value" TEXT, '
            "other TEXT, CONSTRAINT case_check CHECK(vAlUe <> ''), "
            "CONSTRAINT case_unique UNIQUE(value, OTHER))"
        )
        try:
            constraints = connection.introspection.get_constraints(cursor, "intro_constraint_case")
            assert constraints["case_check"]["columns"] == ["Value"]
            assert constraints["case_unique"]["columns"] == ["Value", "other"]
            output = StringIO()
            call_command("inspectdb", "intro_constraint_case", stdout=output)
            assert "unique_together = (('value', 'other'),)" in output.getvalue()
        finally:
            cursor.execute("DROP TABLE intro_constraint_case")


@pytest.mark.core
@pytest.mark.parametrize("columns", [("Straße", "STRASSE"), ("é", "É"), ("Ω", "ω")])
@pytest.mark.parametrize("json_index", [0, 1])
def test_json_introspection_keeps_distinct_unicode_identifiers(
    django_db_blocker: Any, columns: tuple[str, str], json_index: int
) -> None:
    quoted = [connection.ops.quote_name(column) for column in columns]
    definitions = [
        f"{column} TEXT CHECK(JSON_VALID({column}))" if index == json_index else f"{column} TEXT"
        for index, column in enumerate(quoted)
    ]
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE intro_json_case ({', '.join(definitions)})")
        try:
            description = connection.introspection.get_table_description(cursor, "intro_json_case")
            assert {
                field.name: connection.introspection.get_field_type(field.type_code, field)
                for field in description
            } == {
                column: "JSONField" if index == json_index else "TextField"
                for index, column in enumerate(columns)
            }
        finally:
            cursor.execute("DROP TABLE intro_json_case")


@pytest.mark.core
def test_unique_constraint_modifiers_do_not_become_columns(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE intro_collated_unique (id INTEGER PRIMARY KEY, value TEXT, "
            'other TEXT, "NOCASE" TEXT, CONSTRAINT collated_pair '
            "UNIQUE(value COLLATE NOCASE DESC, other ASC))"
        )
        try:
            constraints = connection.introspection.get_constraints(cursor, "intro_collated_unique")
            assert constraints["collated_pair"]["columns"] == ["value", "other"]
            output = StringIO()
            call_command("inspectdb", "intro_collated_unique", stdout=output)
            assert "unique_together = (('value', 'other'),)" in output.getvalue()
        finally:
            cursor.execute("DROP TABLE intro_collated_unique")


@pytest.mark.core
def test_schema_lookup_uses_native_table_name_case(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            'CREATE TABLE intro_lookup_case (id INTEGER PRIMARY KEY, "Value" VARCHAR(31) '
            'COLLATE NOCASE UNIQUE CHECK(JSON_VALID("Value")))'
        )
        try:
            assert connection.introspection.get_table_description(
                cursor, "INTRO_LOOKUP_CASE"
            ) == connection.introspection.get_table_description(cursor, "intro_lookup_case")
            assert connection.introspection.get_constraints(
                cursor, "INTRO_LOOKUP_CASE"
            ) == connection.introspection.get_constraints(cursor, "intro_lookup_case")
            output = StringIO()
            call_command("inspectdb", "INTRO_LOOKUP_CASE", stdout=output)
            assert "models.JSONField(" in output.getvalue()
            assert "unique=True" in output.getvalue()
        finally:
            cursor.execute("DROP TABLE intro_lookup_case")


@pytest.mark.core
def test_single_quoted_identifiers_preserve_unique_constraints(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE intro_single_quotes (id INTEGER PRIMARY KEY, 'value' TEXT UNIQUE, "
            "'other' TEXT, CONSTRAINT 'uq''pair' UNIQUE('value', 'other'), "
            "CONSTRAINT 'quoted_check' CHECK(\"value\" <> 'other'))"
        )
        try:
            constraints = connection.introspection.get_constraints(cursor, "intro_single_quotes")
            assert any(
                details["unique"] and details["columns"] == ["value"]
                for details in constraints.values()
            )
            assert constraints["uq'pair"]["columns"] == ["value", "other"]
            assert constraints["quoted_check"]["columns"] == ["value"]
            output = StringIO()
            call_command("inspectdb", "intro_single_quotes", stdout=output)
            assert "unique=True" in output.getvalue()
            assert "unique_together = (('value', 'other'),)" in output.getvalue()
        finally:
            cursor.execute("DROP TABLE intro_single_quotes")


@pytest.mark.core
@pytest.mark.parametrize(
    ("expression", "expected_columns"),
    [
        ("length(value) > 0", ["value"]),
        ("length(length) > 0", ["length"]),
        ("value COLLATE NOCASE <> ''", ["value"]),
        ('value COLLATE NOCASE <> "NOCASE"', ["value", "NOCASE"]),
    ],
)
def test_check_expression_labels_do_not_become_columns(
    django_db_blocker: Any, expression: str, expected_columns: list[str]
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            'CREATE TABLE intro_check_labels (id INTEGER PRIMARY KEY, value TEXT, '
            '"length" TEXT, "NOCASE" TEXT, CONSTRAINT value_check '
            f"CHECK({expression}))"
        )
        try:
            constraints = connection.introspection.get_constraints(cursor, "intro_check_labels")
            assert constraints["value_check"]["columns"] == expected_columns
        finally:
            cursor.execute("DROP TABLE intro_check_labels")


@pytest.mark.core
@pytest.mark.parametrize(
    "literal", ["NULL", "TRUE", "FALSE", "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP"]
)
@pytest.mark.parametrize("quoted", [False, True])
def test_check_literals_are_distinct_from_quoted_column_names(
    django_db_blocker: Any, literal: str, quoted: bool
) -> None:
    operand = connection.ops.quote_name(literal) if quoted else literal
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            'CREATE TABLE intro_check_literals (value TEXT, '
            f'{connection.ops.quote_name(literal)} TEXT, CONSTRAINT literal_check '
            f"CHECK(value <> {operand}))"
        )
        try:
            constraints = connection.introspection.get_constraints(cursor, "intro_check_literals")
            assert constraints["literal_check"]["columns"] == (
                ["value", literal] if quoted else ["value"]
            )
        finally:
            cursor.execute("DROP TABLE intro_check_literals")


@pytest.mark.core
@pytest.mark.parametrize(
    ("expression", "expected_columns"),
    [
        (
            "CASE WHEN value IS NULL OR value = '' THEN 0 ELSE CAST(value AS INTEGER) END "
            "BETWEEN 0 AND 100",
            ["value"],
        ),
        ("value GLOB '*'", ["value"]),
        ("value LIKE '%' ESCAPE '!'", ["value"]),
        ("NOT (value IN (1, 2))", ["value"]),
        ("END > 0", ["END"]),
        ("LIKE > 0", ["LIKE"]),
        ("GLOB > 0", ["GLOB"]),
        ("CASE WHEN value > 0 THEN END ELSE 0 END > 0", ["value", "END"]),
        ("length(END) > 0", ["END"]),
        ("(value > 0 AND GLOB > 0) OR LIKE > 0", ["value", "GLOB", "LIKE"]),
        ("value <> 'END'", ["value"]),
        ("value <> 'LIKE'", ["value"]),
        ("value <> 'GLOB'", ["value"]),
        ("value NOT GLOB '*'", ["value"]),
        ("value NOT LIKE '%'", ["value"]),
        ("value > 0 AND NOT GLOB", ["value", "GLOB"]),
    ],
)
def test_check_syntax_is_distinct_from_column_references(
    django_db_blocker: Any, expression: str, expected_columns: list[str]
) -> None:
    names = (
        "AND", "OR", "IS", "NOT", "CASE", "WHEN", "THEN", "ELSE", "END", "AS", "IN",
        "BETWEEN", "LIKE", "GLOB", "ESCAPE",
    )
    definitions = ", ".join(f"{connection.ops.quote_name(name)} TEXT" for name in names)
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            f"CREATE TABLE intro_check_syntax (value TEXT, {definitions}, "
            f"CONSTRAINT syntax_check CHECK({expression}))"
        )
        try:
            constraints = connection.introspection.get_constraints(cursor, "intro_check_syntax")
            assert constraints["syntax_check"]["columns"] == expected_columns
        finally:
            cursor.execute("DROP TABLE intro_check_syntax")


@pytest.mark.parametrize(
    ("definition", "expected_columns"),
    [
        ("UNIQUE (a, b)", ["a", "b"]),
        ("UNIQUE (b, a)", ["b", "a"]),
        ("UNIQUE (a)", ["a"]),
        ('UNIQUE ("a", "quoted field")', ["a", "quoted field"]),
    ],
)
def test_unnamed_table_unique_parser_preserves_column_order(
    definition: str,
    expected_columns: list[str],
) -> None:
    constraints = DatabaseIntrospection._parse_table_constraints(
        f'CREATE TABLE sample (a INTEGER, b TEXT, "quoted field" TEXT, {definition})',
        {"a", "b", "quoted field"},
    )
    assert len(constraints) == 1
    constraint = next(iter(constraints.values()))
    assert constraint == {
        "columns": expected_columns,
        "unique": True,
        "primary_key": False,
        "foreign_key": None,
        "check": False,
        "index": False,
    }
