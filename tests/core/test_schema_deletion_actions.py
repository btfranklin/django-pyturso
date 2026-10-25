"""Preserve database deletion actions through schema migrations."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Never

import pytest
from django.db import IntegrityError, models, transaction
from django.db.migrations.operations import AddField, AlterField, CreateModel
from django.db.migrations.operations.base import Operation
from django.db.migrations.state import ProjectState
from django.db.models.deletion import Collector, DatabaseOnDelete
from pytest_django.plugin import DjangoDbBlocker

from django_pyturso.base import DatabaseWrapper
from tests.core.transactions.test_state_machine import registered_wrapper

type OnDelete = (
    DatabaseOnDelete
    | Callable[[Collector, models.Field[Never, object], models.QuerySet[models.Model], str], None]
)

pytestmark = pytest.mark.core
APP_LABEL = "deletion_tests"
MODES = [
    {"journal_mode": "WAL"},
    {"journal_mode": "MVCC", "transaction_mode": "CONCURRENT"},
]
ACTIONS = [
    pytest.param(models.DB_CASCADE, "CASCADE", id="cascade"),
    pytest.param(models.DB_SET_NULL, "SET NULL", id="set-null"),
    pytest.param(models.DB_SET_DEFAULT, "SET DEFAULT", id="set-default"),
]


def _foreign_key(
    action: OnDelete, *, db_default: bool = False
) -> models.ForeignKey[int | models.Model | None, models.Model | None]:
    if db_default:
        return models.ForeignKey(f"{APP_LABEL}.Parent", action, null=True, db_default=0)
    return models.ForeignKey(f"{APP_LABEL}.Parent", action, null=True)


def _apply(wrapper: DatabaseWrapper, state: ProjectState, operation: Operation) -> ProjectState:
    after = state.clone()
    operation.state_forwards(APP_LABEL, after)
    with wrapper.schema_editor() as editor:
        operation.database_forwards(APP_LABEL, editor, state, after)
    return after


def _reverse(
    wrapper: DatabaseWrapper,
    operation: Operation,
    before: ProjectState,
    after: ProjectState,
) -> None:
    with wrapper.schema_editor() as editor:
        operation.database_backwards(APP_LABEL, editor, after, before)


def _create(
    wrapper: DatabaseWrapper, field: models.Field[Never, object] | None = None
) -> ProjectState:
    state = _apply(
        wrapper,
        ProjectState(),
        CreateModel(
            name="Parent",
            fields=[("id", models.IntegerField(primary_key=True))],
            options={"db_table": "deletion_parent"},
        ),
    )
    fields: list[tuple[str, models.Field[Never, object]]] = [
        ("id", models.IntegerField(primary_key=True)),
        ("value", models.IntegerField(default=7)),
    ]
    if field is not None:
        fields.append(("parent", field))
    state = _apply(
        wrapper,
        state,
        CreateModel(name="Child", fields=fields, options={"db_table": "deletion_child"}),
    )
    parent = state.apps.get_model(APP_LABEL, "Parent")
    parent.objects.using(wrapper.alias).create(id=0)
    return state


def _assert_action(wrapper: DatabaseWrapper, action_sql: str) -> None:
    with wrapper.cursor() as cursor:
        cursor.execute("PRAGMA foreign_key_list(deletion_child)")
        foreign_keys = cursor.fetchall()
        assert len(foreign_keys) == 1
        assert foreign_keys[0][2:5] == ("deletion_parent", "parent_id", "id")
        assert foreign_keys[0][6] == action_sql
        cursor.execute("PRAGMA foreign_key_check")
        assert cursor.fetchall() == []


def _child_rows(wrapper: DatabaseWrapper, state: ProjectState) -> list[tuple[object, ...]]:
    child = state.apps.get_model(APP_LABEL, "Child")
    return list(
        child.objects.using(wrapper.alias).order_by("id").values_list("id", "parent_id", "value")
    )


def _assert_delete(
    wrapper: DatabaseWrapper, state: ProjectState, action_sql: str, row_id: int
) -> None:
    _assert_action(wrapper, action_sql)
    parent = state.apps.get_model(APP_LABEL, "Parent")
    child = state.apps.get_model(APP_LABEL, "Child")
    parents = parent.objects.using(wrapper.alias)
    children = child.objects.using(wrapper.alias)
    previous = list(children.order_by("id").values_list("id", "parent_id", "value"))
    parents.create(id=row_id)
    children.create(id=row_id, parent_id=row_id)
    with wrapper.cursor() as cursor:
        cursor.execute("DELETE FROM deletion_parent WHERE id = %s", [row_id])
    assert not parents.filter(id=row_id).exists()
    assert parents.filter(id=0).exists()
    expected = previous
    if action_sql != "CASCADE":
        expected += [(row_id, None if action_sql == "SET NULL" else 0, 7)]
    assert list(children.order_by("id").values_list("id", "parent_id", "value")) == expected
    _assert_action(wrapper, action_sql)


def _assert_python_cascade(wrapper: DatabaseWrapper, state: ProjectState) -> None:
    _assert_action(wrapper, "NO ACTION")
    parent = state.apps.get_model(APP_LABEL, "Parent")
    child = state.apps.get_model(APP_LABEL, "Child")
    parents = parent.objects.using(wrapper.alias)
    children = child.objects.using(wrapper.alias)
    previous = list(children.order_by("id").values_list("id", "parent_id", "value"))
    parents.create(id=20)
    children.create(id=20, parent_id=20)
    with pytest.raises(IntegrityError), transaction.atomic(using=wrapper.alias):
        with wrapper.cursor() as cursor:
            cursor.execute("DELETE FROM deletion_parent WHERE id = 20")
    assert parents.filter(id=20).exists()
    assert children.filter(id=20, parent_id=20).exists()
    parents.get(id=20).delete(using=wrapper.alias)
    assert not parents.filter(id=20).exists()
    assert list(children.order_by("id").values_list("id", "parent_id", "value")) == previous
    _assert_action(wrapper, "NO ACTION")


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize(("action", "action_sql"), ACTIONS)
def test_create_remake_and_reverse_action_migrations(
    tmp_path: Path,
    django_db_blocker: DjangoDbBlocker,
    options: dict[str, str],
    action: OnDelete,
    action_sql: str,
) -> None:
    db_default = action_sql == "SET DEFAULT"
    with (
        django_db_blocker.unblock(),
        registered_wrapper(NAME=tmp_path / "deletion.db", OPTIONS=options) as wrapper,
    ):
        state = _create(wrapper, _foreign_key(action, db_default=db_default))
        child = state.apps.get_model(APP_LABEL, "Child")
        child.objects.using(wrapper.alias).create(id=1, parent_id=None)
        child.objects.using(wrapper.alias).create(id=2, parent_id=0)
        _assert_delete(wrapper, state, action_sql, 10)

        remake = AlterField("child", "value", models.BigIntegerField(default=7))
        before_remake = state
        rows = _child_rows(wrapper, state)
        state = _apply(wrapper, state, remake)
        assert _child_rows(wrapper, state) == rows
        _assert_delete(wrapper, state, action_sql, 11)
        rows = _child_rows(wrapper, state)
        _reverse(wrapper, remake, before_remake, state)
        state = before_remake
        assert _child_rows(wrapper, state) == rows
        _assert_delete(wrapper, state, action_sql, 12)

        change_action = AlterField(
            "child", "parent", _foreign_key(models.CASCADE, db_default=db_default)
        )
        before_action = state
        rows = _child_rows(wrapper, state)
        state = _apply(wrapper, state, change_action)
        assert _child_rows(wrapper, state) == rows
        _assert_python_cascade(wrapper, state)
        _reverse(wrapper, change_action, before_action, state)
        assert _child_rows(wrapper, before_action) == rows
        _assert_delete(wrapper, before_action, action_sql, 13)


@pytest.mark.parametrize("options", MODES, ids=["wal", "mvcc"])
@pytest.mark.parametrize(("action", "action_sql"), ACTIONS)
def test_add_foreign_key_and_reverse_migration(
    tmp_path: Path,
    django_db_blocker: DjangoDbBlocker,
    options: dict[str, str],
    action: OnDelete,
    action_sql: str,
) -> None:
    with (
        django_db_blocker.unblock(),
        registered_wrapper(NAME=tmp_path / "add_deletion.db", OPTIONS=options) as wrapper,
    ):
        before = _create(wrapper)
        child = before.apps.get_model(APP_LABEL, "Child")
        child.objects.using(wrapper.alias).create(id=1)
        operation = AddField(
            "child", "parent", _foreign_key(action, db_default=action_sql == "SET DEFAULT")
        )
        after = _apply(wrapper, before, operation)
        child = after.apps.get_model(APP_LABEL, "Child")
        assert _child_rows(wrapper, after) == [(1, 0 if action_sql == "SET DEFAULT" else None, 7)]
        _assert_delete(wrapper, after, action_sql, 10)
        _reverse(wrapper, operation, before, after)
        child = before.apps.get_model(APP_LABEL, "Child")
        expected_ids = [1] if action_sql == "CASCADE" else [1, 10]
        assert list(
            child.objects.using(wrapper.alias).order_by("id").values_list("id", "value")
        ) == [(row_id, 7) for row_id in expected_ids]
        with wrapper.cursor() as cursor:
            cursor.execute("PRAGMA foreign_key_list(deletion_child)")
            assert cursor.fetchall() == []
            cursor.execute("PRAGMA foreign_key_check")
            assert cursor.fetchall() == []
