"""Deterministic property coverage for cursors, values, and identifiers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from itertools import count
from typing import Any, cast

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from django_pyturso.base import DatabaseWrapper, TursoCursorWrapper

ALIASES = count()
PROPERTY_SETTINGS = settings(
    max_examples=40,
    deadline=None,
    derandomize=True,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)


@pytest.fixture(autouse=True)
def unblock_database_access(django_db_blocker: Any) -> Iterator[None]:
    with django_db_blocker.unblock():
        yield


def wrapper_settings() -> dict[str, Any]:
    return {
        "ENGINE": "django_pyturso",
        "NAME": ":memory:",
        "OPTIONS": {},
        "HOST": "",
        "PORT": "",
        "USER": "",
        "PASSWORD": "",
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "TIME_ZONE": None,
        "TEST": {"NAME": None},
    }


@contextmanager
def memory_wrapper() -> Iterator[DatabaseWrapper]:
    wrapper = DatabaseWrapper(wrapper_settings(), f"property_{next(ALIASES)}")
    try:
        yield wrapper
    finally:
        wrapper._force_close()


format_literal = st.text(
    alphabet=st.characters(blacklist_characters="%"),
    max_size=12,
)
format_segment = st.one_of(st.just("%s"), st.just("%%"), format_literal)
identifier = st.text(
    alphabet=st.characters(blacklist_characters="\x00"),
    min_size=1,
    max_size=24,
).filter(
    lambda value: not (
        (value.startswith('"') and value.endswith('"'))
        or value.casefold().startswith("sqlite_")
    )
    and value == value.casefold()
)
driver_scalar = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**63), max_value=2**63 - 1),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
    st.binary(max_size=128),
    st.text(max_size=128),
)


@PROPERTY_SETTINGS
@given(segments=st.lists(format_segment, min_size=1, max_size=16))
def test_format_placeholder_conversion_is_local_and_preserves_escaped_percent(
    segments: list[str],
) -> None:
    query = " | ".join(segments)
    expected = " | ".join(
        "?" if segment == "%s" else "%" if segment == "%%" else segment
        for segment in segments
    )

    assert TursoCursorWrapper.convert_query(query) == expected


@PROPERTY_SETTINGS
@given(
    names=st.lists(
        st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,15}", fullmatch=True),
        min_size=1,
        max_size=12,
        unique=True,
    )
)
def test_named_placeholder_conversion_uses_driver_bindings(names: list[str]) -> None:
    query = ", ".join(f"%({name})s" for name in names)
    expected = ", ".join(f":{name}" for name in names)

    assert TursoCursorWrapper.convert_query(query, param_names=names) == expected


@PROPERTY_SETTINGS
@given(value=driver_scalar)
def test_public_cursor_round_trips_driver_scalars(value: object) -> None:
    with memory_wrapper() as wrapper, wrapper.cursor() as cursor:
        cursor.execute("SELECT %s", (cast(Any, value),))
        returned = cursor.fetchone()[0]

    expected = int(value) if isinstance(value, bool) else value
    assert returned == expected


@PROPERTY_SETTINGS
@given(table_name=identifier, column_name=identifier)
def test_quoted_unicode_identifiers_round_trip(
    table_name: str, column_name: str
) -> None:
    with memory_wrapper() as wrapper:
        quoted_table = wrapper.ops.quote_name(table_name)
        quoted_column = wrapper.ops.quote_name(column_name)
        with wrapper.cursor() as cursor:
            cursor.execute(f"CREATE TABLE {quoted_table} ({quoted_column} TEXT)")
            cursor.execute(
                f"INSERT INTO {quoted_table} ({quoted_column}) VALUES (%s)",
                ("round-trip",),
            )
            cursor.execute(f"SELECT {quoted_column} FROM {quoted_table}")
            returned = cursor.fetchone()

    assert returned == ("round-trip",)
