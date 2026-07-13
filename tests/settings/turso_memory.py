"""Embedded Turso in-memory test settings."""

from .base import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django_pyturso", "NAME": ":memory:"}}
