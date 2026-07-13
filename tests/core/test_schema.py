"""Schema editing, migration, and constraint-lifecycle tests."""

from __future__ import annotations

import datetime
import decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from django.db import IntegrityError, NotSupportedError, connection, models, transaction
from django.db.migrations.operations import (
    AddConstraint,
    AddField,
    AlterField,
    CreateModel,
    RemoveField,
    RenameField,
)
from django.db.migrations.state import ProjectState
from django.test.utils import isolate_apps

from django_pyturso.schema import DatabaseSchemaEditor


def _foreign_key_state() -> int:
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _apply_operation(
    state: ProjectState, operation: Any, app_label: str = "schema_tests"
) -> ProjectState:
    next_state = state.clone()
    operation.state_forwards(app_label, next_state)
    with connection.schema_editor() as editor:
        operation.database_forwards(app_label, editor, state, next_state)
    return next_state


@pytest.mark.core
def test_schema_editor_restores_foreign_keys_after_success(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock():
        assert _foreign_key_state() == 1
        with connection.schema_editor():
            assert _foreign_key_state() == 0
        assert _foreign_key_state() == 1


@pytest.mark.core
def test_schema_editor_preserves_an_originally_disabled_state(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF")
        try:
            assert _foreign_key_state() == 0
            with connection.schema_editor():
                assert _foreign_key_state() == 0
            assert _foreign_key_state() == 0
        finally:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys = ON")
            assert _foreign_key_state() == 1


@pytest.mark.core
def test_schema_editor_rejects_entry_inside_atomic(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock():
        with transaction.atomic():
            with pytest.raises(NotSupportedError, match="outside transaction.atomic"):
                with connection.schema_editor():
                    pytest.fail("schema editor entered with foreign keys still enabled")
        assert _foreign_key_state() == 1


@pytest.mark.core
@isolate_apps()
def test_constraint_failure_rolls_back_ddl_and_restores_state(django_db_blocker: Any) -> None:
    class FailedModel(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "schema_tests"
            db_table = "schema_failed_model"

    with django_db_blocker.unblock():
        with patch.object(
            connection, "check_constraints", side_effect=IntegrityError("injected check failure")
        ):
            with pytest.raises(IntegrityError, match="injected check failure"):
                with connection.schema_editor() as editor:
                    editor.create_model(FailedModel)

        assert _foreign_key_state() == 1
        assert "schema_failed_model" not in connection.introspection.table_names()


@pytest.mark.core
def test_migration_operations_remake_tables_and_preserve_data(
    django_db_blocker: Any,
) -> None:
    state = ProjectState()
    create = CreateModel(
        name="Record",
        fields=[
            ("id", models.BigAutoField(primary_key=True)),
            ("name", models.CharField(max_length=20)),
            ("obsolete", models.CharField(db_index=True, default="remove-me", max_length=20)),
        ],
        options={"db_table": "schema_record"},
    )

    with django_db_blocker.unblock():
        state = _apply_operation(state, create)
        try:
            record_model = state.apps.get_model("schema_tests", "Record")
            record_model.objects.create(name="alpha")

            state = _apply_operation(
                state,
                AddField(
                    model_name="record",
                    name="status",
                    field=models.CharField(max_length=12, default="ready"),
                ),
            )
            state = _apply_operation(
                state,
                AlterField(
                    model_name="record",
                    name="name",
                    field=models.CharField(max_length=80),
                ),
            )
            state = _apply_operation(
                state,
                RenameField(model_name="record", old_name="name", new_name="title"),
            )
            state = _apply_operation(
                state,
                RemoveField(model_name="record", name="obsolete"),
            )
            state = _apply_operation(
                state,
                AddConstraint(
                    model_name="record",
                    constraint=models.CheckConstraint(
                        condition=models.Q(status__in=("ready", "done")),
                        name="schema_record_valid_status",
                    ),
                ),
            )

            record_model = state.apps.get_model("schema_tests", "Record")
            assert list(record_model.objects.values_list("title", "status")) == [
                ("alpha", "ready")
            ]
            with pytest.raises(IntegrityError):
                record_model.objects.create(title="bad", status="invalid")

            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, "schema_record")
            assert constraints["schema_record_valid_status"]["check"]
            assert "new__schema_record" not in connection.introspection.table_names()
        finally:
            final_model = state.apps.get_model("schema_tests", "Record")
            with connection.schema_editor() as editor:
                editor.delete_model(final_model)


@pytest.mark.core
def test_table_remake_preserves_named_unique_constraint(
    django_db_blocker: Any,
) -> None:
    state = ProjectState()
    create = CreateModel(
        name="UniqueRecord",
        fields=[
            ("id", models.BigAutoField(primary_key=True)),
            ("title", models.CharField(max_length=80)),
        ],
        options={
            "db_table": "schema_unique_record",
            "constraints": [
                models.UniqueConstraint(
                    fields=["title"], name="schema_unique_record_title_uq"
                )
            ],
        },
    )

    with django_db_blocker.unblock():
        state = _apply_operation(state, create)
        try:
            state = _apply_operation(
                state,
                AddField(
                    model_name="uniquerecord",
                    name="status",
                    field=models.CharField(default="ready", max_length=12),
                ),
            )
            record_model = state.apps.get_model("schema_tests", "UniqueRecord")
            record_model.objects.create(title="alpha")
            with pytest.raises(IntegrityError):
                record_model.objects.create(title="alpha")

            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(
                    cursor, "schema_unique_record"
                )
            assert constraints["schema_unique_record_title_uq"]["unique"]
            assert constraints["schema_unique_record_title_uq"]["columns"] == ["title"]
        finally:
            final_model = state.apps.get_model("schema_tests", "UniqueRecord")
            with connection.schema_editor() as editor:
                editor.delete_model(final_model)


@pytest.mark.core
def test_adding_nullable_field_preserves_nullability(django_db_blocker: Any) -> None:
    state = ProjectState()
    create = CreateModel(
        name="NullableRecord",
        fields=[
            ("id", models.BigAutoField(primary_key=True)),
            ("title", models.CharField(max_length=80)),
        ],
        options={"db_table": "schema_nullable_record"},
    )

    with django_db_blocker.unblock():
        state = _apply_operation(state, create)
        try:
            state = _apply_operation(
                state,
                AddField(
                    model_name="nullablerecord",
                    name="rank",
                    field=models.IntegerField(null=True),
                ),
            )
            with connection.cursor() as cursor:
                description = {
                    field.name: field
                    for field in connection.introspection.get_table_description(
                        cursor, "schema_nullable_record"
                    )
                }
            assert description["rank"].null_ok
        finally:
            final_model = state.apps.get_model("schema_tests", "NullableRecord")
            with connection.schema_editor() as editor:
                editor.delete_model(final_model)


@pytest.mark.core
def test_create_model_migration_runs_backward(django_db_blocker: Any) -> None:
    before = ProjectState()
    operation = CreateModel(
        name="Temporary",
        fields=[("id", models.BigAutoField(primary_key=True))],
        options={"db_table": "schema_temporary"},
    )
    after = before.clone()
    operation.state_forwards("schema_tests", after)

    with django_db_blocker.unblock():
        with connection.schema_editor() as editor:
            operation.database_forwards("schema_tests", editor, before, after)
        assert "schema_temporary" in connection.introspection.table_names()
        with connection.schema_editor() as editor:
            operation.database_backwards("schema_tests", editor, after, before)
        assert "schema_temporary" not in connection.introspection.table_names()


class _LifecycleConnection:
    def __init__(self) -> None:
        self.features = SimpleNamespace(can_rollback_ddl=True)
        self.alias = "default"
        self.in_atomic_block = False
        self.checked = 0
        self.disposed = False

    def ensure_connection(self) -> None:
        pass

    def check_constraints(self) -> None:
        self.checked += 1

    def _force_close(self) -> None:
        self.disposed = True


def test_restoration_failure_preserves_primary_exception_and_disposes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = _LifecycleConnection()
    editor = DatabaseSchemaEditor(wrapper, atomic=False)  # type: ignore[arg-type]
    monkeypatch.setattr(editor, "_foreign_key_state", lambda: 1)

    def set_state(enabled: bool) -> None:
        if enabled:
            raise RuntimeError("restore failed")

    monkeypatch.setattr(editor, "_set_foreign_key_state", set_state)

    with pytest.raises(ValueError, match="primary") as raised:
        with editor:
            raise ValueError("primary")

    assert isinstance(raised.value.__cause__, RuntimeError)
    assert wrapper.disposed


def test_unreadable_initial_state_disposes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = _LifecycleConnection()
    editor = DatabaseSchemaEditor(wrapper, atomic=False)  # type: ignore[arg-type]

    def unreadable_state() -> int:
        raise RuntimeError("state unreadable")

    monkeypatch.setattr(editor, "_foreign_key_state", unreadable_state)

    with pytest.raises(RuntimeError, match="state unreadable"):
        editor.__enter__()
    assert wrapper.disposed


@pytest.mark.parametrize(
    ("value", "sql"),
    [
        (None, "NULL"),
        (True, "1"),
        (decimal.Decimal("12.50"), "12.50"),
        ("O'Reilly", "'O''Reilly'"),
        (b"\x00\xff", "X'00ff'"),
        (datetime.date(2026, 7, 13), "'2026-07-13'"),
    ],
)
def test_quote_value_uses_local_turso_literals(value: Any, sql: str) -> None:
    editor = object.__new__(DatabaseSchemaEditor)
    assert editor.quote_value(value) == sql
