"""Django bulk-write regressions. See docs/testing/django-regressions.md."""

from typing import Any

import pytest
from django.db import IntegrityError
from django.db.models import F, IntegerField, Value
from django.db.models.functions import Coalesce, Lower

from tests.django_regressions.models import NamedRank, Record

pytestmark = pytest.mark.core


def test_bulk_create_mixed_primary_keys() -> None:
    Record.objects.bulk_create(
        [
            Record(id=i if i % 2 == 0 else None, name=f"record-{i}", number=i)
            for i in range(100000, 100020)
        ],
        batch_size=3,
    )
    explicit_ids = range(100000, 100020, 2)
    assert Record.objects.count() == 20
    assert Record.objects.filter(id__in=explicit_ids).count() == 10
    assert Record.objects.exclude(id__in=explicit_ids).count() == 10


def test_bulk_create_sql_expressions() -> None:
    Record.objects.bulk_create(
        [Record(name="Sam's Shake Shack"), Record(name=Lower(Value("Betty's Beetroot Bar")))]
    )
    assert Record.objects.filter(name="betty's beetroot bar").count() == 1


def test_bulk_create_ignore_conflicts() -> None:
    Record.objects.bulk_create([Record(name=str(i)) for i in range(1, 4)])
    conflicts = [Record(name="2"), Record(name="3")]
    new = Record(name="4")
    Record.objects.bulk_create(conflicts + [new], ignore_conflicts=True)
    assert list(Record.objects.order_by("name").values_list("name", flat=True)) == [
        "1",
        "2",
        "3",
        "4",
    ]
    assert all(obj.pk is None for obj in conflicts + [new])
    with pytest.raises(IntegrityError):
        Record.objects.bulk_create(conflicts)
    assert Record.objects.count() == 4


def test_bulk_create_update_conflicts_with_db_columns() -> None:
    NamedRank.objects.bulk_create([NamedRank(rank=1, name="a"), NamedRank(rank=2, name="b")])
    conflicts = [NamedRank(rank=1, name="c"), NamedRank(rank=2, name="d")]
    results = NamedRank.objects.bulk_create(
        conflicts, update_conflicts=True, unique_fields=["rank"], update_fields=["name"]
    )
    assert len(results) == 2
    assert all(obj.pk is not None for obj in results)
    assert list(NamedRank.objects.order_by("rank").values_list("rank", "name")) == [
        (1, "c"),
        (2, "d"),
    ]


def test_bulk_update_field_references() -> None:
    rows = [Record.objects.create(name=str(i), number=0) for i in range(4)]
    for row in rows:
        setattr(row, "number", F("number") + 1)
    assert Record.objects.bulk_update(rows, ["number"], batch_size=2) == 4
    assert Record.objects.filter(number=1).count() == 4


def test_bulk_update_duplicate_row_counts() -> None:
    row = Record.objects.create(name="duplicate")
    assert Record.objects.bulk_update([row, row], ["name"]) == 1
    assert Record.objects.bulk_update([row, row], ["name"], batch_size=1) == 2


def test_bulk_update_batches_are_atomic() -> None:
    first = Record.objects.create(name="Banana")
    second = Record.objects.create(name="Apple")
    first.name = second.name = "Kiwi"
    with pytest.raises(IntegrityError):
        Record.objects.bulk_update([first, second], ["name"], batch_size=1)
    assert not Record.objects.filter(name="Kiwi").exists()
    assert set(Record.objects.values_list("name", flat=True)) == {"Banana", "Apple"}


@pytest.mark.parametrize(
    "value", [None, Value(None), Coalesce(None, None, output_field=IntegerField())]
)
def test_bulk_update_json_sql_null(value: Any) -> None:
    row = Record.objects.create(name="json", payload={})
    row.payload = value
    Record.objects.bulk_update([row], ["payload"])
    row.refresh_from_db()
    assert row.payload is None
    assert list(Record.objects.filter(payload__isnull=True)) == [row]
