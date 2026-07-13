"""Reference SQLite settings used only by differential tests."""

from .base import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
