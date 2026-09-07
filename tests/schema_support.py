"""Shared support for schema editor tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.db import connection

from django_pyturso.schema import DatabaseSchemaEditor


class _Cursor:
    def __init__(self, row: tuple[int] | None = (1,)) -> None:
        self.row = row
        self.commands: list[str] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.commands.append(sql)

    def fetchone(self) -> tuple[int] | None:
        return self.row


class SchemaConnection:
    def __init__(self, row: tuple[int] | None = (1,)) -> None:
        self.features = SimpleNamespace(can_rollback_ddl=True)
        self.alias = "default"
        self.in_atomic_block = False
        self.cursor_instance = _Cursor(row)
        self.checked = 0
        self.force_closed = 0

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def ensure_connection(self) -> None:
        return None

    def check_constraints(self) -> None:
        self.checked += 1

    def _force_close(self) -> None:
        self.force_closed += 1


def schema_editor(wrapper: Any | None = None) -> DatabaseSchemaEditor:
    editor = DatabaseSchemaEditor(
        wrapper or SchemaConnection(),  # type: ignore[arg-type]
        atomic=False,
    )
    editor.deferred_sql = []
    return editor


def hashable_namespace(**attributes: Any) -> Any:
    value = type("BranchFixture", (), {})()
    for name, attribute in attributes.items():
        setattr(value, name, attribute)
    return value


def remake_editor(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[DatabaseSchemaEditor, MagicMock]:
    editor = DatabaseSchemaEditor(connection, atomic=False)
    delete = MagicMock()
    monkeypatch.setattr(editor, "create_model", MagicMock())
    monkeypatch.setattr(editor, "execute", MagicMock())
    monkeypatch.setattr(editor, "delete_model", delete)
    monkeypatch.setattr(editor, "alter_db_table", MagicMock())
    editor.deferred_sql = []
    return editor, delete


def many_to_many_field(through: Any, local: str, reverse: str) -> Any:
    return SimpleNamespace(
        remote_field=SimpleNamespace(through=through),
        m2m_reverse_field_name=lambda: reverse,
        m2m_field_name=lambda: local,
        m2m_column_name=lambda: f"{local}_id",
        m2m_reverse_name=lambda: f"{reverse}_id",
    )
