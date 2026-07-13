"""Focused mutation tests for the final table-remake contracts."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from django.db import models
from django.test.utils import isolate_apps

from tests.core.test_schema_branches import _remake_editor

pytestmark = pytest.mark.core


@isolate_apps()
def test_remake_uses_exact_temporary_model_and_finalization_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        value = models.CharField(max_length=20)

        class Meta:
            app_label = "schema_remake_finalize"
            db_table = "remake_finalize_record"

    editor, delete = _remake_editor(monkeypatch)
    create = MagicMock()
    alter = MagicMock()
    monkeypatch.setattr(editor, "create_model", create)
    monkeypatch.setattr(editor, "alter_db_table", alter)

    editor._remake_table(Record)

    new_model: Any = create.call_args.args[0]
    assert new_model.__name__ == "NewRecord"
    assert new_model._meta.db_table == "new__remake_finalize_record"
    delete.assert_called_once_with(Record, handle_autom2m=False)
    alter.assert_called_once_with(
        new_model,
        "new__remake_finalize_record",
        "remake_finalize_record",
    )


@isolate_apps()
def test_deleting_automatic_primary_key_clears_recreated_model_pk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Record(models.Model):
        value = models.CharField(max_length=20)

        class Meta:
            app_label = "schema_remake_finalize"
            db_table = "remake_finalize_primary_delete"

    editor, _delete = _remake_editor(monkeypatch)
    create = MagicMock()
    monkeypatch.setattr(editor, "create_model", create)

    editor._remake_table(Record, delete_field=Record._meta.pk)

    new_model: Any = create.call_args.args[0]
    assert new_model.pk is None
    assert new_model._meta.local_fields == [new_model._meta.get_field("value")]
