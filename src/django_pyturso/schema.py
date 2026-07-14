"""Schema editing for embedded Turso."""

from __future__ import annotations

import copy
import datetime
import decimal
import math
from types import TracebackType
from typing import Any, Self, cast

from django.apps.registry import Apps
from django.db import NotSupportedError
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.ddl_references import Statement
from django.db.backends.utils import strip_quotes
from django.db.models import CompositePrimaryKey, UniqueConstraint

from .features import DatabaseFeatures

# The table-remake algorithm is substantially adapted from Django 6.0.7's
# django/db/backends/sqlite3/schema.py. Constraint state management and default
# quoting are local Turso implementations. See docs/design/django-provenance.md.


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    """Edit schemas using Turso's SQLite-compatible DDL surface."""

    sql_delete_table = "DROP TABLE %(table)s"
    sql_create_inline_fk = (
        "REFERENCES %(to_table)s (%(to_column)s) DEFERRABLE INITIALLY DEFERRED"
    )
    sql_create_unique = "CREATE UNIQUE INDEX %(name)s ON %(table)s (%(columns)s)"
    sql_delete_unique = "DROP INDEX %(name)s"
    sql_create_fk = None  # type: ignore[assignment]
    sql_create_column_inline_fk = sql_create_inline_fk
    sql_alter_table_comment = None  # type: ignore[assignment]
    sql_alter_column_comment = None  # type: ignore[assignment]

    _original_foreign_keys: int | None = None

    def _foreign_key_state(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys")
            row = cursor.fetchone()
        if row is None or row[0] not in (0, 1):
            raise NotSupportedError("Turso did not report a valid foreign-key state.")
        return int(row[0])

    def _set_foreign_key_state(self, enabled: bool) -> None:
        requested = 1 if enabled else 0
        with self.connection.cursor() as cursor:
            cursor.execute(f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}")
        if self._foreign_key_state() != requested:
            state = "enable" if enabled else "disable"
            raise NotSupportedError(
                f"Turso could not {state} foreign-key checks for schema editing. "
                "Enter the schema editor outside transaction.atomic()."
            )

    def _dispose_unrestorable_connection(self) -> None:
        self.connection._force_close()  # type: ignore[attr-defined]

    def _restore_foreign_key_state(self) -> None:
        if self._original_foreign_keys is None:
            return
        try:
            self._set_foreign_key_state(bool(self._original_foreign_keys))
        except BaseException:
            self._dispose_unrestorable_connection()
            raise
        finally:
            self._original_foreign_keys = None

    def __enter__(self) -> Self:
        self.connection.ensure_connection()
        try:
            self._original_foreign_keys = self._foreign_key_state()
        except BaseException:
            self._dispose_unrestorable_connection()
            raise
        try:
            if self._original_foreign_keys and self.connection.in_atomic_block:
                raise NotSupportedError(
                    "Turso schema editing must begin outside transaction.atomic() "
                    "so foreign-key checks can be disabled and verified first."
                )
            if self._original_foreign_keys:
                self._set_foreign_key_state(False)
            return super().__enter__()
        except BaseException as primary:
            try:
                self._restore_foreign_key_state()
            except BaseException as restoration:
                raise primary from restoration
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        check_error: BaseException | None = None
        check_traceback: TracebackType | None = None
        if exc_type is None:
            try:
                self.connection.check_constraints()
            except BaseException as error:
                check_error = error
                check_traceback = error.__traceback__
                exc_type = type(error)
                exc_value = error
                traceback = check_traceback

        exit_error: BaseException | None = None
        try:
            super().__exit__(exc_type, exc_value, traceback)
        except BaseException as error:
            exit_error = error

        try:
            self._restore_foreign_key_state()
        except BaseException as restoration:
            primary = exit_error or check_error or exc_value
            if primary is not None:
                raise primary.with_traceback(primary.__traceback__) from restoration
            raise

        if exit_error is not None:
            raise exit_error.with_traceback(exit_error.__traceback__)
        if check_error is not None:
            raise check_error.with_traceback(check_traceback)

    def quote_value(self, value: Any) -> str:
        """Quote a Python value without stdlib SQLite adapter registration."""

        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, int | decimal.Decimal):
            return str(value)
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                raise ValueError("Non-finite floats cannot be used as Turso schema defaults.")
            return repr(value)
        if isinstance(value, bytes | bytearray | memoryview):
            return f"X'{bytes(value).hex()}'"
        if isinstance(value, datetime.datetime):
            value = value.isoformat(" ")
        elif isinstance(value, datetime.date | datetime.time):
            value = value.isoformat()
        if isinstance(value, str):
            return "'%s'" % value.replace("'", "''")
        raise ValueError(f"Unsupported Turso schema default type: {type(value).__name__}.")

    def prepare_default(self, value: Any) -> str:
        return self.quote_value(value)

    def _remake_table(
        self,
        model: Any,
        create_field: Any = None,
        delete_field: Any = None,
        alter_fields: list[tuple[Any, Any]] | None = None,
    ) -> None:
        """Recreate a table with an updated definition and copy its data."""

        def is_self_referential(field: Any) -> bool:
            return field.is_relation and field.remote_field.model is model

        body = {
            field.name: field.clone() if is_self_referential(field) else field
            for field in model._meta.local_concrete_fields
        }
        primary_key = model._meta.pk
        if isinstance(primary_key, CompositePrimaryKey):
            body[primary_key.name] = primary_key.clone()

        mapping = {
            field.column: self.quote_name(field.column)
            for field in model._meta.local_concrete_fields
            if field.generated is False
        }
        rename_mapping: dict[str, str] = {}
        alter_fields = alter_fields or []
        if getattr(create_field, "primary_key", False) or any(
            getattr(new_field, "primary_key", False) for _, new_field in alter_fields
        ):
            for name, field in list(body.items()):
                if field.primary_key and not any(
                    name == new_field.name for _, new_field in alter_fields
                ):
                    original_column = field.column
                    field = field.clone()
                    body[name] = field
                    field.primary_key = False
                    if field.auto_created:
                        del body[name]
                        del mapping[original_column]

        if create_field:
            body[create_field.name] = create_field
            if (
                not create_field.has_db_default()
                and not create_field.generated
                and create_field.concrete
            ):
                mapping[create_field.column] = self.prepare_default(
                    self.effective_default(create_field)
                )

        for old_field, new_field in alter_fields:
            body.pop(old_field.name, None)
            mapping.pop(old_field.column, None)
            body[new_field.name] = new_field
            rename_mapping[old_field.name] = new_field.name
            if new_field.generated:
                continue
            if old_field.null and not new_field.null:
                if not new_field.has_db_default():
                    default = self.prepare_default(self.effective_default(new_field))
                else:
                    default, _ = self.db_default_sql(new_field)
                mapping[new_field.column] = "coalesce(%(col)s, %(default)s)" % {
                    "col": self.quote_name(old_field.column),
                    "default": default,
                }
            else:
                mapping[new_field.column] = self.quote_name(old_field.column)

        if delete_field:
            del body[delete_field.name]
            mapping.pop(delete_field.column, None)
            if (
                delete_field.many_to_many
                and delete_field.remote_field.through._meta.auto_created
            ):
                self.delete_model(delete_field.remote_field.through)
                return

        apps = Apps()
        unique_together = [
            [rename_mapping.get(name, name) for name in unique]
            for unique in model._meta.unique_together
        ]
        indexes = model._meta.indexes
        if delete_field:
            indexes = [
                index for index in indexes if delete_field.name not in index.fields
            ]
        constraints = list(model._meta.constraints)

        body_copy = copy.deepcopy(body)
        meta_contents = {
            "app_label": model._meta.app_label,
            "db_table": model._meta.db_table,
            "unique_together": unique_together,
            "indexes": indexes,
            "constraints": constraints,
            "apps": apps,
        }
        meta = type("Meta", (), meta_contents)
        body_copy["Meta"] = meta
        body_copy["__module__"] = model.__module__
        type(model._meta.object_name, model.__bases__, body_copy)

        body_copy = copy.deepcopy(body)
        meta_contents = {
            "app_label": model._meta.app_label,
            "db_table": "new__%s" % strip_quotes(model._meta.db_table),
            "unique_together": unique_together,
            "indexes": indexes,
            "constraints": constraints,
            "apps": apps,
        }
        meta = type("Meta", (), meta_contents)
        body_copy["Meta"] = meta
        body_copy["__module__"] = model.__module__
        new_model: Any = type(
            "New%s" % model._meta.object_name, model.__bases__, body_copy
        )

        if delete_field and delete_field.attname == new_model._meta.pk.attname:
            auto_pk = new_model._meta.pk
            delattr(new_model, auto_pk.attname)
            new_model._meta.local_fields.remove(auto_pk)
            new_model.pk = None

        self.create_model(new_model)
        self.execute(
            "INSERT INTO %s (%s) SELECT %s FROM %s"
            % (
                self.quote_name(new_model._meta.db_table),
                ", ".join(self.quote_name(column) for column in mapping),
                ", ".join(mapping.values()),
                self.quote_name(model._meta.db_table),
            )
        )
        self.delete_model(model, handle_autom2m=False)
        self.alter_db_table(new_model, new_model._meta.db_table, model._meta.db_table)

        for sql in self.deferred_sql:
            self.execute(sql)
        self.deferred_sql = []

    def delete_model(self, model: Any, handle_autom2m: bool = True) -> None:
        if handle_autom2m:
            super().delete_model(model)
            return
        self.execute(self.sql_delete_table % {"table": self.quote_name(model._meta.db_table)})
        for sql in list(self.deferred_sql):
            if isinstance(sql, Statement) and sql.references_table(model._meta.db_table):
                self.deferred_sql.remove(sql)

    def add_field(self, model: Any, field: Any) -> None:
        if field.many_to_many and field.remote_field.through._meta.auto_created:
            self.create_model(field.remote_field.through)
        elif isinstance(field, CompositePrimaryKey):
            return
        else:
            # Turso 0.7.0 rewrites `ADD COLUMN ... NULL` as `NOT NULL` in the
            # stored schema. Remaking the table is required even for a plain
            # nullable field so Django's nullability contract remains true.
            self._remake_table(model, create_field=field)

    def remove_field(self, model: Any, field: Any) -> None:
        if field.many_to_many:
            if field.remote_field.through._meta.auto_created:
                self.delete_model(field.remote_field.through)
        elif (
            cast(DatabaseFeatures, self.connection.features).can_alter_table_drop_column
            and not field.primary_key
            and not field.unique
            and not field.db_index
            and not (field.remote_field and field.db_constraint)
        ):
            super().remove_field(model, field)
        elif field.db_parameters(connection=self.connection)["type"] is not None:
            self._remake_table(model, delete_field=field)

    def _alter_field(
        self,
        model: Any,
        old_field: Any,
        new_field: Any,
        old_type: str,
        new_type: str,
        old_db_params: dict[str, Any],
        new_db_params: dict[str, Any],
        strict: bool = False,
    ) -> None:
        if (
            old_field.column != new_field.column
            and self.column_sql(model, old_field) == self.column_sql(model, new_field)
            and not (
                old_field.remote_field
                and old_field.db_constraint
                or new_field.remote_field
                and new_field.db_constraint
            )
        ):
            self.execute(
                self._rename_field_sql(  # type: ignore[attr-defined]
                    model._meta.db_table, old_field, new_field, new_type
                )
            )
            return

        self._remake_table(model, alter_fields=[(old_field, new_field)])
        old_collation = old_db_params.get("collation")
        new_collation = new_db_params.get("collation")
        if new_field.unique and (old_type != new_type or old_collation != new_collation):
            related_models = set()
            opts = new_field.model._meta
            for remote_field in opts.related_objects:
                if remote_field.related_model == model:
                    continue
                if not remote_field.many_to_many:
                    if remote_field.field_name == new_field.name:
                        related_models.add(remote_field.related_model)
                elif new_field.primary_key and remote_field.through._meta.auto_created:
                    related_models.add(remote_field.through)
            if new_field.primary_key:
                for many_to_many in opts.many_to_many:
                    if many_to_many.related_model == model:
                        continue
                    if many_to_many.remote_field.through._meta.auto_created:
                        related_models.add(many_to_many.remote_field.through)
            for related_model in related_models:
                self._remake_table(related_model)

    def _alter_many_to_many(
        self, model: Any, old_field: Any, new_field: Any, strict: bool
    ) -> None:
        if (
            old_field.remote_field.through._meta.db_table
            == new_field.remote_field.through._meta.db_table
        ):
            self._remake_table(
                old_field.remote_field.through,
                alter_fields=[
                    (
                        old_field.remote_field.through._meta.get_field(
                            old_field.m2m_reverse_field_name()
                        ),
                        new_field.remote_field.through._meta.get_field(
                            new_field.m2m_reverse_field_name()
                        ),
                    ),
                    (
                        old_field.remote_field.through._meta.get_field(
                            old_field.m2m_field_name()
                        ),
                        new_field.remote_field.through._meta.get_field(
                            new_field.m2m_field_name()
                        ),
                    ),
                ],
            )
            return

        self.create_model(new_field.remote_field.through)
        self.execute(
            "INSERT INTO %s (%s) SELECT %s FROM %s"
            % (
                self.quote_name(new_field.remote_field.through._meta.db_table),
                ", ".join(
                    ["id", new_field.m2m_column_name(), new_field.m2m_reverse_name()]
                ),
                ", ".join(
                    ["id", old_field.m2m_column_name(), old_field.m2m_reverse_name()]
                ),
                self.quote_name(old_field.remote_field.through._meta.db_table),
            )
        )
        self.delete_model(old_field.remote_field.through)

    def add_constraint(self, model: Any, constraint: Any) -> None:
        if isinstance(constraint, UniqueConstraint) and (
            constraint.condition
            or constraint.contains_expressions
            or constraint.include  # type: ignore[attr-defined]
            or constraint.deferrable
        ):
            super().add_constraint(model, constraint)
        else:
            self._remake_table(model)

    def remove_constraint(self, model: Any, constraint: Any) -> None:
        if isinstance(constraint, UniqueConstraint) and (
            constraint.condition
            or constraint.contains_expressions
            or constraint.include  # type: ignore[attr-defined]
            or constraint.deferrable
        ):
            super().remove_constraint(model, constraint)
        else:
            self._remake_table(model)

    def _collate_sql(self, collation: str) -> str:
        return "COLLATE " + collation
