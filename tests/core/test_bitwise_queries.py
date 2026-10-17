"""Bitwise expressions must execute correctly or fail before SQL execution."""

from __future__ import annotations

import pytest
from django.db import NotSupportedError, connection
from django.db.models import BitAnd, BitOr, BitXor, F, Value
from django.db.models.aggregates import BitAggregate
from django.test.utils import CaptureQueriesContext

from tests.project.models import Entry

pytestmark = [pytest.mark.core, pytest.mark.django_db]


@pytest.mark.parametrize("aggregate", [BitAnd, BitOr, BitXor])
@pytest.mark.parametrize("use_default", [False, True])
def test_bitwise_aggregates_are_rejected_before_sql_execution(
    aggregate: type[BitAggregate], use_default: bool
) -> None:
    Entry.objects.bulk_create([Entry(pk=1, title="first"), Entry(pk=3, title="second")])
    expression = aggregate("pk", default=0) if use_default else aggregate("pk")
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(NotSupportedError, match=aggregate.__name__):
            Entry.objects.aggregate(result=expression)
    assert len(queries) == 0


@pytest.mark.parametrize("use_column", [False, True])
def test_bitwise_xor_is_rejected_before_sql_execution(use_column: bool) -> None:
    Entry.objects.create(title="xor")
    lhs = F("pk") if use_column else Value(3)
    query = Entry.objects.annotate(result=lhs.bitxor(5)).values_list("result", flat=True)
    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(NotSupportedError, match="Bitwise XOR"):
            list(query)
    assert len(queries) == 0


@pytest.mark.parametrize(
    ("method", "rhs", "expected"),
    [("bitand", 5, 1), ("bitor", 5, 7), ("bitleftshift", 2, 12), ("bitrightshift", 1, 1)],
)
def test_supported_bitwise_queries(method: str, rhs: int, expected: int) -> None:
    entry = Entry.objects.create(pk=3, title="bitwise")
    expression = getattr(F("pk"), method)(Value(rhs))
    assert Entry.objects.annotate(result=expression).values_list("result", flat=True).get(
        pk=entry.pk
    ) == expected
