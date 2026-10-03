"""Django JSON-query regressions. See docs/testing/django-regressions.md."""

from typing import Any

import pytest
from django.db.models import Count, F, JSONField, OuterRef, Subquery, Value
from django.db.models.fields.json import KT, KeyTransform

from tests.django_regressions.models import Record

pytestmark = pytest.mark.core


def test_json_null_differs_from_sql_null() -> None:
    json_null = Record.objects.create(name="json", payload=Value(None, JSONField()))
    Record.objects.update(payload=Value(None, JSONField()))
    json_null.refresh_from_db()
    sql_null = Record.objects.create(name="sql", payload=None)
    sql_null.refresh_from_db()
    assert list(Record.objects.filter(payload=Value(None, JSONField()))) == [json_null]
    assert list(Record.objects.filter(payload=None)) == [json_null]
    assert list(Record.objects.filter(payload__isnull=True)) == [sql_null]
    assert json_null.payload == sql_null.payload


def test_has_key_matches_json_null() -> None:
    row = Record.objects.create(name="present", payload={"j": None})
    Record.objects.create(name="missing", payload={})
    Record.objects.create(name="sql", payload=None)
    assert list(Record.objects.filter(payload__has_key="j")) == [row]


@pytest.mark.parametrize(
    "lookup,values",
    [
        ("payload__c__in", [14, 15]),
        ("payload__foo__in", ["bar", "baz"]),
        ("payload__foo__in", [F("payload__bax__foo"), "baz"]),
        ("payload__h__in", [True, "foo"]),
        ("payload__i__in", [False, "foo"]),
    ],
)
def test_json_key_in(lookup: str, values: list[Any]) -> None:
    row = Record.objects.create(
        name="match", payload={"c": 14, "foo": "bar", "bax": {"foo": "bar"}, "h": True, "i": False}
    )
    Record.objects.create(name="missing", payload={})
    assert list(Record.objects.filter(**{lookup: values})) == [row]


def test_group_by_nested_json_key() -> None:
    Record.objects.create(name="missing", payload={})
    Record.objects.create(name="nested", payload={"d": ["e", {"f": "g"}]})
    Record.objects.create(name="sql", payload=None)
    grouped = (
        Record.objects.filter(payload__isnull=False)
        .annotate(key=KT("payload__d__1__f"))
        .values("key")
        .annotate(count=Count("key"))
        .order_by("count")
    )
    assert list(grouped.values_list("key", "count")) == [(None, 0), ("g", 1)]


def test_nested_json_transform_on_subquery() -> None:
    row = Record.objects.create(name="nested", payload={"d": ["e", {"f": "g"}]})
    Record.objects.create(name="other", payload={"d": ["e", {"f": "other"}]})
    query = Record.objects.annotate(
        subquery_value=Subquery(Record.objects.filter(pk=OuterRef("pk")).values("payload")),
        key=KeyTransform("d", "subquery_value"),
        chain=KeyTransform("f", KeyTransform("1", "key")),
    ).filter(chain="g")
    assert list(query) == [row]
