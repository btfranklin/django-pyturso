"""Django database wrapper for the embedded Turso DB-API driver."""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from itertools import tee
from typing import Any

import turso as Database
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, IntegrityError, NotSupportedError, OperationalError
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.transaction import TransactionManagementError
from django.utils.asyncio import async_unsafe

from .client import DatabaseClient
from .creation import DatabaseCreation
from .features import DatabaseFeatures
from .introspection import DatabaseIntrospection
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor

# Field mappings and operators are adapted from Django 6.0.7's SQLite backend.
# Placeholder conversion deliberately uses a local SQL-aware implementation.
# See docs/design/django-provenance.md.


def _get_varchar_column(data: Mapping[str, Any]) -> str:
    max_length = data["max_length"]
    return "varchar" if max_length is None else f"varchar({max_length})"


class DatabaseWrapper(BaseDatabaseWrapper):
    """Connect Django directly to local Turso databases."""

    vendor = "sqlite"
    display_name = "Turso"
    Database = Database
    SchemaEditorClass = DatabaseSchemaEditor
    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations

    data_types: dict[str, Any] = {
        "AutoField": "integer",
        "BigAutoField": "integer",
        "BinaryField": "BLOB",
        "BooleanField": "bool",
        "CharField": _get_varchar_column,
        "DateField": "date",
        "DateTimeField": "datetime",
        "DecimalField": "decimal",
        "DurationField": "bigint",
        "FileField": "varchar(%(max_length)s)",
        "FilePathField": "varchar(%(max_length)s)",
        "FloatField": "real",
        "IntegerField": "integer",
        "BigIntegerField": "bigint",
        "IPAddressField": "char(15)",
        "GenericIPAddressField": "char(39)",
        "JSONField": "text",
        "PositiveBigIntegerField": "bigint unsigned",
        "PositiveIntegerField": "integer unsigned",
        "PositiveSmallIntegerField": "smallint unsigned",
        "SlugField": "varchar(%(max_length)s)",
        "SmallAutoField": "integer",
        "SmallIntegerField": "smallint",
        "TextField": "text",
        "TimeField": "time",
        "UUIDField": "char(32)",
    }
    data_type_check_constraints = {
        "PositiveBigIntegerField": '"%(column)s" >= 0',
        "JSONField": '(JSON_VALID("%(column)s") OR "%(column)s" IS NULL)',
        "PositiveIntegerField": '"%(column)s" >= 0',
        "PositiveSmallIntegerField": '"%(column)s" >= 0',
    }
    data_types_suffix = {
        "AutoField": "AUTOINCREMENT",
        "BigAutoField": "AUTOINCREMENT",
        "SmallAutoField": "AUTOINCREMENT",
    }
    operators = {
        "exact": "= %s",
        "iexact": "LIKE %s ESCAPE '\\'",
        "contains": "LIKE %s ESCAPE '\\'",
        "icontains": "LIKE %s ESCAPE '\\'",
        "regex": "REGEXP %s",
        "iregex": "REGEXP '(?i)' || %s",
        "gt": "> %s",
        "gte": ">= %s",
        "lt": "< %s",
        "lte": "<= %s",
        "startswith": "LIKE %s ESCAPE '\\'",
        "endswith": "LIKE %s ESCAPE '\\'",
        "istartswith": "LIKE %s ESCAPE '\\'",
        "iendswith": "LIKE %s ESCAPE '\\'",
    }
    pattern_esc = r"REPLACE(REPLACE(REPLACE({}, '\', '\\'), '%%', '\%%'), '_', '\_')"
    pattern_ops = {
        "contains": r"LIKE '%%' || {} || '%%' ESCAPE '\'",
        "icontains": r"LIKE '%%' || UPPER({}) || '%%' ESCAPE '\'",
        "startswith": r"LIKE {} || '%%' ESCAPE '\'",
        "istartswith": r"LIKE UPPER({}) || '%%' ESCAPE '\'",
        "endswith": r"LIKE '%%' || {} ESCAPE '\'",
        "iendswith": r"LIKE '%%' || UPPER({}) ESCAPE '\'",
    }
    transaction_modes = frozenset({"DEFERRED", "IMMEDIATE"})

    transaction_mode: str
    _connected_database_version: tuple[int, int, int]
    health_check_enabled: bool
    health_check_done: bool

    def get_connection_params(self) -> dict[str, Any]:
        settings_dict = self.settings_dict
        raw_name = settings_dict["NAME"]
        if not raw_name:
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. Please supply NAME."
            )
        try:
            database = os.fspath(raw_name)
        except TypeError as exc:
            raise ImproperlyConfigured("Database NAME must be a local filesystem path.") from exc
        if not isinstance(database, str) or not database:
            raise ImproperlyConfigured("Database NAME must be a nonempty local path.")
        if database.startswith("file:") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", database):
            raise ImproperlyConfigured(
                "django-pyturso accepts local paths and exactly ':memory:', not URLs or file URIs."
            )
        for key in ("HOST", "PORT", "USER", "PASSWORD"):
            if settings_dict.get(key):
                raise ImproperlyConfigured(
                    f"django-pyturso doesn't accept the {key} database setting."
                )
        options = dict(settings_dict.get("OPTIONS") or {})
        unknown = set(options) - {"transaction_mode"}
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ImproperlyConfigured(f"Unsupported django-pyturso OPTIONS: {names}.")
        raw_mode = options.get("transaction_mode", "DEFERRED")
        if not isinstance(raw_mode, str) or raw_mode.upper() not in self.transaction_modes:
            allowed = ", ".join(sorted(self.transaction_modes))
            raise ImproperlyConfigured(f"transaction_mode must be one of: {allowed}.")
        self.transaction_mode = raw_mode.upper()
        return {"database": database, "isolation_level": None}

    @async_unsafe
    def get_new_connection(self, conn_params: dict[str, Any]) -> Any:
        try:
            connection = Database.connect(**conn_params)
        except Exception as error:
            # pyturso 0.6.1 raises an extension `turso.IoError` outside its
            # exported PEP 249 hierarchy for database-open failures. It can't
            # pass through Django's normal DatabaseErrorWrapper, so translate
            # only that audited driver defect at the connection boundary.
            error_type = type(error)
            if error_type.__module__ == "turso" and error_type.__name__ == "IoError":
                raise OperationalError(f"Unable to open Turso database: {error}") from error
            raise
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA foreign_keys")
                row = cursor.fetchone()
                if row is None or row[0] != 1:
                    raise DatabaseError("Turso did not enable foreign-key enforcement.")
                cursor.execute("SELECT sqlite_version()")
                version_row = cursor.fetchone()
                if version_row is None:
                    raise DatabaseError("Turso did not report a connected engine version.")
                self._connected_database_version = self._parse_database_version(version_row[0])
            finally:
                cursor.close()
        except BaseException:
            connection.close()
            raise
        return connection

    @staticmethod
    def _parse_database_version(raw_version: object) -> tuple[int, int, int]:
        if not isinstance(raw_version, str):
            raise DatabaseError("Turso returned a non-text engine version.")
        parts = raw_version.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise DatabaseError(f"Invalid Turso engine version: {raw_version!r}.")
        return tuple(int(part) for part in parts)  # type: ignore[return-value]

    def get_database_version(self) -> tuple[int, int, int]:
        return self._connected_database_version

    def create_cursor(self, name: str | None = None) -> Any:
        cursor = self.connection.cursor(factory=TursoCursorWrapper)
        cursor._django_wrapper = self
        return cursor

    def _begin(self) -> None:
        self.connection.execute(f"BEGIN {self.transaction_mode}")

    def _ensure_transaction(self) -> None:
        if self.connection is None or self.autocommit or self.connection.in_transaction:
            return
        if self.in_atomic_block and self.commit_on_exit:
            raise TransactionManagementError(
                "Django is inside atomic() but the Turso transaction is no longer active."
            )
        self._begin()

    def _set_autocommit(self, autocommit: bool) -> None:
        with self.wrap_database_errors:
            if autocommit:
                if self.connection.in_transaction:
                    raise TransactionManagementError(
                        "Commit or roll back before enabling autocommit."
                    )
            elif not self.connection.in_transaction:
                self._begin()

    def _start_transaction_under_autocommit(self) -> None:
        with self.wrap_database_errors:
            self._begin()

    def _read_foreign_key_state(self) -> int:
        with self.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys")
            row = cursor.fetchone()
        if row is None or row[0] not in (0, 1):
            raise DatabaseError("Turso did not report a valid foreign-key state.")
        return int(row[0])

    def disable_constraint_checking(self) -> bool:
        """Disable FK enforcement and report whether this call changed it."""
        if self._read_foreign_key_state() == 0:
            return False
        with self.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF")
        if self._read_foreign_key_state() != 0:
            raise NotSupportedError(
                "Turso did not disable foreign-key checks after PRAGMA readback."
            )
        return True

    def enable_constraint_checking(self) -> None:
        """Enable FK enforcement and verify that the requested state took effect."""
        if self._read_foreign_key_state() == 1:
            return
        with self.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = ON")
        if self._read_foreign_key_state() != 1:
            raise NotSupportedError(
                "Turso did not enable foreign-key checks after PRAGMA readback."
            )

    def check_constraints(self, table_names: Iterable[str] | None = None) -> None:
        """Raise for the first invalid FK without PRAGMA foreign_key_check."""
        with self.cursor() as cursor:
            tables = (
                list(table_names)
                if table_names is not None
                else self.introspection.table_names(cursor)
            )
            for table_name in tables:
                foreign_keys = self._foreign_keys_by_id(cursor, table_name)
                for rows in foreign_keys.values():
                    self._check_foreign_key(cursor, table_name, rows)

    def _foreign_keys_by_id(self, cursor: Any, table_name: str) -> dict[int, list[tuple[Any, ...]]]:
        cursor.execute("PRAGMA foreign_key_list(%s)" % self.ops.quote_name(table_name))
        grouped: defaultdict[int, list[tuple[Any, ...]]] = defaultdict(list)
        for raw_row in cursor.fetchall():
            row = tuple(raw_row)
            grouped[int(row[0])].append(row)
        for rows in grouped.values():
            rows.sort(key=lambda row: int(row[1]))
        return dict(grouped)

    def _resolve_foreign_key_targets(
        self, cursor: Any, target_table: str, rows: list[tuple[Any, ...]]
    ) -> list[str]:
        declared_columns = [row[4] for row in rows]
        if all(column not in (None, "") for column in declared_columns):
            return [str(column) for column in declared_columns]

        primary_key_columns = self.introspection.get_primary_key_columns(cursor, target_table) or []
        if len(primary_key_columns) != len(rows):
            source_columns = tuple(str(row[3]) for row in rows)
            raise DatabaseError(
                "Cannot resolve omitted foreign-key target columns for "
                f"{target_table!r}: source columns {source_columns!r} do not match "
                f"the target primary key {tuple(primary_key_columns)!r}."
            )

        resolved: list[str] = []
        for row, declared_column in zip(rows, declared_columns, strict=True):
            sequence = int(row[1])
            if sequence >= len(primary_key_columns):
                raise DatabaseError(
                    f"Invalid foreign-key sequence {sequence} for table {target_table!r}."
                )
            resolved.append(
                str(declared_column)
                if declared_column not in (None, "")
                else primary_key_columns[sequence]
            )
        return resolved

    def _source_identity(
        self, cursor: Any, table_name: str, child_alias: str
    ) -> tuple[list[str], list[str]]:
        primary_key_columns = self.introspection.get_primary_key_columns(cursor, table_name) or []
        if primary_key_columns:
            return (
                [f"{child_alias}.{self.ops.quote_name(column)}" for column in primary_key_columns],
                primary_key_columns,
            )

        description = self.introspection.get_table_description(cursor, table_name)
        declared_columns = {field.name.casefold() for field in description}
        rowid_name = next(
            (
                candidate
                for candidate in ("rowid", "_rowid_", "oid")
                if candidate.casefold() not in declared_columns
            ),
            None,
        )
        if rowid_name is None:
            raise DatabaseError(
                f"Table {table_name!r} has no primary key or unshadowed rowid alias."
            )
        return [f"{child_alias}.{self.ops.quote_name(rowid_name)}"], [rowid_name]

    def _check_foreign_key(self, cursor: Any, table_name: str, rows: list[tuple[Any, ...]]) -> None:
        target_table = str(rows[0][2])
        source_columns = [str(row[3]) for row in rows]
        target_columns = self._resolve_foreign_key_targets(cursor, target_table, rows)
        child_alias = self.ops.quote_name("django_pyturso_child")
        parent_alias = self.ops.quote_name("django_pyturso_parent")
        identity_sql, identity_names = self._source_identity(cursor, table_name, child_alias)
        source_sql = [f"{child_alias}.{self.ops.quote_name(column)}" for column in source_columns]
        target_sql = [f"{parent_alias}.{self.ops.quote_name(column)}" for column in target_columns]
        nonnull_sql = " AND ".join(f"{column} IS NOT NULL" for column in source_sql)
        join_sql = " AND ".join(
            f"{target} = {source}" for source, target in zip(source_sql, target_sql, strict=True)
        )
        query = (
            f"SELECT {', '.join([*identity_sql, *source_sql])} "
            f"FROM {self.ops.quote_name(table_name)} AS {child_alias} "
            f"WHERE {nonnull_sql} AND NOT EXISTS ("
            f"SELECT 1 FROM {self.ops.quote_name(target_table)} AS {parent_alias} "
            f"WHERE {join_sql}) LIMIT 1"
        )
        cursor.execute(query)
        violation = cursor.fetchone()
        if violation is None:
            return

        identity_values = tuple(violation[: len(identity_names)])
        source_values = tuple(violation[len(identity_names) :])
        identity = ", ".join(
            f"{name}={value!r}" for name, value in zip(identity_names, identity_values, strict=True)
        )
        raise IntegrityError(
            f"Foreign key constraint violation in table {table_name!r}; "
            f"row identified by {identity}. Source columns {tuple(source_columns)!r} "
            f"contain values {source_values!r}, which do not reference table "
            f"{target_table!r} columns {tuple(target_columns)!r}."
        )

    def is_usable(self) -> bool:
        try:
            self.connection.execute("SELECT 1")
        except Database.Error:
            return False
        return True

    def is_in_memory_db(self) -> bool:
        database_name: object = self.settings_dict["NAME"]
        if not isinstance(database_name, str | bytes | os.PathLike):
            return False
        return bool(os.fspath(database_name) == ":memory:")

    def _force_close(self) -> None:
        BaseDatabaseWrapper.close(self)

    def _rollback_active_transaction_for_close(self) -> None:
        """End active engine work before a lifecycle-preserving or physical close."""
        if self.connection is None:
            return
        try:
            if not self.connection.in_transaction:
                return
            self.connection.rollback()
            if self.connection.in_transaction:
                raise DatabaseError("Turso remained in a transaction after rollback.")
        except BaseException:
            # A connection whose transaction state cannot be restored must never
            # remain reusable, including when it owns an in-memory database.
            self._force_close()
            raise

    def _rollback_and_force_close(self) -> None:
        self._rollback_active_transaction_for_close()
        self._force_close()

    @async_unsafe
    def close(self) -> None:
        self.validate_thread_sharing()
        self.run_on_commit = []
        if self.connection is None:
            return
        if self.closed_in_transaction:
            return
        self._rollback_active_transaction_for_close()
        if self.in_atomic_block:
            self._force_close()
            return
        if not self.is_in_memory_db():
            self._force_close()

    def close_if_health_check_failed(self) -> None:
        if self.connection is None or not self.health_check_enabled or self.health_check_done:
            return
        if not self.is_usable():
            self._force_close()
        self.health_check_done = True

    def close_if_unusable_or_obsolete(self) -> None:
        if not self.is_in_memory_db():
            BaseDatabaseWrapper.close_if_unusable_or_obsolete(self)
            return
        if self.connection is None:
            return
        self.health_check_done = False
        if self.get_autocommit() != self.settings_dict["AUTOCOMMIT"]:
            self._rollback_and_force_close()
            return
        try:
            engine_state_drifted = self.autocommit and self.connection.in_transaction
        except Database.Error:
            self._force_close()
            return
        if engine_state_drifted:
            self._rollback_and_force_close()
            return
        if self.errors_occurred:
            if self.is_usable():
                self.errors_occurred = False
                self.health_check_done = True
            else:
                self._force_close()
                return
        if self.close_at is not None and time.monotonic() >= self.close_at:
            self.health_check_done = True

    def inc_thread_sharing(self) -> None:
        if self.is_in_memory_db():
            raise NotSupportedError(
                "In-memory django-pyturso databases cannot be shared across threads; "
                "use a file-backed test database for LiveServerTestCase."
            )
        super().inc_thread_sharing()


_IDENTIFIER_QUOTES = {'"': '"', "`": "`", "[": "]"}


def _convert_placeholders(query: str, *, param_names: list[str] | None) -> str:
    """Translate Django placeholders without interpreting quoted SQL text."""
    converted: list[str] = []
    names = set(param_names) if param_names is not None else None
    index = 0
    state = "sql"
    closing_quote = ""

    while index < len(query):
        character = query[index]
        following = query[index + 1] if index + 1 < len(query) else ""

        if state == "line-comment":
            converted.append(character)
            index += 1
            if character in "\r\n":
                state = "sql"
            continue

        if state == "block-comment":
            if character == "*" and following == "/":
                converted.append("*/")
                index += 2
                state = "sql"
            else:
                converted.append(character)
                index += 1
            continue

        if state == "identifier":
            converted.append(character)
            index += 1
            if character != closing_quote:
                continue
            if closing_quote != "]" and following == closing_quote:
                converted.append(following)
                index += 1
            else:
                state = "sql"
            continue

        if state == "literal":
            if character == "'" and following == "'":
                converted.append("''")
                index += 2
            elif character == "'":
                converted.append(character)
                index += 1
                state = "sql"
            elif character == "%" and following == "%":
                converted.append("%")
                index += 2
            else:
                converted.append(character)
                index += 1
            continue

        if character == "-" and following == "-":
            converted.append("--")
            index += 2
            state = "line-comment"
        elif character == "/" and following == "*":
            converted.append("/*")
            index += 2
            state = "block-comment"
        elif character == "'":
            converted.append(character)
            index += 1
            state = "literal"
        elif character in _IDENTIFIER_QUOTES:
            converted.append(character)
            index += 1
            state = "identifier"
            closing_quote = _IDENTIFIER_QUOTES[character]
        elif character == "%" and following == "%":
            converted.append("%")
            index += 2
        elif names is None and character == "%" and following == "s":
            converted.append("?")
            index += 2
        elif names is not None and character == "%" and following == "(":
            placeholder_end = index + 2
            while placeholder_end < len(query) and query[placeholder_end] != ")":
                if query[placeholder_end : placeholder_end + 2] == "%(":
                    break
                placeholder_end += 1
            if placeholder_end == len(query):
                converted.append(query[index:])
                break
            if query[placeholder_end : placeholder_end + 2] == "%(":
                converted.append(query[index:placeholder_end])
                index = placeholder_end
                continue
            if query[placeholder_end + 1 : placeholder_end + 2] != "s":
                converted.append(query[index : placeholder_end + 1])
                index = placeholder_end + 1
                continue
            name = query[index + 2 : placeholder_end]
            if name not in names:
                raise KeyError(name)
            converted.append(f":{name}")
            index = placeholder_end + 2
        else:
            converted.append(character)
            index += 1

    return "".join(converted)


class TursoCursorWrapper(Database.Cursor):
    """Translate Django format/pyformat placeholders to Turso placeholders."""

    _django_wrapper: DatabaseWrapper

    def _ensure_django_transaction(self) -> None:
        self._django_wrapper._ensure_transaction()

    def execute(self, query: str, params: Any = None) -> Any:
        self._ensure_django_transaction()
        if params is None:
            return super().execute(query)
        names = list(params) if isinstance(params, Mapping) else None
        return super().execute(self.convert_query(query, param_names=names), params)

    def executemany(self, query: str, param_list: Iterable[Any]) -> Any:
        self._ensure_django_transaction()
        peekable, preserved = tee(iter(param_list))
        first = next(peekable, None)
        if first is None:
            return self
        names = list(first) if isinstance(first, Mapping) else None
        return super().executemany(self.convert_query(query, param_names=names), preserved)

    @staticmethod
    def convert_query(query: str, *, param_names: list[str] | None = None) -> str:
        return _convert_placeholders(query, param_names=param_names)
