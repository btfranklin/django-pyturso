"""Focused contracts for behavior-changing operations mutation survivors."""

from __future__ import annotations

import datetime
import decimal
from typing import Any, Self, cast

import pytest
from django.core.management.color import no_style
from django.db import connection, models
from django.db.models import Func, Sum, Value
from django.db.models.constants import OnConflict
from django.db.models.expressions import Col

from django_pyturso.operations import DatabaseOperations

pytestmark = pytest.mark.core
OPS = cast(DatabaseOperations, connection.ops)


def test_distinct_aggregate_rejection_keeps_allowed_expression_boundaries() -> None:
    ops = OPS

    ordinary_expression = Func(Value(1), Value(2))
    setattr(ordinary_expression, "distinct", True)
    ops.check_expression_support(ordinary_expression)
    ops.check_expression_support(Sum(Value(1)))
    ops.check_expression_support(Sum(Value(1), distinct=True))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ('"leading', '"""leading"'),
        ('trailing"', '"trailing"""'),
    ],
)
def test_quote_name_requires_a_complete_existing_quote_pair(
    name: str, expected: str
) -> None:
    assert OPS.quote_name(name) == expected


class _GraphCursor:
    def __init__(self, foreign_keys: dict[str, tuple[str, ...]]) -> None:
        self.foreign_keys = foreign_keys
        self.rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> _GraphCursor:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def execute(self, sql: str) -> None:
        if "sqlite_master" in sql:
            self.rows = [(table,) for table in self.foreign_keys]
            return
        table = next(
            table for table in self.foreign_keys if f'"{table}"' in sql
        )
        self.rows = [
            (index, index, target, f"source_{index}", f"target_{index}")
            for index, target in enumerate(self.foreign_keys[table])
        ]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class _GraphConnection:
    def __init__(self, foreign_keys: dict[str, tuple[str, ...]]) -> None:
        self.foreign_keys = foreign_keys

    def cursor(self) -> _GraphCursor:
        return _GraphCursor(self.foreign_keys)


@pytest.mark.timeout(2)
def test_reference_graph_terminates_and_visits_each_referencing_table_once() -> None:
    foreign_keys = {
        "parent": (),
        "child_a": ("parent",),
        "child_b": ("parent",),
        "child_c": ("parent",),
        "grandchild": ("child_a", "child_b"),
        "self_loop": ("self_loop",),
    }
    ops = DatabaseOperations(_GraphConnection(foreign_keys))  # type: ignore[arg-type]

    graph = ops._references_graph_for_table("parent")
    assert set(graph) == {"parent", "child_a", "child_b", "child_c", "grandchild"}
    assert len(graph) == 5
    assert ops._references_graph_for_table("self_loop") == ["self_loop"]


def test_sequence_reset_sql_is_complete_for_multiple_escaped_table_names() -> None:
    assert OPS.sequence_reset_by_name_sql(
        no_style(), [{"table": "alpha"}, {"table": "quote'table"}]
    ) == [
        'UPDATE "sqlite_sequence" SET "seq" = 0 '
        'WHERE "name" IN (\'alpha\', \'quote\'\'table\');'
    ]


def test_datetime_adaptation_uses_the_database_timezone() -> None:
    class TrackingDateTime(datetime.datetime):
        observed_timezone: datetime.tzinfo | None = None

        def astimezone(self, tz: datetime.tzinfo | None = None) -> Self:
            type(self).observed_timezone = tz
            return super().astimezone(tz)

    value = TrackingDateTime(2026, 7, 13, 12, tzinfo=datetime.UTC)

    OPS.adapt_datetimefield_value(value)

    assert TrackingDateTime.observed_timezone is connection.timezone


def test_datetime_conversion_uses_the_database_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[datetime.tzinfo | None] = []

    def make_aware(
        value: datetime.datetime, timezone: datetime.tzinfo | None = None
    ) -> datetime.datetime:
        observed.append(timezone)
        return value.replace(tzinfo=timezone)

    monkeypatch.setattr("django_pyturso.operations.timezone.make_aware", make_aware)

    converted = OPS.convert_datetimefield_value(
        datetime.datetime(2026, 7, 13, 12), Value(None), connection
    )

    assert converted.tzinfo is connection.timezone
    assert observed == [connection.timezone]


def test_decimal_converter_registration_preserves_the_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops = OPS
    field = models.DecimalField(max_digits=8, decimal_places=2)
    expression = Value(None, output_field=field)
    observed: list[Any] = []

    def converter_factory(candidate: Any) -> Any:
        observed.append(candidate)
        return lambda value, _expression, _connection: value

    monkeypatch.setattr(ops, "get_decimalfield_converter", converter_factory)

    ops.get_db_converters(expression)

    assert observed == [expression]


def test_decimal_conversion_uses_fixed_precision_and_field_context() -> None:
    ops = OPS
    field = models.DecimalField(max_digits=8, decimal_places=2)
    value_converter = ops.get_decimalfield_converter(Value(None, output_field=field))
    assert value_converter(1.2345678901234567, None, connection) == decimal.Decimal(
        "1.23456789012346"
    )

    field.context.rounding = decimal.ROUND_DOWN
    column_converter = ops.get_decimalfield_converter(Col("sample", field))
    assert column_converter(1.239, None, connection) == decimal.Decimal("1.23")


@pytest.mark.parametrize(
    "internal_type", ["PositiveBigIntegerField", "PositiveSmallIntegerField"]
)
def test_all_positive_integer_ranges_have_a_zero_lower_bound(
    internal_type: str,
) -> None:
    assert OPS.integer_field_range(internal_type) == (
        0,
        9223372036854775807,
    )


def test_update_conflict_sql_joins_every_target_and_assignment() -> None:
    assert OPS.on_conflict_suffix_sql(
        [],
        OnConflict.UPDATE,
        ["first", "second"],
        ["tenant", "key"],
    ) == (
        'ON CONFLICT("tenant", "key") DO UPDATE SET '
        '"first" = EXCLUDED."first", "second" = EXCLUDED."second"'
    )
