"""Focused branch contracts for the schema editor."""

from __future__ import annotations

import datetime
import math
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.db import NotSupportedError, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.ddl_references import Statement, Table

from django_pyturso.schema import DatabaseSchemaEditor
from tests.schema_support import (
    SchemaConnection,
    hashable_namespace,
    many_to_many_field,
    schema_editor,
)

pytestmark = pytest.mark.core


@pytest.mark.parametrize("row", [None, (2,)])
def test_foreign_key_state_rejects_missing_or_invalid_values(
    row: tuple[int] | None,
) -> None:
    editor = schema_editor(SchemaConnection(row))
    with pytest.raises(NotSupportedError, match="valid foreign-key state"):
        editor._foreign_key_state()


@pytest.mark.parametrize(
    ("enabled", "reported", "message"),
    [(True, 0, "enable"), (False, 1, "disable")],
)
def test_set_foreign_key_state_requires_readback(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    reported: int,
    message: str,
) -> None:
    wrapper = SchemaConnection()
    editor = schema_editor(wrapper)
    monkeypatch.setattr(editor, "_foreign_key_state", lambda: reported)
    with pytest.raises(NotSupportedError, match=message):
        editor._set_foreign_key_state(enabled)
    assert wrapper.cursor_instance.commands == [
        f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}"
    ]


def test_disposal_uses_required_force_close_and_restore_none_is_a_noop() -> None:
    wrapper = SchemaConnection()
    editor = schema_editor(wrapper)
    editor._dispose_unrestorable_connection()
    editor._original_foreign_keys = None
    editor._restore_foreign_key_state()
    assert wrapper.force_closed == 1


def test_entry_preserves_primary_when_disable_and_restore_both_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = schema_editor()
    monkeypatch.setattr(editor, "_foreign_key_state", lambda: 1)

    def fail_state(enabled: bool) -> None:
        if enabled:
            raise RuntimeError("restore")
        raise ValueError("disable")

    monkeypatch.setattr(editor, "_set_foreign_key_state", fail_state)
    with pytest.raises(ValueError, match="disable") as raised:
        editor.__enter__()
    assert isinstance(raised.value.__cause__, RuntimeError)


def test_exit_reraises_atomic_exit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = schema_editor()
    editor._original_foreign_keys = None
    failure = RuntimeError("atomic exit")
    with (
        patch.object(BaseDatabaseSchemaEditor, "__exit__", side_effect=failure),
        pytest.raises(RuntimeError, match="atomic exit"),
    ):
        editor.__exit__(ValueError, ValueError("body"), None)


def test_exit_raises_lone_restoration_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = schema_editor()
    monkeypatch.setattr(
        editor,
        "_restore_foreign_key_state",
        MagicMock(side_effect=RuntimeError("restore only")),
    )
    with (
        patch.object(BaseDatabaseSchemaEditor, "__exit__", return_value=None),
        pytest.raises(RuntimeError, match="restore only"),
    ):
        editor.__exit__(None, None, None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (False, "0"),
        (17, "17"),
        (1.25, "1.25"),
        (bytearray(b"ab"), "X'6162'"),
        (memoryview(b"cd"), "X'6364'"),
        (datetime.datetime(2026, 7, 13, 12, 30, 1), "'2026-07-13 12:30:01'"),
        (datetime.time(12, 30, 1, 4000), "'12:30:01.004000'"),
    ],
)
def test_quote_value_additional_supported_literals(value: Any, expected: str) -> None:
    editor = object.__new__(DatabaseSchemaEditor)
    assert editor.prepare_default(value) == expected


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_quote_value_rejects_non_finite_floats(value: float) -> None:
    editor = object.__new__(DatabaseSchemaEditor)
    with pytest.raises(ValueError, match="Non-finite"):
        editor.quote_value(value)


def test_quote_value_rejects_unknown_types() -> None:
    editor = object.__new__(DatabaseSchemaEditor)
    with pytest.raises(ValueError, match="object"):
        editor.quote_value(object())


def test_delete_model_filters_only_matching_deferred_statements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = schema_editor()
    monkeypatch.setattr(editor, "execute", MagicMock())
    monkeypatch.setattr(editor, "quote_name", lambda name: f'"{name}"')
    matching = Statement("%(table)s", table=Table("branch_table", lambda value: value))
    other = Statement("%(table)s", table=Table("other_table", lambda value: value))
    marker = "literal deferred SQL"
    editor.deferred_sql = [matching, other, marker]
    model = SimpleNamespace(_meta=SimpleNamespace(db_table="branch_table"))

    editor.delete_model(model, handle_autom2m=False)

    assert editor.deferred_sql == [other, marker]


def test_delete_model_default_delegates_to_base() -> None:
    editor = schema_editor()
    model = SimpleNamespace()
    with patch.object(BaseDatabaseSchemaEditor, "delete_model") as parent:
        editor.delete_model(model)
    parent.assert_called_once_with(model)


def test_add_field_dispatches_many_to_many_composite_and_remake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = schema_editor()
    created = MagicMock()
    remade = MagicMock()
    monkeypatch.setattr(editor, "create_model", created)
    monkeypatch.setattr(editor, "_remake_table", remade)
    through = SimpleNamespace(_meta=SimpleNamespace(auto_created=True))
    many = SimpleNamespace(
        many_to_many=True, remote_field=SimpleNamespace(through=through)
    )
    model = SimpleNamespace()

    editor.add_field(model, many)
    editor.add_field(model, models.CompositePrimaryKey("left", "right"))
    ordinary = SimpleNamespace(many_to_many=False)
    editor.add_field(model, ordinary)

    created.assert_called_once_with(through)
    remade.assert_called_once_with(model, create_field=ordinary)


def test_remove_field_dispatches_all_supported_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = schema_editor()
    features: Any = editor.connection.features
    features.can_alter_table_drop_column = True
    deleted = MagicMock()
    remade = MagicMock()
    monkeypatch.setattr(editor, "delete_model", deleted)
    monkeypatch.setattr(editor, "_remake_table", remade)
    model = SimpleNamespace()
    auto_through = SimpleNamespace(_meta=SimpleNamespace(auto_created=True))
    manual_through = SimpleNamespace(_meta=SimpleNamespace(auto_created=False))
    auto_m2m = SimpleNamespace(
        many_to_many=True, remote_field=SimpleNamespace(through=auto_through)
    )
    manual_m2m = SimpleNamespace(
        many_to_many=True, remote_field=SimpleNamespace(through=manual_through)
    )
    direct = SimpleNamespace(
        many_to_many=False,
        primary_key=False,
        unique=False,
        db_index=False,
        remote_field=None,
    )
    remake = SimpleNamespace(
        many_to_many=False,
        primary_key=False,
        unique=True,
        db_index=False,
        remote_field=None,
        db_parameters=lambda **_kwargs: {"type": "varchar"},
    )
    virtual = SimpleNamespace(
        many_to_many=False,
        primary_key=False,
        unique=True,
        db_index=False,
        remote_field=None,
        db_parameters=lambda **_kwargs: {"type": None},
    )

    editor.remove_field(model, auto_m2m)
    editor.remove_field(model, manual_m2m)
    with patch.object(BaseDatabaseSchemaEditor, "remove_field") as parent:
        editor.remove_field(model, direct)
    editor.remove_field(model, remake)
    editor.remove_field(model, virtual)

    deleted.assert_called_once_with(auto_through)
    parent.assert_called_once_with(model, direct)
    remade.assert_called_once_with(model, delete_field=remake)


def test_alter_unique_field_remakes_matching_related_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = schema_editor()
    remade = MagicMock()
    monkeypatch.setattr(editor, "_remake_table", remade)
    related = hashable_namespace(name="related")
    model = SimpleNamespace(name="owner")
    opts = SimpleNamespace(
        related_objects=[
            SimpleNamespace(related_model=model),
            SimpleNamespace(
                related_model=related,
                many_to_many=False,
                field_name="code",
            ),
            SimpleNamespace(
                related_model=SimpleNamespace(name="ignored"),
                many_to_many=False,
                field_name="other",
            ),
        ],
        many_to_many=[],
    )
    new_field = SimpleNamespace(
        column="code",
        unique=True,
        primary_key=False,
        model=SimpleNamespace(_meta=opts),
        name="code",
        remote_field=None,
        db_constraint=False,
    )
    old_field = SimpleNamespace(
        column="code",
        remote_field=None,
        db_constraint=False,
    )

    editor._alter_field(model, old_field, new_field, "varchar(10)", "varchar(20)", {}, {})

    assert [call.args[0] for call in remade.call_args_list] == [model, related]


def test_alter_primary_key_remakes_auto_many_to_many_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = schema_editor()
    remade = MagicMock()
    monkeypatch.setattr(editor, "_remake_table", remade)
    model = SimpleNamespace(name="owner")
    through_from_relation = hashable_namespace(name="through relation")
    through_from_field = hashable_namespace(name="through field")
    relation = SimpleNamespace(
        related_model=SimpleNamespace(name="related"),
        many_to_many=True,
        through=SimpleNamespace(_meta=SimpleNamespace(auto_created=True)),
    )
    relation.through = through_from_relation
    relation.through._meta = SimpleNamespace(auto_created=True)
    self_m2m = SimpleNamespace(related_model=model)
    other_m2m = SimpleNamespace(
        related_model=SimpleNamespace(name="other"),
        remote_field=SimpleNamespace(
            through=through_from_field,
        ),
    )
    other_m2m.remote_field.through._meta = SimpleNamespace(auto_created=True)
    manual_m2m = SimpleNamespace(
        related_model=SimpleNamespace(name="manual"),
        remote_field=SimpleNamespace(
            through=SimpleNamespace(_meta=SimpleNamespace(auto_created=False))
        ),
    )
    manual_relation = SimpleNamespace(
        related_model=SimpleNamespace(name="manual relation"),
        many_to_many=True,
        through=SimpleNamespace(_meta=SimpleNamespace(auto_created=False)),
    )
    opts = SimpleNamespace(
        related_objects=[relation, manual_relation],
        many_to_many=[self_m2m, other_m2m, manual_m2m],
    )
    new_field = SimpleNamespace(
        column="id",
        unique=True,
        primary_key=True,
        model=SimpleNamespace(_meta=opts),
        name="id",
        remote_field=None,
        db_constraint=False,
    )
    old_field = SimpleNamespace(column="id", remote_field=None, db_constraint=False)

    editor._alter_field(model, old_field, new_field, "integer", "bigint", {}, {})

    remade_models = {call.args[0] for call in remade.call_args_list[1:]}
    assert remade_models == {through_from_relation, through_from_field}


def test_alter_many_to_many_same_table_uses_remake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = schema_editor()
    remade = MagicMock()
    monkeypatch.setattr(editor, "_remake_table", remade)
    old_fields = {"left": object(), "right": object()}
    new_fields = {"left": object(), "right": object()}
    old_through = SimpleNamespace(
        _meta=SimpleNamespace(
            db_table="same_table", get_field=lambda name: old_fields[name]
        )
    )
    new_through = SimpleNamespace(
        _meta=SimpleNamespace(
            db_table="same_table", get_field=lambda name: new_fields[name]
        )
    )

    editor._alter_many_to_many(
        SimpleNamespace(),
        many_to_many_field(old_through, "left", "right"),
        many_to_many_field(new_through, "left", "right"),
        strict=False,
    )

    remade.assert_called_once()


def test_alter_many_to_many_different_table_copies_and_drops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = schema_editor()
    old_through = SimpleNamespace(_meta=SimpleNamespace(db_table="old_join"))
    new_through = SimpleNamespace(_meta=SimpleNamespace(db_table="new_join"))
    create = MagicMock()
    execute = MagicMock()
    delete = MagicMock()
    monkeypatch.setattr(editor, "create_model", create)
    monkeypatch.setattr(editor, "execute", execute)
    monkeypatch.setattr(editor, "delete_model", delete)
    monkeypatch.setattr(editor, "quote_name", lambda name: f'"{name}"')

    editor._alter_many_to_many(
        SimpleNamespace(),
        many_to_many_field(old_through, "old_left", "old_right"),
        many_to_many_field(new_through, "new_left", "new_right"),
        strict=False,
    )

    create.assert_called_once_with(new_through)
    assert 'INSERT INTO "new_join"' in execute.call_args.args[0]
    assert 'FROM "old_join"' in execute.call_args.args[0]
    delete.assert_called_once_with(old_through)


def test_constraint_dispatch_and_collation(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = schema_editor()
    model = SimpleNamespace()
    conditional = models.UniqueConstraint(
        fields=["value"], condition=models.Q(value__gt=0), name="positive_value_uq"
    )
    ordinary = models.UniqueConstraint(fields=["value"], name="value_uq")
    remade = MagicMock()
    monkeypatch.setattr(editor, "_remake_table", remade)

    with (
        patch.object(BaseDatabaseSchemaEditor, "add_constraint") as parent_add,
        patch.object(BaseDatabaseSchemaEditor, "remove_constraint") as parent_remove,
    ):
        editor.add_constraint(model, conditional)
        editor.remove_constraint(model, conditional)
    editor.add_constraint(model, ordinary)
    editor.remove_constraint(model, ordinary)

    parent_add.assert_called_once_with(model, conditional)
    parent_remove.assert_called_once_with(model, conditional)
    assert remade.call_count == 2
    assert editor._collate_sql("NOCASE") == "COLLATE NOCASE"
