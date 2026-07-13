"""Isolated settings for the pinned Django upstream compatibility lane."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

DATABASE_ROOT = Path(
    os.environ.get(
        "DJANGO_PYTURSO_UPSTREAM_DB_DIR",
        Path(tempfile.gettempdir()) / "django-pyturso-upstream-databases",
    )
)
DATABASE_ROOT.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django_pyturso",
        "NAME": DATABASE_ROOT / "default.db",
        "TEST": {"NAME": DATABASE_ROOT / "test-default.db"},
    },
    "other": {
        "ENGINE": "django_pyturso",
        "NAME": DATABASE_ROOT / "other.db",
        "TEST": {"NAME": DATABASE_ROOT / "test-other.db"},
    },
}

SECRET_KEY = "django-pyturso-upstream-tests"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TIME_ZONE = "UTC"
USE_TZ = False
