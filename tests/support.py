"""Small test-only helpers shared by backend surface tests."""

from __future__ import annotations

from typing import Any


def wrapper_settings(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
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
    values.update(overrides)
    return values
