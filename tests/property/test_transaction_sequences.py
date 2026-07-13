"""Bounded model-based transaction sequences for manual autocommit mode."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from django_pyturso.base import DatabaseWrapper


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


@settings(
    max_examples=30,
    deadline=None,
    derandomize=True,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@given(
    actions=st.lists(
        st.sampled_from(("write", "read", "commit", "rollback")),
        min_size=1,
        max_size=24,
    )
)
def test_manual_transaction_sequences_match_the_reference_model(
    actions: list[str],
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "property_transactions")
    committed: list[int] = []
    pending: list[int] = []
    try:
        with wrapper.cursor() as cursor:
            cursor.execute("CREATE TABLE sequence_probe (value INTEGER)")
        wrapper.set_autocommit(False)

        for index, action in enumerate(actions):
            if action == "write":
                with wrapper.cursor() as cursor:
                    cursor.execute("INSERT INTO sequence_probe VALUES (%s)", (index,))
                pending.append(index)
                assert wrapper.connection.in_transaction is True
            elif action == "read":
                with wrapper.cursor() as cursor:
                    cursor.execute("SELECT value FROM sequence_probe ORDER BY rowid")
                    observed = [row[0] for row in cursor.fetchall()]
                assert observed == [*committed, *pending]
                assert wrapper.connection.in_transaction is True
            elif action == "commit":
                wrapper.commit()
                committed.extend(pending)
                pending.clear()
                assert wrapper.connection.in_transaction is False
            else:
                wrapper.rollback()
                pending.clear()
                assert wrapper.connection.in_transaction is False
            assert wrapper.autocommit is False

        wrapper.rollback()
        pending.clear()
        wrapper.set_autocommit(True)
        with wrapper.cursor() as cursor:
            cursor.execute("SELECT value FROM sequence_probe ORDER BY rowid")
            observed = [row[0] for row in cursor.fetchall()]
        assert observed == committed
        assert wrapper.connection.in_transaction is False
    finally:
        wrapper._force_close()
