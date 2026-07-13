"""Test database lifecycle for embedded Turso."""

import os
from pathlib import Path
from typing import Any

from django.db import NotSupportedError
from django.db.backends.base.creation import BaseDatabaseCreation


class DatabaseCreation(BaseDatabaseCreation):
    """Create local file or single-connection in-memory test databases."""

    @staticmethod
    def is_in_memory_db(database_name: object) -> bool:
        if not isinstance(database_name, str | bytes | os.PathLike):
            return False
        return bool(os.fspath(database_name) == ":memory:")

    def _get_test_db_name(self) -> str:
        configured_name = self.connection.settings_dict["TEST"]["NAME"]
        if configured_name:
            return str(os.fspath(configured_name))
        source_name = os.fspath(self.connection.settings_dict["NAME"])
        if self.is_in_memory_db(source_name):
            return ":memory:"
        path = Path(source_name)
        return str(path.with_name(f"test_{path.name}"))

    def _create_test_db(self, verbosity: int, autoclobber: bool, keepdb: bool = False) -> str:
        test_database_name = self._get_test_db_name()
        if self.is_in_memory_db(test_database_name) or keepdb:
            return test_database_name
        path = Path(test_database_name)
        if path.exists() and not autoclobber:
            confirm = input(
                f"Type 'yes' to delete the test database {test_database_name!r}, "
                "or 'no' to cancel: "
            )
            if confirm != "yes":
                self.log("Tests cancelled.")
                raise SystemExit(1)
        try:
            self._remove_database_artifacts(path)
        except OSError as exc:
            self.log(f"Unable to remove the old test database: {exc}")
            raise SystemExit(2) from exc
        return test_database_name

    def _clone_test_db(self, suffix: str, verbosity: int, keepdb: bool = False) -> None:
        raise NotSupportedError("django-pyturso doesn't support parallel test database cloning.")

    def get_test_db_clone_settings(self, suffix: str) -> dict[str, Any]:
        raise NotSupportedError("django-pyturso doesn't support parallel test database cloning.")

    def _destroy_test_db(self, test_database_name: str, verbosity: int) -> None:
        if test_database_name and not self.is_in_memory_db(test_database_name):
            self.connection.close()
            self._remove_database_artifacts(Path(test_database_name))

    @staticmethod
    def _remove_database_artifacts(path: Path) -> None:
        for artifact in (path, Path(f"{path}-wal")):
            if artifact.exists():
                artifact.unlink()

    def set_as_test_mirror(self, primary_settings_dict: dict[str, Any]) -> None:
        if self.is_in_memory_db(primary_settings_dict["NAME"]):
            raise NotSupportedError(
                "django-pyturso test mirrors require a file-backed primary database."
            )
        super().set_as_test_mirror(primary_settings_dict)

    def test_db_signature(self) -> tuple[Any, ...]:
        test_database_name = self._get_test_db_name()
        if self.is_in_memory_db(test_database_name):
            return (self.connection.settings_dict["NAME"], self.connection.alias)
        return (self.connection.settings_dict["NAME"], test_database_name)
