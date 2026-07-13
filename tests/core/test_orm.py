"""Thin Django ORM vertical-slice tests."""

import datetime
import decimal
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from django.db import connection
from django.db.models.functions import ExtractYear, TruncSecond

from tests.project.models import Entry, ScalarValues


@contextmanager
def model_table(model: Any) -> Iterator[None]:
    created = model._meta.db_table not in connection.introspection.table_names()
    if created:
        with connection.schema_editor() as editor:
            editor.create_model(model)
    try:
        yield
    finally:
        if created:
            with connection.schema_editor() as editor:
                editor.delete_model(model)
        else:
            model.objects.all().delete()


@pytest.mark.core
def test_create_query_update_and_delete(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock():
        with model_table(Entry):
            entry = Entry.objects.create(title="first")
            assert entry.pk is not None
            assert Entry.objects.get(pk=entry.pk).title == "first"

            Entry.objects.filter(pk=entry.pk).update(title="updated")
            assert list(Entry.objects.values_list("title", flat=True)) == ["updated"]

            assert Entry.objects.filter(pk=entry.pk).delete()[0] == 1
            assert not Entry.objects.exists()


@pytest.mark.core
def test_scalar_value_round_trips(django_db_blocker: Any) -> None:
    identifier = uuid.UUID("018f1c7d-2a9b-7d64-bf10-123456789abc")
    expected_datetime = datetime.datetime(2026, 7, 13, 18, 42, 31, 123456, tzinfo=datetime.UTC)
    values = {
        "date_value": datetime.date(2026, 7, 13),
        "datetime_value": expected_datetime,
        "time_value": datetime.time(18, 42, 31, 123456),
        "decimal_value": decimal.Decimal("123456.7890"),
        "duration_value": datetime.timedelta(days=-2, microseconds=123456),
        "boolean_value": True,
        "uuid_value": identifier,
        "json_value": {"nested": [True, None, 3]},
        "binary_value": None,
    }
    with django_db_blocker.unblock():
        with model_table(ScalarValues):
            ScalarValues.objects.create(**values)
            fetched = ScalarValues.objects.get()
            for field, expected in values.items():
                assert getattr(fetched, field) == expected


@pytest.mark.core
def test_native_temporal_and_json_expressions(django_db_blocker: Any) -> None:
    moment = datetime.datetime(2026, 7, 13, 18, 42, 31, 123456, tzinfo=datetime.UTC)
    with django_db_blocker.unblock():
        with model_table(ScalarValues):
            row = ScalarValues.objects.create(
                date_value=moment.date(),
                datetime_value=moment,
                time_value=moment.time().replace(tzinfo=None),
                decimal_value=decimal.Decimal("1.0000"),
                duration_value=datetime.timedelta(),
                boolean_value=True,
                json_value={"values": ["first", "last"]},
            )
            annotated = ScalarValues.objects.annotate(
                extracted_year=ExtractYear("datetime_value"),
                truncated_second=TruncSecond("datetime_value"),
            ).get(pk=row.pk)
            assert annotated.extracted_year == 2026
            assert annotated.truncated_second == moment.replace(microsecond=0)
            assert ScalarValues.objects.filter(json_value__values__0="first").exists()
            assert ScalarValues.objects.filter(**{"json_value__values__-1": "last"}).exists()
