"""Embedded Turso MVCC test settings for one process."""

import os

from .base import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django_pyturso",
        "NAME": os.environ.get("DJANGO_PYTURSO_MVCC_DB", ":memory:"),
        "OPTIONS": {"journal_mode": "MVCC", "transaction_mode": "CONCURRENT"},
    }
}
