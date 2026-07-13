"""Unsupported in-memory mirror settings used by a rejection test."""

from copy import deepcopy

from .turso_memory import *  # noqa: F403

DATABASES["replica"] = deepcopy(DATABASES["default"])  # noqa: F405
DATABASES["replica"]["TEST"] = {"MIRROR": "default"}  # noqa: F405
