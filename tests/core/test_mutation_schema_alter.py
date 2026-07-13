"""Focused mutation tests for schema alteration dispatch contracts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from django.db import models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.models.functions import Lower

from tests.core.test_schema_branches import (
    _editor,
    _hashable,
    _many_to_many_field,
)

pytestmark = pytest.mark.core


def _field(*, column: str, remote_field: object | None = None) -> Any:
    return SimpleNamespace(
        column=column,
        remote_field=remote_field,
        db_constraint=remote_field is not None,
        unique=False,
        primary_key=False,
    )


def test_equivalent_column_rename_uses_exact_fast_path_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor()
    model = SimpleNamespace(_meta=SimpleNamespace(db_table="records"))
    old_field = _field(column="old_code")
    new_field = _field(column="new_code")
    rename = MagicMock(return_value="RENAME COLUMN")
    execute = MagicMock()
    remake = MagicMock()
    monkeypatch.setattr(editor, "column_sql", lambda candidate, field: ("text", []))
    monkeypatch.setattr(editor, "_rename_field_sql", rename)
    monkeypatch.setattr(editor, "execute", execute)
    monkeypatch.setattr(editor, "_remake_table", remake)

    editor._alter_field(
        model,
        old_field,
        new_field,
        "varchar(20)",
        "varchar(40)",
        {},
        {},
    )

    rename.assert_called_once_with("records", old_field, new_field, "varchar(40)")
    execute.assert_called_once_with("RENAME COLUMN")
    remake.assert_not_called()


def test_constrained_relation_rename_requires_table_remake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor()
    model = SimpleNamespace(_meta=SimpleNamespace(db_table="records"))
    old_field = _field(column="old_parent_id", remote_field=object())
    new_field = _field(column="new_parent_id")
    rename = MagicMock()
    remake = MagicMock()
    monkeypatch.setattr(editor, "column_sql", lambda candidate, field: ("integer", []))
    monkeypatch.setattr(editor, "_rename_field_sql", rename)
    monkeypatch.setattr(editor, "_remake_table", remake)

    editor._alter_field(model, old_field, new_field, "integer", "integer", {}, {})

    remake.assert_called_once_with(model, alter_fields=[(old_field, new_field)])
    rename.assert_not_called()


def _related_unique_fields(*, unique: bool) -> tuple[Any, Any, Any, Any]:
    model = _hashable(name="owner")
    related = _hashable(name="related")
    opts = SimpleNamespace(
        related_objects=[
            SimpleNamespace(
                related_model=related,
                many_to_many=False,
                field_name="code",
            )
        ],
        many_to_many=[],
    )
    old_field = _field(column="code")
    new_field = SimpleNamespace(
        column="code",
        remote_field=None,
        db_constraint=False,
        unique=unique,
        primary_key=False,
        model=SimpleNamespace(_meta=opts),
        name="code",
    )
    return model, related, old_field, new_field


@pytest.mark.parametrize(
    ("old_params", "new_params"),
    [({"collation": "NOCASE"}, {}), ({}, {"collation": "NOCASE"})],
)
def test_unique_collation_change_remakes_related_table(
    monkeypatch: pytest.MonkeyPatch,
    old_params: dict[str, str],
    new_params: dict[str, str],
) -> None:
    editor = _editor()
    model, related, old_field, new_field = _related_unique_fields(unique=True)
    remake = MagicMock()
    monkeypatch.setattr(editor, "_remake_table", remake)

    editor._alter_field(
        model,
        old_field,
        new_field,
        "varchar(20)",
        "varchar(20)",
        old_params,
        new_params,
    )

    assert remake.call_args_list == [
        call(model, alter_fields=[(old_field, new_field)]),
        call(related),
    ]


def test_nonunique_type_change_does_not_remake_related_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor()
    model, _related, old_field, new_field = _related_unique_fields(unique=False)
    remake = MagicMock()
    monkeypatch.setattr(editor, "_remake_table", remake)

    editor._alter_field(
        model,
        old_field,
        new_field,
        "varchar(20)",
        "varchar(40)",
        {},
        {},
    )

    remake.assert_called_once_with(model, alter_fields=[(old_field, new_field)])


def test_same_table_many_to_many_remake_receives_exact_field_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor()
    remake = MagicMock()
    monkeypatch.setattr(editor, "_remake_table", remake)
    old_local, old_reverse = object(), object()
    new_local, new_reverse = object(), object()
    old_fields = {"local": old_local, "reverse": old_reverse}
    new_fields = {"local": new_local, "reverse": new_reverse}
    old_through = SimpleNamespace(
        _meta=SimpleNamespace(
            db_table="join_table",
            get_field=lambda name: old_fields[name],
        )
    )
    new_through = SimpleNamespace(
        _meta=SimpleNamespace(
            db_table="join_table",
            get_field=lambda name: new_fields[name],
        )
    )

    editor._alter_many_to_many(
        SimpleNamespace(),
        _many_to_many_field(old_through, "local", "reverse"),
        _many_to_many_field(new_through, "local", "reverse"),
        strict=False,
    )

    remake.assert_called_once_with(
        old_through,
        alter_fields=[
            (old_reverse, new_reverse),
            (old_local, new_local),
        ],
    )


def test_different_table_many_to_many_uses_exact_copy_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor()
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
        _many_to_many_field(old_through, "old_local", "old_reverse"),
        _many_to_many_field(new_through, "new_local", "new_reverse"),
        strict=False,
    )

    create.assert_called_once_with(new_through)
    execute.assert_called_once_with(
        'INSERT INTO "new_join" (id, new_local_id, new_reverse_id) '
        'SELECT id, old_local_id, old_reverse_id FROM "old_join"'
    )
    delete.assert_called_once_with(old_through)


@pytest.mark.parametrize(
    "constraint",
    [
        models.UniqueConstraint(Lower("value"), name="lower_value_uq"),
        models.UniqueConstraint(
            fields=["value"],
            include=["extra"],
            name="included_value_uq",
        ),
        models.UniqueConstraint(
            fields=["value"],
            deferrable=models.Deferrable.DEFERRED,
            name="deferred_value_uq",
        ),
    ],
    ids=["expression", "include", "deferrable"],
)
def test_specialized_unique_constraints_delegate_to_base(
    monkeypatch: pytest.MonkeyPatch,
    constraint: Any,
) -> None:
    editor = _editor()
    model = SimpleNamespace()
    remake = MagicMock()
    monkeypatch.setattr(editor, "_remake_table", remake)

    with (
        patch.object(BaseDatabaseSchemaEditor, "add_constraint") as parent_add,
        patch.object(BaseDatabaseSchemaEditor, "remove_constraint") as parent_remove,
    ):
        editor.add_constraint(model, constraint)
        editor.remove_constraint(model, constraint)

    parent_add.assert_called_once_with(model, constraint)
    parent_remove.assert_called_once_with(model, constraint)
    remake.assert_not_called()
