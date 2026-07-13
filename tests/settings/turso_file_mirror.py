"""File-backed primary and test mirror settings."""

from copy import deepcopy

from .turso_file import *  # noqa: F403

DATABASES["replica"] = deepcopy(DATABASES["default"])  # noqa: F405
DATABASES["replica"]["TEST"] = {"MIRROR": "default"}  # noqa: F405
