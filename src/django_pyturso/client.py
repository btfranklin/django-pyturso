"""Database client integration for embedded Turso."""

from collections.abc import Iterable

from django.db import NotSupportedError
from django.db.backends.base.client import BaseDatabaseClient


class DatabaseClient(BaseDatabaseClient):
    """Reject dbshell because it would bypass the pyturso connection contract."""

    executable_name = ""

    def runshell(self, parameters: Iterable[str]) -> None:
        raise NotSupportedError(
            "django-pyturso doesn't provide dbshell because external clients "
            "cannot preserve the embedded pyturso connection contract."
        )
