"""Fixtures for the isolated embedded-Turso performance lane."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from django.db import connections

from django_pyturso.base import DatabaseWrapper

from .scenarios import seed_database


@dataclass(frozen=True)
class PerformanceDatabase:
    wrapper: DatabaseWrapper
    path: Path

    @property
    def alias(self) -> str:
        return self.wrapper.alias


def wrapper_settings(database: Path) -> dict[str, Any]:
    return {
        "ENGINE": "django_pyturso",
        "NAME": database,
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


@pytest.fixture(scope="module")
def performance_database(
    tmp_path_factory: pytest.TempPathFactory, django_db_blocker: Any
) -> Iterator[PerformanceDatabase]:
    database = tmp_path_factory.mktemp("django-pyturso-performance") / "performance.db"
    wrapper = DatabaseWrapper(wrapper_settings(database), "performance")
    connections[wrapper.alias] = wrapper
    with django_db_blocker.unblock():
        seed_database(wrapper)
        try:
            yield PerformanceDatabase(wrapper=wrapper, path=database)
        finally:
            wrapper.close()
            del connections[wrapper.alias]
