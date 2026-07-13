"""Embedded Turso file-backed test settings."""

import os
import tempfile
from pathlib import Path

from .base import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django_pyturso",
        "NAME": Path(os.environ.get("DJANGO_PYTURSO_TEST_DB", tempfile.gettempdir()))
        / "django-pyturso-tests.db",
    }
}
