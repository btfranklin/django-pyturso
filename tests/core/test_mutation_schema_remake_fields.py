"""Mutation-focused contracts for fields handled by table remakes."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from django.db import connection, models
from django.test.utils import isolate_apps

from django_pyturso.schema import DatabaseSchemaEditor

pytestmark = pytest.mark.core


def _editor(monkeypatch: pytest.MonkeyPatch) -> DatabaseSchemaEditor:
    editor = DatabaseSchemaEditor(connection, atomic=False)
    monkeypatch.setattr(editor, "create_model", MagicMock())
    monkeypatch.setattr(editor, "execute", MagicMock())
    monkeypatch.setattr(editor, "delete_model", MagicMock())
    monkeypatch.setattr(editor, "alter_db_table", MagicMock())
    editor.deferred_sql = []
    return editor


def _created_model(editor: DatabaseSchemaEditor) -> Any:
    create_model = editor.create_model
    assert isinstance(create_model, MagicMock)
    return create_model.call_args.args[0]


def _first_executed_sql(editor: DatabaseSchemaEditor) -> str:
    execute: Any = editor.execute
    return str(execute.call_args_list[0].args[0])


@isolate_apps()
def test_remake_preserves_composite_primary_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        tenant_id = models.IntegerField()
        record_id = models.IntegerField()
        pk = models.CompositePrimaryKey("tenant_id", "record_id")

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_composite"

    editor = _editor(monkeypatch)

    editor._remake_table(Record)

    remade = _created_model(editor)
    assert isinstance(remade._meta.pk, models.CompositePrimaryKey)
    assert remade._meta.pk.name == "pk"
    assert tuple(remade._meta.pk.field_names) == ("tenant_id", "record_id")


@isolate_apps()
def test_remake_new_primary_key_replaces_automatic_key_without_mutating_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_new_primary"

    original_pk = Record._meta.pk
    replacement = models.IntegerField(default=7, primary_key=True)
    replacement.set_attributes_from_name("replacement_id")
    editor = _editor(monkeypatch)

    editor._remake_table(Record, create_field=replacement)

    remade = _created_model(editor)
    assert remade._meta.pk.name == "replacement_id"
    assert [field.name for field in remade._meta.local_fields] == [
        "value",
        "replacement_id",
    ]
    assert original_pk.primary_key is True
    assert original_pk.model is Record


@isolate_apps()
def test_remake_new_primary_key_demotes_explicit_source_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        old_key = models.IntegerField(primary_key=True)
        value = models.IntegerField()

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_explicit_primary"

    original_pk = Record._meta.pk
    replacement = models.IntegerField(default=7, primary_key=True)
    replacement.set_attributes_from_name("replacement_id")
    editor = _editor(monkeypatch)

    editor._remake_table(Record, create_field=replacement)

    remade = _created_model(editor)
    assert remade._meta.pk.name == "replacement_id"
    assert remade._meta.get_field("old_key").primary_key is False
    assert remade._meta.get_field("old_key").column == "old_key"
    assert original_pk.primary_key is True
    assert original_pk.model is Record


@isolate_apps()
def test_remake_altered_primary_key_remains_the_primary_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        key = models.IntegerField(primary_key=True)
        value = models.IntegerField()

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_altered_primary"

    old_field = Record._meta.get_field("key")
    new_field = models.BigIntegerField(primary_key=True)
    new_field.set_attributes_from_name("key")
    new_field.model = Record
    editor = _editor(monkeypatch)

    editor._remake_table(Record, alter_fields=[(old_field, new_field)])

    remade = _created_model(editor)
    assert remade._meta.pk.name == "key"
    assert isinstance(remade._meta.pk, models.BigIntegerField)
    assert old_field.primary_key is True
    assert old_field.model is Record


@isolate_apps()
def test_remake_altering_another_field_to_primary_key_demotes_the_old_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        old_key = models.IntegerField(primary_key=True)
        replacement = models.IntegerField()

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_altered_replacement_primary"

    old_field = Record._meta.get_field("replacement")
    new_field = models.BigIntegerField(primary_key=True)
    new_field.set_attributes_from_name("replacement")
    new_field.model = Record
    original_pk = Record._meta.pk
    editor = _editor(monkeypatch)

    editor._remake_table(Record, alter_fields=[(old_field, new_field)])

    remade = _created_model(editor)
    assert remade._meta.pk.name == "replacement"
    assert isinstance(remade._meta.pk, models.BigIntegerField)
    assert remade._meta.get_field("old_key").primary_key is False
    assert original_pk.primary_key is True
    assert original_pk.model is Record


@isolate_apps()
def test_remake_renamed_field_replaces_body_and_maps_the_source_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        old_name = models.IntegerField()
        untouched = models.IntegerField()

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_rename"

    old_field = Record._meta.get_field("old_name")
    new_field = models.IntegerField()
    new_field.set_attributes_from_name("new_name")
    new_field.model = Record
    editor = _editor(monkeypatch)

    editor._remake_table(Record, alter_fields=[(old_field, new_field)])

    remade = _created_model(editor)
    assert [field.name for field in remade._meta.local_fields] == [
        "id",
        "untouched",
        "new_name",
    ]
    sql = _first_executed_sql(editor)
    assert (
        'INSERT INTO "new__mutation_rename" ("id", "untouched", "new_name") '
        'SELECT "id", "untouched", "old_name" FROM "mutation_rename"'
    ) == sql


@isolate_apps()
def test_remake_database_default_field_is_not_copied_from_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_database_default"

    added = models.IntegerField(db_default=5)
    added.set_attributes_from_name("with_database_default")
    editor = _editor(monkeypatch)

    editor._remake_table(Record, create_field=added)

    sql = _first_executed_sql(editor)
    assert 'INSERT INTO "new__mutation_database_default" ("id", "value")' in sql
    assert 'SELECT "id", "value" FROM "mutation_database_default"' in sql
    assert "with_database_default" not in sql


@isolate_apps()
def test_remake_nullable_to_required_uses_the_effective_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        value = models.IntegerField(null=True)

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_null_default"

    old_field = Record._meta.get_field("value")
    new_field = models.IntegerField(default=17)
    new_field.set_attributes_from_name("value")
    new_field.model = Record
    editor = _editor(monkeypatch)
    prepare_default = MagicMock(return_value="17")
    monkeypatch.setattr(editor, "prepare_default", prepare_default)

    editor._remake_table(Record, alter_fields=[(old_field, new_field)])

    sql = _first_executed_sql(editor)
    prepare_default.assert_called_once_with(17)
    assert 'coalesce("value", 17)' in sql


@isolate_apps()
def test_remake_required_field_does_not_use_coalesce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "mutation_schema"
            db_table = "mutation_required"

    old_field = Record._meta.get_field("value")
    new_field = models.BigIntegerField()
    new_field.set_attributes_from_name("value")
    new_field.model = Record
    editor = _editor(monkeypatch)

    editor._remake_table(Record, alter_fields=[(old_field, new_field)])

    sql = _first_executed_sql(editor)
    assert "coalesce" not in sql
    assert 'SELECT "id", "value" FROM "mutation_required"' in sql
