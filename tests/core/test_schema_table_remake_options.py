"""Focused table-remake option contracts."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from django.db import connection, models
from django.test.utils import isolate_apps

from django_pyturso.schema import DatabaseSchemaEditor

pytestmark = pytest.mark.core


def _capturing_editor(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[DatabaseSchemaEditor, list[Any], MagicMock]:
    editor = DatabaseSchemaEditor(connection, atomic=False)
    created_models: list[Any] = []
    execute = MagicMock()
    monkeypatch.setattr(editor, "create_model", created_models.append)
    monkeypatch.setattr(editor, "execute", execute)
    monkeypatch.setattr(editor, "delete_model", MagicMock())
    monkeypatch.setattr(editor, "alter_db_table", MagicMock())
    editor.deferred_sql = []
    return editor, created_models, execute


@isolate_apps()
def test_remake_uses_the_effective_default_for_nullable_to_nonnull_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        value = models.IntegerField(null=True)

        class Meta:
            app_label = "schema_remake_options"
            db_table = "remake_default"

    editor, _created_models, execute = _capturing_editor(monkeypatch)
    old_field = Record._meta.get_field("value")
    new_field = models.IntegerField(default=7)
    new_field.set_attributes_from_name("value")

    editor._remake_table(Record, alter_fields=[(old_field, new_field)])

    insert_sql = execute.call_args_list[0].args[0]
    assert 'coalesce("value", 7)' in insert_sql


@isolate_apps()
def test_remake_renames_only_changed_unique_together_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        left = models.CharField(max_length=20)
        right = models.CharField(max_length=20)

        class Meta:
            app_label = "schema_remake_options"
            db_table = "remake_unique_together"
            unique_together = (("left", "right"),)

    editor, created_models, _execute = _capturing_editor(monkeypatch)
    old_field = Record._meta.get_field("left")
    renamed_field = models.CharField(max_length=20)
    renamed_field.set_attributes_from_name("renamed_left")

    editor._remake_table(Record, alter_fields=[(old_field, renamed_field)])

    assert len(created_models) == 1
    assert created_models[0]._meta.unique_together == (("renamed_left", "right"),)


@isolate_apps()
def test_remake_filters_deleted_field_indexes_without_mutating_original_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        removed = models.IntegerField()
        retained = models.IntegerField()

        class Meta:
            app_label = "schema_remake_options"
            db_table = "remake_index_filter"
            indexes = [
                models.Index(fields=["removed"], name="remove_me_idx"),
                models.Index(fields=["retained"], name="retain_me_idx"),
            ]

    editor, created_models, _execute = _capturing_editor(monkeypatch)
    removed_field = Record._meta.get_field("removed")
    retained_field = Record._meta.get_field("retained")

    editor._remake_table(Record, delete_field=removed_field)

    assert len(created_models) == 1
    temporary_model = created_models[0]
    assert [index.name for index in temporary_model._meta.indexes] == [
        "retain_me_idx"
    ]
    assert temporary_model._meta.db_table == "new__remake_index_filter"
    assert retained_field.model is Record
    assert Record._meta.get_field("id").model is Record
