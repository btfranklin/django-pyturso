"""Schema editing for embedded Turso."""

from __future__ import annotations

import copy
import datetime
import decimal
import math
from types import TracebackType
from typing import TYPE_CHECKING, Never, Protocol, Self, cast

from django.apps.registry import Apps
from django.db import NotSupportedError
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.ddl_references import Statement
from django.db.backends.utils import strip_quotes
from django.db.models import CompositePrimaryKey, Field, ManyToManyField, Model, UniqueConstraint
from django.db.models.constraints import BaseConstraint
from django.db.models.fields.reverse_related import ManyToManyRel

if TYPE_CHECKING:
    from .base import DatabaseWrapper

type SchemaField = Field[Never, object]


def _column(field: SchemaField) -> str:
    column = field.column
    if column is None:
        raise ValueError("Expected a database column for this field.")
    return column


class _IndexedField(Protocol):
    db_index: bool | None


class _ConstrainedField(Protocol):
    db_constraint: bool


def _db_index(field: SchemaField) -> bool | None:
    # Field.db_index is present in Django, but its stub omits the attribute.
    return cast(_IndexedField, field).db_index


def _db_constraint(field: SchemaField) -> bool:
    # Call this only for relation fields that support database constraints.
    return cast(_ConstrainedField, field).db_constraint


def _model_field(model: type[Model], name: str) -> SchemaField:
    # Intermediary-model field names identify forward ForeignKey fields.
    return cast(SchemaField, model._meta.get_field(name))


def _through_model(field: SchemaField) -> type[Model]:
    # Callers select many-to-many fields from Django's resolved model metadata.
    through = cast(ManyToManyField[Model, Model], field).remote_field.through
    if through is None:
        raise ValueError("Expected a resolved many-to-many model.")
    return through


# The table-remake algorithm follows Django 6.0.7's SQLite backend. Constraint
# state management and default quoting are local Turso implementations.


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    """Edit schemas using Turso's SQLite-compatible DDL surface."""

    connection: DatabaseWrapper
    deferred_sql: list[Statement | str]

    sql_delete_table = "DROP TABLE %(table)s"
    sql_create_inline_fk = (
        "REFERENCES %(to_table)s (%(to_column)s) %(on_delete_db)s DEFERRABLE INITIALLY DEFERRED"
    )
    sql_create_unique = "CREATE UNIQUE INDEX %(name)s ON %(table)s (%(columns)s)"
    sql_delete_unique = "DROP INDEX %(name)s"
    # Django permits None for unsupported DDL; these stubs require strings.
    sql_create_fk = None  # type: ignore[assignment]
    sql_create_column_inline_fk = sql_create_inline_fk
    sql_alter_table_comment = None  # type: ignore[assignment]
    sql_alter_column_comment = None  # type: ignore[assignment]

    _original_foreign_keys: int | None = None
    _original_transaction_mode: str | None = None

    def _restore_transaction_mode(self) -> None:
        if self._original_transaction_mode is not None:
            self.connection.transaction_mode = self._original_transaction_mode
            self._original_transaction_mode = None

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
        self.connection._force_close()

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
        if getattr(self.connection, "transaction_mode", None) == "CONCURRENT":
            if not self.connection.get_autocommit() or self.connection.in_atomic_block:
                raise NotSupportedError(
                    "Concurrent schema editing must begin outside an active transaction."
                )
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
            if getattr(self.connection, "transaction_mode", None) == "CONCURRENT":
                self._original_transaction_mode = "CONCURRENT"
                self.connection.transaction_mode = "IMMEDIATE"
            return super().__enter__()
        except BaseException as primary:
            try:
                self._restore_foreign_key_state()
            except BaseException as restoration:
                raise primary from restoration
            finally:
                self._restore_transaction_mode()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self._exit_schema(exc_type, exc_value, traceback)
        finally:
            self._restore_transaction_mode()

    def _exit_schema(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        schema_error: BaseException | None = None
        schema_traceback: TracebackType | None = None
        if exc_type is None:
            try:
                # Run deferred DDL here so its errors reach the atomic exit.
                deferred_sql, self.deferred_sql = self.deferred_sql, []
                for sql in deferred_sql:
                    self.execute(sql, None)
                self.connection.check_constraints()
            except BaseException as error:
                schema_error = error
                schema_traceback = error.__traceback__
                exc_type = type(error)
                exc_value = error
                traceback = schema_traceback

        exit_error: BaseException | None = None
        try:
            super().__exit__(exc_type, exc_value, traceback)
        except BaseException as error:
            exit_error = error

        try:
            self._restore_foreign_key_state()
        except BaseException as restoration:
            primary = exit_error or schema_error or exc_value
            if primary is not None:
                raise primary.with_traceback(primary.__traceback__) from restoration
            raise

        if exit_error is not None:
            raise exit_error.with_traceback(exit_error.__traceback__)
        if schema_error is not None:
            raise schema_error.with_traceback(schema_traceback)

    def quote_value(self, value: object) -> str:
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

    def prepare_default(self, value: object) -> str:
        return self.quote_value(value)

    def _remake_table(
        self,
        model: type[Model],
        create_field: SchemaField | None = None,
        delete_field: SchemaField | None = None,
        alter_fields: list[tuple[SchemaField, SchemaField]] | None = None,
    ) -> None:
        """Recreate a table with an updated definition and copy its data."""

        def is_self_referential(field: SchemaField) -> bool:
            return (
                field.is_relation
                and field.remote_field is not None
                and field.remote_field.model is model
            )

        body: dict[str, SchemaField] = {
            field.name: field.clone() if is_self_referential(field) else field
            for field in model._meta.local_concrete_fields
        }
        primary_key = model._meta.pk
        if isinstance(primary_key, CompositePrimaryKey):
            body[primary_key.name] = primary_key.clone()

        mapping = {
            _column(field): self.quote_name(_column(field))
            for field in model._meta.local_concrete_fields
            if field.generated is False
        }
        rename_mapping: dict[str, str] = {}
        alter_fields = alter_fields or []
        if (create_field is not None and create_field.primary_key) or any(
            new_field.primary_key for _, new_field in alter_fields
        ):
            for name, field in list(body.items()):
                if field.primary_key and not any(
                    name == new_field.name for _, new_field in alter_fields
                ):
                    original_column = _column(field)
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
                mapping[_column(create_field)] = self.prepare_default(
                    self.effective_default(create_field)
                )

        for old_field, new_field in alter_fields:
            body.pop(old_field.name, None)
            mapping.pop(_column(old_field), None)
            body[new_field.name] = new_field
            rename_mapping[old_field.name] = new_field.name
            if new_field.generated:
                continue
            if old_field.null and not new_field.null:
                if not new_field.has_db_default():
                    default = self.prepare_default(self.effective_default(new_field))
                else:
                    default, _ = self.db_default_sql(new_field)
                mapping[_column(new_field)] = "coalesce(%(col)s, %(default)s)" % {
                    "col": self.quote_name(_column(old_field)),
                    "default": default,
                }
            else:
                mapping[_column(new_field)] = self.quote_name(_column(old_field))

        if delete_field:
            del body[delete_field.name]
            if delete_field.column is not None:
                mapping.pop(delete_field.column, None)
            if delete_field.many_to_many and _through_model(delete_field)._meta.auto_created:
                self.delete_model(_through_model(delete_field))
                return

        apps = Apps()
        unique_together = [
            [rename_mapping.get(name, name) for name in unique]
            for unique in model._meta.unique_together
        ]
        indexes = model._meta.indexes
        if delete_field:
            indexes = [index for index in indexes if delete_field.name not in index.fields]
        constraints = list(model._meta.constraints)

        # Register the original-table model in the temporary app registry.
        # This lets relations resolve when the replacement model is built.
        original_body: dict[str, object] = copy.deepcopy(dict[str, object](body))
        original_meta_contents = {
            "app_label": model._meta.app_label,
            "db_table": model._meta.db_table,
            "unique_together": unique_together,
            "indexes": indexes,
            "constraints": constraints,
            "apps": apps,
        }
        original_meta = type("Meta", (), original_meta_contents)
        original_body["Meta"] = original_meta
        original_body["__module__"] = model.__module__
        type(model._meta.object_name or model.__name__, model.__bases__, original_body)

        replacement_body: dict[str, object] = copy.deepcopy(dict[str, object](body))
        replacement_meta_contents = {
            "app_label": model._meta.app_label,
            "db_table": "new__%s" % strip_quotes(model._meta.db_table),
            "unique_together": unique_together,
            "indexes": indexes,
            "constraints": constraints,
            "apps": apps,
        }
        replacement_meta = type("Meta", (), replacement_meta_contents)
        replacement_body["Meta"] = replacement_meta
        replacement_body["__module__"] = model.__module__
        new_model: type[Model] = type(
            "New%s" % model._meta.object_name, model.__bases__, replacement_body
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

    def delete_model(self, model: type[Model], handle_autom2m: bool = True) -> None:
        if handle_autom2m:
            super().delete_model(model)
            return
        self.execute(self.sql_delete_table % {"table": self.quote_name(model._meta.db_table)})
        for sql in list(self.deferred_sql):
            if isinstance(sql, Statement) and sql.references_table(model._meta.db_table):
                self.deferred_sql.remove(sql)

    def add_field(self, model: type[Model], field: SchemaField) -> None:
        if field.many_to_many and _through_model(field)._meta.auto_created:
            self.create_model(_through_model(field))
        elif isinstance(field, CompositePrimaryKey):
            return
        else:
            # Turso 0.7.0 rewrites `ADD COLUMN ... NULL` as `NOT NULL` in the
            # stored schema. Remaking the table is required even for a plain
            # nullable field so Django's nullability contract remains true.
            self._remake_table(model, create_field=field)

    def remove_field(self, model: type[Model], field: SchemaField) -> None:
        if field.many_to_many:
            if _through_model(field)._meta.auto_created:
                self.delete_model(_through_model(field))
        elif (
            self.connection.features.can_alter_table_drop_column
            and not field.primary_key
            and not field.unique
            and not _db_index(field)
            and not (field.remote_field and _db_constraint(field))
        ):
            super().remove_field(model, field)
        elif field.db_parameters(connection=self.connection)["type"] is not None:
            self._remake_table(model, delete_field=field)

    def _alter_field(
        self,
        model: type[Model],
        old_field: SchemaField,
        new_field: SchemaField,
        old_type: str,
        new_type: str,
        old_db_params: dict[str, str | None],
        new_db_params: dict[str, str | None],
        strict: bool = False,
    ) -> None:
        if (
            _column(old_field) != _column(new_field)
            and _db_index(old_field) == _db_index(new_field)
            and self.column_sql(model, old_field) == self.column_sql(model, new_field)
            and not (
                old_field.remote_field
                and _db_constraint(old_field)
                or new_field.remote_field
                and _db_constraint(new_field)
            )
        ):
            # Django provides this schema method, but its stub omits it.
            self.execute(
                self._rename_field_sql(  # type: ignore[attr-defined]
                    model._meta.db_table, old_field, new_field, new_type
                )
            )
            for sql in self.deferred_sql:
                if isinstance(sql, Statement):
                    sql.rename_column_references(
                        model._meta.db_table, _column(old_field), _column(new_field)
                    )
            return

        self._remake_table(model, alter_fields=[(old_field, new_field)])
        old_collation = old_db_params.get("collation")
        new_collation = new_db_params.get("collation")
        if new_field.unique and (
            old_type != new_type
            or old_collation != new_collation
            or _column(old_field) != _column(new_field)
        ):
            related_models: set[type[Model]] = set()
            opts = new_field.model._meta
            for remote_field in opts.related_objects:
                if remote_field.related_model == model:
                    continue
                if not remote_field.many_to_many:
                    if remote_field.field_name == new_field.name:
                        related_models.add(remote_field.related_model)
                elif new_field.primary_key:
                    # The many_to_many flag identifies this resolved relation type.
                    through = cast(ManyToManyRel, remote_field).through
                    if through is not None and through._meta.auto_created:
                        related_models.add(through)
            if new_field.primary_key:
                for many_to_many in opts.many_to_many:
                    if many_to_many.related_model == model:
                        continue
                    if _through_model(many_to_many)._meta.auto_created:
                        related_models.add(_through_model(many_to_many))
            for related_model in related_models:
                self._remake_table(related_model)

    def _alter_many_to_many(
        self,
        model: type[Model],
        old_field: ManyToManyField[Model, Model],
        new_field: ManyToManyField[Model, Model],
        strict: bool,
    ) -> None:
        if _through_model(old_field)._meta.db_table == _through_model(new_field)._meta.db_table:
            self._remake_table(
                _through_model(old_field),
                alter_fields=[
                    (
                        _model_field(_through_model(old_field), old_field.m2m_reverse_field_name()),
                        _model_field(_through_model(new_field), new_field.m2m_reverse_field_name()),
                    ),
                    (
                        _model_field(_through_model(old_field), old_field.m2m_field_name()),
                        _model_field(_through_model(new_field), new_field.m2m_field_name()),
                    ),
                ],
            )
            return

        self.create_model(_through_model(new_field))
        self.execute(
            "INSERT INTO %s (%s) SELECT %s FROM %s"
            % (
                self.quote_name(_through_model(new_field)._meta.db_table),
                ", ".join(["id", new_field.m2m_column_name(), new_field.m2m_reverse_name()]),
                ", ".join(["id", old_field.m2m_column_name(), old_field.m2m_reverse_name()]),
                self.quote_name(_through_model(old_field)._meta.db_table),
            )
        )
        self.delete_model(_through_model(old_field))

    def add_constraint(self, model: type[Model], constraint: BaseConstraint) -> None:
        if isinstance(constraint, UniqueConstraint) and (
            constraint.condition
            or constraint.contains_expressions
            # UniqueConstraint.include is present in Django, but absent from its stub.
            or constraint.include  # type: ignore[attr-defined]
            or constraint.deferrable
        ):
            super().add_constraint(model, constraint)
        else:
            self._remake_table(model)

    def remove_constraint(self, model: type[Model], constraint: BaseConstraint) -> None:
        if isinstance(constraint, UniqueConstraint) and (
            constraint.condition
            or constraint.contains_expressions
            # UniqueConstraint.include is present in Django, but absent from its stub.
            or constraint.include  # type: ignore[attr-defined]
            or constraint.deferrable
        ):
            super().remove_constraint(model, constraint)
        else:
            self._remake_table(model)

    def _collate_sql(self, collation: str) -> str:
        return "COLLATE " + collation
