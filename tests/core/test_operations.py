"""Focused behavioral contracts for Turso database operations."""

from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Any, cast

import pytest
from django.core.management.color import no_style
from django.db import DatabaseError, NotSupportedError, connection, models
from django.db.models import Value
from django.db.models.aggregates import AnyValue, StdDev, Variance
from django.db.models.constants import OnConflict
from django.db.models.expressions import Col, Window
from django.db.models.functions import (
    MD5,
    SHA1,
    SHA224,
    SHA256,
    SHA384,
    SHA512,
    Cot,
    LPad,
    Random,
    Repeat,
    Reverse,
    RPad,
)
from django.test import override_settings
from django.test.utils import isolate_apps
from django.utils.dateparse import parse_time

from django_pyturso.operations import DatabaseOperations

pytestmark = [pytest.mark.core, pytest.mark.django_db]
OPS = cast(DatabaseOperations, connection.ops)


def _raw_scalar(sql: str, params: tuple[Any, ...] = ()) -> Any:
    connection.ensure_connection()
    raw_connection = connection.connection
    assert raw_connection is not None
    cursor = raw_connection.cursor()
    try:
        cursor.execute("SELECT " + sql.replace("%%", "%").replace("%s", "?"), params)
        row = cursor.fetchone()
    finally:
        cursor.close()
    assert row is not None
    return row[0]


@isolate_apps()
def test_bulk_batch_size_flattens_composite_keys_and_handles_empty_fields() -> None:
    class CompositeModel(models.Model):
        part_a = models.IntegerField()
        part_b = models.IntegerField()
        pk = models.CompositePrimaryKey("part_a", "part_b")

        class Meta:
            app_label = "operations_tests"

    ops = OPS
    assert ops.bulk_batch_size([], [1, 2, 3]) == 3
    assert ops.bulk_batch_size([models.IntegerField()], [object()]) == 999
    assert ops.bulk_batch_size([CompositeModel._meta.pk], [object()]) == 499


@pytest.mark.parametrize(
    "expression",
    [
        AnyValue("value"),
        Cot("value"),
        LPad("value", 4),
        MD5("value"),
        RPad("value", 4),
        Random(),
        Repeat("value", 2),
        Reverse("value"),
        SHA1("value"),
        SHA224("value"),
        SHA256("value"),
        SHA384("value"),
        SHA512("value"),
        StdDev("value"),
        Variance("value"),
        Window(expression=models.Sum("value")),
    ],
    ids=lambda expression: expression.__class__.__name__,
)
def test_unsupported_expression_matrix_is_rejected(expression: models.Expression) -> None:
    with pytest.raises(NotSupportedError, match=expression.__class__.__name__):
        OPS.check_expression_support(expression)


def test_allowed_and_multi_argument_distinct_aggregate_paths() -> None:
    class Random:
        pass

    class MultiArgumentAggregate(models.Aggregate):
        function = "TEST_AGG"
        allow_distinct = True

    OPS.check_expression_support(Value(1))
    OPS.check_expression_support(Random())
    aggregate = MultiArgumentAggregate(Value(1), Value(2), distinct=True)
    with pytest.raises(NotSupportedError, match="DISTINCT"):
        OPS.check_expression_support(aggregate)


@pytest.mark.parametrize(
    ("lookup", "expected"),
    [
        ("year", 2026),
        ("iso_year", 2026),
        ("quarter", 3),
        ("month", 7),
        ("day", 13),
        ("week", 29),
        ("week_day", 2),
        ("iso_week_day", 1),
        ("hour", 18),
        ("minute", 42),
        ("second", 31),
    ],
)
def test_every_datetime_extract_path_executes(lookup: str, expected: int) -> None:
    sample = "2026-07-13 18:42:31.123456"
    sql, params = OPS.datetime_extract_sql(lookup.upper(), "%s", (sample,), "UTC")
    assert params == (sample,)
    assert _raw_scalar(sql, params) == expected


def test_date_and_time_extract_wrappers_preserve_tuple_params() -> None:
    date_sql, date_params = OPS.date_extract_sql("month", "%s", ["2026-07-13"])
    time_sql, time_params = OPS.time_extract_sql("hour", "%s", ["18:42:31"])
    assert _raw_scalar(date_sql, date_params) == 7
    assert _raw_scalar(time_sql, time_params) == 18
    assert isinstance(date_params, tuple)
    assert isinstance(time_params, tuple)


def test_unknown_extract_and_named_timezone_are_rejected() -> None:
    with pytest.raises(NotSupportedError, match="Unsupported temporal extraction"):
        OPS.date_extract_sql("century", "field", ())
    with pytest.raises(NotSupportedError, match="without timezone conversion"):
        OPS.datetime_extract_sql("year", "field", (), "America/Phoenix")


@pytest.mark.parametrize(
    ("lookup", "expected"),
    [
        ("year", "2026-01-01"),
        ("quarter", "2026-07-01"),
        ("month", "2026-07-01"),
        ("week", "2026-07-13"),
        ("day", "2026-07-13"),
    ],
)
def test_every_date_truncation_path_executes(lookup: str, expected: str) -> None:
    sample = "2026-07-13"
    sql, params = OPS.date_trunc_sql(lookup.upper(), "%s", (sample,), None)
    expected_params = (sample, sample) if lookup in {"quarter", "week"} else (sample,)
    assert params == expected_params
    assert _raw_scalar(sql, params) == expected


@pytest.mark.parametrize(
    ("lookup", "expected"),
    [
        ("year", "2026-01-01 00:00:00"),
        ("quarter", "2026-07-01 00:00:00"),
        ("month", "2026-07-01 00:00:00"),
        ("week", "2026-07-13 00:00:00"),
        ("day", "2026-07-13 00:00:00"),
        ("hour", "2026-07-13 18:00:00"),
        ("minute", "2026-07-13 18:42:00"),
        ("second", "2026-07-13 18:42:31"),
    ],
)
def test_every_datetime_truncation_path_executes(lookup: str, expected: str) -> None:
    sample = "2026-07-13 18:42:31.123456"
    sql, params = OPS.datetime_trunc_sql(lookup, "%s", (sample,), "UTC")
    expected_params = (sample, sample) if lookup == "week" else (sample,)
    assert params == expected_params
    assert _raw_scalar(sql, params) == expected


@pytest.mark.parametrize(
    ("lookup", "expected"),
    [("hour", "18:00:00"), ("minute", "18:42:00"), ("second", "18:42:31")],
)
def test_every_time_truncation_path_executes(lookup: str, expected: str) -> None:
    sample = "18:42:31.123456"
    sql, params = OPS.time_trunc_sql(lookup, "%s", (sample,), None)
    assert params == (sample,)
    assert _raw_scalar(sql, params) == expected


def test_temporal_truncation_rejections_and_casts() -> None:
    ops = OPS
    with pytest.raises(NotSupportedError, match="Unsupported date truncation"):
        ops.date_trunc_sql("hour", "field", ())
    with pytest.raises(NotSupportedError, match="Unsupported datetime truncation"):
        ops.datetime_trunc_sql("millisecond", "field", (), None)
    with pytest.raises(NotSupportedError, match="Unsupported time truncation"):
        ops.time_trunc_sql("day", "field", ())
    for method, args in (
        (ops.date_trunc_sql, ("day", "field", (), "Europe/London")),
        (ops.datetime_trunc_sql, ("day", "field", (), "Europe/London")),
        (ops.time_trunc_sql, ("hour", "field", (), "Europe/London")),
    ):
        with pytest.raises(NotSupportedError, match="without timezone conversion"):
            method(*args)

    sample = "2026-07-13 18:42:31.123456"
    date_sql, date_params = ops.datetime_cast_date_sql("%s", (sample,), "UTC")
    time_sql, time_params = ops.datetime_cast_time_sql("%s", (sample,), None)
    assert _raw_scalar(date_sql, date_params) == "2026-07-13"
    raw_time = _raw_scalar(time_sql, time_params)
    assert raw_time == "18:42:31.123456000"
    assert parse_time(raw_time) == datetime.time(18, 42, 31, 123456)
    with pytest.raises(NotSupportedError, match="without timezone conversion"):
        ops.datetime_cast_date_sql("field", (), "Asia/Tokyo")
    with pytest.raises(NotSupportedError, match="without timezone conversion"):
        ops.datetime_cast_time_sql("field", (), "Asia/Tokyo")


def test_time_extension_helpers_and_basic_sql_constants() -> None:
    ops = OPS
    assert ops._time_extension_input("field") == "time_parse(REPLACE(field, ' ', 'T') || 'Z')"
    assert ops._time_extension_input("field", time_only=True) == (
        "time_parse('1970-01-01T' || field || 'Z')"
    )
    assert ops._format_time_extension("parsed") == (
        "RTRIM(REPLACE(time_fmt_iso(parsed), 'T', ' '), 'Z')"
    )
    assert ops._format_time_extension("parsed", time_only=True).startswith("SUBSTR(")
    assert ops.format_for_duration_arithmetic("field") == "field"
    assert ops.quote_name("already") == '"already"'
    assert ops.quote_name('a"b') == '"a""b"'
    assert ops.quote_name('"already"') == '"already"'
    assert ops.no_limit_value() == "-1"
    assert ops.pk_default_value() == "NULL"


def test_debug_query_quoting_supports_empty_positional_mapping_and_batches() -> None:
    ops = OPS
    connection.ensure_connection()
    assert ops._quote_params_for_last_executed_query(()) == ()
    quoted = ops._quote_params_for_last_executed_query(("O'Reilly", None, 3))
    assert quoted == ("'O''Reilly'", "NULL", "3")
    batched = ops._quote_params_for_last_executed_query(tuple(range(1001)))
    assert len(batched) == 1001
    assert batched[:2] == ("0", "1")
    assert batched[-1] == "1000"
    assert ops.last_executed_query(None, "SELECT 1", None) == "SELECT 1"
    assert ops.last_executed_query(None, "SELECT %s, %s", ("x", 2)) == "SELECT 'x', 2"
    assert ops.last_executed_query(None, "SELECT %(value)s", {"value": "x"}) == "SELECT 'x'"


def test_reference_graph_flush_cascade_and_sequence_reset_sql() -> None:
    ops = OPS
    style = no_style()
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE operations_parent (id integer primary key)")
        cursor.execute(
            "CREATE TABLE operations_child (id integer primary key, parent_id integer "
            "REFERENCES operations_parent(id))"
        )
        cursor.execute(
            "CREATE TABLE operations_grandchild (id integer primary key, child_id integer "
            "REFERENCES operations_child(id))"
        )
        cursor.execute(
            "CREATE TABLE operations_self (id integer primary key, parent_id integer "
            "REFERENCES operations_self(id))"
        )
    try:
        assert ops._references_graph_for_table("operations_parent") == [
            "operations_parent",
            "operations_child",
            "operations_grandchild",
        ]
        assert ops._references_graph_for_table("operations_self") == ["operations_self"]
        plain = ops.sql_flush(style, ["operations_parent"])
        assert plain == ['DELETE FROM "operations_parent";']
        cascade = ops.sql_flush(
            style, ["operations_parent"], reset_sequences=True, allow_cascade=True
        )
        assert set(cascade[:-1]) == {
            'DELETE FROM "operations_parent";',
            'DELETE FROM "operations_child";',
            'DELETE FROM "operations_grandchild";',
        }
        assert '"sqlite_sequence"' in cascade[-1]
        assert ops.sequence_reset_by_name_sql(style, []) == []
        escaped = ops.sequence_reset_by_name_sql(style, [{"table": "quote'table"}])
        assert "quote''table" in escaped[0]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE operations_self")
            cursor.execute("DROP TABLE operations_grandchild")
            cursor.execute("DROP TABLE operations_child")
            cursor.execute("DROP TABLE operations_parent")


def test_value_adaptation_nulls_timezone_and_errors() -> None:
    ops = OPS
    date_value = datetime.date(2026, 7, 13)
    time_value = datetime.time(18, 42, 31, 123456)
    aware = datetime.datetime(2026, 7, 13, 18, 42, tzinfo=datetime.UTC)
    assert ops.adapt_datefield_value(None) is None
    assert ops.adapt_datefield_value(date_value) == "2026-07-13"
    assert ops.adapt_datetimefield_value(None) is None
    assert ops.adapt_datetimefield_value(aware) == "2026-07-13 18:42:00"
    assert ops.adapt_datetimefield_value(aware.replace(tzinfo=None)) == "2026-07-13 18:42:00"
    assert ops.adapt_timefield_value(None) is None
    assert ops.adapt_timefield_value(time_value) == "18:42:31.123456"
    assert ops.adapt_decimalfield_value(None) is None
    assert ops.adapt_decimalfield_value(decimal.Decimal("12.50")) == "12.50"
    with pytest.raises(ValueError, match="timezone-aware times"):
        ops.adapt_timefield_value(time_value.replace(tzinfo=datetime.UTC))
    with override_settings(USE_TZ=False):
        with pytest.raises(ValueError, match="USE_TZ is False"):
            ops.adapt_datetimefield_value(aware)


@pytest.mark.parametrize(
    ("field", "converter_name"),
    [
        (models.DateTimeField(), "convert_datetimefield_value"),
        (models.DateField(), "convert_datefield_value"),
        (models.TimeField(), "convert_timefield_value"),
        (models.DecimalField(max_digits=8, decimal_places=2), "converter"),
        (models.UUIDField(), "convert_uuidfield_value"),
        (models.BooleanField(), "convert_booleanfield_value"),
        (models.CharField(max_length=10), None),
    ],
)
def test_converter_registration(field: models.Field[Any, Any], converter_name: str | None) -> None:
    converters = OPS.get_db_converters(Value(None, output_field=field))
    names = [converter.__name__ for converter in converters]
    if converter_name is None:
        assert names == []
    else:
        assert converter_name in names


def test_value_converters_cover_existing_values_strings_and_nulls() -> None:
    ops = OPS
    expression = Value(None)
    moment = datetime.datetime(2026, 7, 13, 18, 42, 31)
    date_value = moment.date()
    time_value = moment.time()
    identifier = uuid.UUID("018f1c7d-2a9b-7d64-bf10-123456789abc")
    assert ops.convert_datetimefield_value(None, expression, connection) is None
    assert ops.convert_datetimefield_value(moment, expression, connection).tzinfo is not None
    assert ops.convert_datetimefield_value("2026-07-13 18:42:31", expression, connection).tzinfo
    assert ops.convert_datefield_value("2026-07-13", expression, connection) == date_value
    assert ops.convert_datefield_value(date_value, expression, connection) is date_value
    assert ops.convert_datefield_value(None, expression, connection) is None
    assert ops.convert_timefield_value("18:42:31", expression, connection) == time_value
    assert ops.convert_timefield_value(time_value, expression, connection) is time_value
    assert ops.convert_timefield_value(None, expression, connection) is None
    assert ops.convert_uuidfield_value(identifier.hex, expression, connection) == identifier
    assert ops.convert_uuidfield_value(identifier, expression, connection) is identifier
    assert ops.convert_uuidfield_value(None, expression, connection) is None
    assert ops.convert_booleanfield_value(1, expression, connection) is True
    assert ops.convert_booleanfield_value(0, expression, connection) is False
    assert ops.convert_booleanfield_value(2, expression, connection) == 2
    assert ops.convert_booleanfield_value(None, expression, connection) is None


def test_decimal_converters_cover_col_and_non_col_paths() -> None:
    ops = OPS
    field = models.DecimalField(max_digits=8, decimal_places=2)
    col_converter = ops.get_decimalfield_converter(Col("table", field))
    assert col_converter(None, None, connection) is None
    assert col_converter(1.235, None, connection) == decimal.Decimal("1.24")
    assert col_converter("1.20", None, connection) == decimal.Decimal("1.20")
    value_converter = ops.get_decimalfield_converter(Value(None, output_field=field))
    assert value_converter(None, None, connection) is None
    assert value_converter("1.20", None, connection) == decimal.Decimal("1.20")
    assert isinstance(value_converter(1.25, None, connection), decimal.Decimal)


def test_expression_combination_duration_rejection_and_integer_ranges() -> None:
    ops = OPS
    assert ops.combine_expression("^", ["a", "b"]) == "POWER(a,b)"
    assert ops.combine_expression("#", ["a", "b"]) == "BITXOR(a,b)"
    assert ops.combine_expression("+", ["a", "b"]) == "a + b"
    for connector in ("+", "-", "*", "/"):
        with pytest.raises(NotSupportedError, match="Duration arithmetic"):
            ops.combine_duration_expression(connector, ["a", "b"])
    with pytest.raises(DatabaseError, match="Invalid connector"):
        ops.combine_duration_expression("%", ["a", "b"])
    assert ops.integer_field_range("PositiveIntegerField") == (0, 9223372036854775807)
    assert ops.integer_field_range("IntegerField") == (
        -9223372036854775808,
        9223372036854775807,
    )
    with pytest.raises(NotSupportedError, match="Temporal subtraction"):
        ops.subtract_temporals("DateTimeField", ("lhs", ()), ("rhs", ()))


def test_conflict_sql_and_json_numeric_indexes() -> None:
    ops = OPS
    assert ops.insert_statement(OnConflict.IGNORE) == "INSERT OR IGNORE INTO"
    assert ops.insert_statement() == "INSERT INTO"
    assert (
        ops.on_conflict_suffix_sql([], OnConflict.UPDATE, ["value"], ["key"])
        == 'ON CONFLICT("key") DO UPDATE SET "value" = EXCLUDED."value"'
    )
    assert ops.on_conflict_suffix_sql([], None, [], []) == ""
    assert ops.format_json_path_numeric_index(0) == "[0]"
    assert ops.format_json_path_numeric_index(7) == "[7]"
    assert ops.format_json_path_numeric_index(-1) == "[#-1]"
