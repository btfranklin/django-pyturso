"""Test database lifecycle for embedded Turso."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Never

from django.db import NotSupportedError
from django.db.backends.base.creation import BaseDatabaseCreation

if TYPE_CHECKING:
    from .base import DatabaseWrapper


class DatabaseCreation(BaseDatabaseCreation):
    """Create local file or single-connection in-memory test databases."""

    connection: DatabaseWrapper

    @staticmethod
    def is_in_memory_db(database_name: object) -> bool:
        if not isinstance(database_name, str | bytes | os.PathLike):
            return False
        return bool(os.fspath(database_name) == ":memory:")

    @staticmethod
    def _database_path(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, os.PathLike):
            path: object = os.fspath(value)
            if isinstance(path, str):
                return path
        raise TypeError("Database names must be strings or paths that return strings.")

    def _get_test_db_name(self) -> str:
        test_settings = self.connection.settings_dict["TEST"]
        if not isinstance(test_settings, Mapping):
            raise TypeError("TEST must be a mapping of test database settings.")
        configured_name: object = test_settings["NAME"]
        if configured_name:
            return self._database_path(configured_name)
        source_name = self._database_path(self.connection.settings_dict["NAME"])
        if self.is_in_memory_db(source_name):
            return ":memory:"
        path = Path(source_name)
        return str(path.with_name(f"test_{path.name}"))

    def _create_test_db(self, verbosity: int, autoclobber: bool, keepdb: bool = False) -> str:
        test_database_name = self._get_test_db_name()
        self._close_for_test_database_switch()
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

    def get_test_db_clone_settings(self, suffix: str) -> Never:
        raise NotSupportedError("django-pyturso doesn't support parallel test database cloning.")

    def destroy_test_db(
        self,
        old_database_name: str | None = None,
        verbosity: int = 1,
        keepdb: bool = False,
        suffix: str | None = None,
    ) -> None:
        self._close_for_test_database_switch()
        super().destroy_test_db(old_database_name, verbosity, keepdb, suffix)

    def _destroy_test_db(self, test_database_name: str, verbosity: int) -> None:
        if test_database_name and not self.is_in_memory_db(test_database_name):
            self.connection.close()
            self._remove_database_artifacts(Path(test_database_name))

    @staticmethod
    def _remove_database_artifacts(path: Path) -> None:
        for artifact in (path, Path(f"{path}-wal"), Path(f"{path}-log")):
            if artifact.exists():
                artifact.unlink()

    def set_as_test_mirror(self, primary_settings_dict: Mapping[str, object]) -> None:
        if self.is_in_memory_db(primary_settings_dict["NAME"]):
            raise NotSupportedError(
                "django-pyturso test mirrors require a file-backed primary database."
            )
        self._close_for_test_database_switch()
        self.connection.settings_dict["NAME"] = primary_settings_dict["NAME"]

    def _close_for_test_database_switch(self) -> None:
        connection = self.connection
        connection.validate_thread_sharing()
        connection.validate_no_atomic_block()
        connection._rollback_and_force_close()

    def test_db_signature(self) -> tuple[object, str]:  # type: ignore[override]
        # Django accepts variable-length signatures; its stub requires four items.
        test_database_name = self._get_test_db_name()
        if self.is_in_memory_db(test_database_name):
            return (self.connection.settings_dict["NAME"], self.connection.alias)
        return (self.connection.settings_dict["NAME"], test_database_name)
