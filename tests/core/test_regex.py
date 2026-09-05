"""Native regular expression support and its Django capability boundary."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection, models
from django.test.utils import isolate_apps

pytestmark = [pytest.mark.core, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("lookup", "expected"),
    [("regex", ["aa", "ab"]), ("iregex", ["AA", "aa", "ab"])],
)
@isolate_apps()
def test_regex_lookups_execute_native_patterns(lookup: str, expected: list[str]) -> None:
    class Record(models.Model):
        value = models.CharField(max_length=20)
        objects: Any = models.Manager()

        class Meta:
            app_label = "regex_tests"
            db_table = "regex_values"

    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE regex_values (id integer primary key, value text)")
    try:
        Record.objects.bulk_create(
            [Record(value=value) for value in ["aa", "AA", "ab", "a1", "baa"]]
        )
        assert list(
            Record.objects.filter(**{f"value__{lookup}": r"^a(a|b)$"})
            .order_by("value")
            .values_list("value", flat=True)
        ) == expected
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE regex_values")


def test_native_backreferences_are_declared_unsupported() -> None:
    assert connection.features.supports_regex_backreferencing is False
    with connection.cursor() as cursor:
        cursor.execute("SELECT %s REGEXP %s", ("aa", r"^(a)\1$"))
        assert cursor.fetchone() == (None,)
