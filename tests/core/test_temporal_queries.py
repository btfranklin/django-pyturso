"""Temporal expressions must preserve Django values through real ORM queries."""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.db import NotSupportedError, connection, models
from django.db.models import F, Value
from django.db.models.functions import (
    TruncDay,
    TruncHour,
    TruncMinute,
    TruncMonth,
    TruncQuarter,
    TruncSecond,
    TruncTime,
    TruncWeek,
    TruncYear,
)
from django.test.utils import isolate_apps

pytestmark = pytest.mark.core
MOMENT = datetime.datetime(2026, 7, 13, 18, 42, 31, 123456, tzinfo=datetime.UTC)


@pytest.fixture
def temporal_rows(django_db_blocker: Any) -> Iterator[Any]:
    with django_db_blocker.unblock(), isolate_apps():

        class TemporalRow(models.Model):
            objects: models.Manager[TemporalRow] = models.Manager()
            date_value = models.DateField(null=True)
            datetime_value = models.DateTimeField(null=True)
            time_value = models.TimeField(null=True)

            class Meta:
                app_label = "temporal_queries"

        with connection.schema_editor() as editor:
            editor.create_model(TemporalRow)
        try:
            TemporalRow.objects.create()
            TemporalRow.objects.create(
                date_value=MOMENT.date(), datetime_value=MOMENT, time_value=MOMENT.time()
            )
            yield TemporalRow
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(TemporalRow)


@pytest.mark.parametrize(
    ("field_name", "function", "expected"),
    [
        ("date_value", TruncQuarter, datetime.date(2026, 7, 1)),
        (
            "datetime_value",
            TruncYear,
            MOMENT.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
        ),
        (
            "datetime_value",
            TruncQuarter,
            MOMENT.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        ),
        (
            "datetime_value",
            TruncMonth,
            MOMENT.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        ),
        ("datetime_value", TruncDay, MOMENT.replace(hour=0, minute=0, second=0, microsecond=0)),
        ("datetime_value", TruncWeek, MOMENT.replace(hour=0, minute=0, second=0, microsecond=0)),
        ("datetime_value", TruncHour, MOMENT.replace(minute=0, second=0, microsecond=0)),
        ("datetime_value", TruncMinute, MOMENT.replace(second=0, microsecond=0)),
        ("datetime_value", TruncSecond, MOMENT.replace(microsecond=0)),
        ("datetime_value", TruncTime, MOMENT.time()),
        ("time_value", TruncHour, datetime.time(18)),
        ("time_value", TruncMinute, datetime.time(18, 42)),
        ("time_value", TruncSecond, datetime.time(18, 42, 31)),
    ],
)
def test_nullable_temporal_queries(
    temporal_rows: Any, field_name: str, function: Any, expected: Any
) -> None:
    rows = temporal_rows.objects.order_by("pk")
    assert list(rows.annotate(result=function(field_name)).values_list("result", flat=True)) == [
        None,
        expected,
    ]

    field = temporal_rows._meta.get_field(field_name)
    sample = getattr(rows.last(), field_name)
    for value, result in [(None, None), (sample, expected)]:
        expression = function(Value(value, output_field=field))
        assert rows.annotate(result=expression).values_list("result", flat=True).first() == result


def test_nullable_truncation_still_rejects_named_timezone(temporal_rows: Any) -> None:
    expression = TruncHour("datetime_value", tzinfo=ZoneInfo("America/Phoenix"))
    with pytest.raises(NotSupportedError, match="without timezone conversion"):
        list(temporal_rows.objects.annotate(result=expression).values_list("result", flat=True))


@pytest.mark.parametrize("microsecond", [0, 1, 100000, 123456, 999999])
def test_time_lookup_uses_python_microsecond_precision(
    temporal_rows: Any, microsecond: int
) -> None:
    moment = MOMENT.replace(microsecond=microsecond)
    temporal_rows.objects.filter(datetime_value__isnull=False).update(
        datetime_value=moment, time_value=moment.time()
    )
    for rhs in [moment.time(), F("time_value")]:
        for lookup, expected_count in [("exact", 1), ("gt", 0), ("gte", 1), ("lt", 0), ("lte", 1)]:
            assert temporal_rows.objects.filter(
                **{f"datetime_value__time__{lookup}": rhs}
            ).count() == expected_count
