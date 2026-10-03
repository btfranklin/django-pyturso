"""Django expression regressions. See docs/testing/django-regressions.md."""

from decimal import Decimal

import pytest
from django.db.models import DecimalField, Exists, ExpressionWrapper, F, Q, Value

from tests.django_regressions.models import NamedRank, Record

pytestmark = pytest.mark.core


def test_range_lookup_with_field_expressions() -> None:
    for chairs in (20, 40, 50, 60, 300):
        Record.objects.create(name=str(chairs), number=50 if chairs != 300 else 99, other=chairs)
    assert set(
        Record.objects.filter(number__range=(F("other"), 100)).values_list("other", flat=True)
    ) == {20, 40, 50}
    assert set(
        Record.objects.filter(number__range=(F("other") - 10, F("other") + 10)).values_list(
            "other", flat=True
        )
    ) == {40, 50, 60}
    assert set(
        Record.objects.filter(number__range=(F("other") - 10, 100)).values_list("other", flat=True)
    ) == {20, 40, 50, 60}


def test_field_expression_reuse_across_models() -> None:
    expression = F("id")
    record = Record.objects.create(name="record")
    rank = NamedRank.objects.create(rank=1, name="rank")
    record_query = Record.objects.filter(id=expression)
    assert record_query.get() == record
    assert NamedRank.objects.filter(id=expression).get() == rank
    assert record_query.get() == record


def test_decimal_expression_filter() -> None:
    row = Record.objects.create(name="decimal", number=0, amount=Decimal("1"))
    query = Record.objects.annotate(
        x=ExpressionWrapper(Value(1), output_field=DecimalField()),
    ).filter(Q(x=1, number=0) & Q(x=Decimal("1")))
    assert list(query) == [row]


def test_negated_empty_exists_filter_and_annotation() -> None:
    row = Record.objects.create(name="exists")
    assert list(Record.objects.filter(~Exists(Record.objects.none()) & Q(pk=row.pk))) == [row]
    query = Record.objects.annotate(not_exists=~Exists(Record.objects.none())).filter(pk=row.pk)
    assert list(query) == [row]
    assert query.values_list("not_exists", flat=True).get() is True
