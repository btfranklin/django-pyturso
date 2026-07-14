"""Focused exception-lifecycle contracts for the Turso schema editor."""

from __future__ import annotations

from types import SimpleNamespace, TracebackType
from typing import Any, cast

import pytest
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from django_pyturso.schema import DatabaseSchemaEditor

pytestmark = pytest.mark.core


class _LifecycleConnection:
    def __init__(self, check_error: BaseException | None = None) -> None:
        self.alias = "default"
        self.features = SimpleNamespace(can_rollback_ddl=True)
        self.in_atomic_block = False
        self.check_error = check_error

    def check_constraints(self) -> None:
        if self.check_error is not None:
            raise self.check_error


def _editor(check_error: BaseException | None = None) -> DatabaseSchemaEditor:
    wrapper = cast(Any, _LifecycleConnection(check_error))
    return DatabaseSchemaEditor(wrapper, atomic=False)


def _traceback_frame_functions(traceback: TracebackType | None) -> list[str]:
    functions: list[str] = []
    while traceback is not None:
        functions.append(traceback.tb_frame.f_code.co_name)
        traceback = traceback.tb_next
    return functions


def _traceback_functions(error: BaseException) -> list[str]:
    return _traceback_frame_functions(error.__traceback__)


def test_foreign_key_restore_clears_the_unset_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor()
    restored: list[bool] = []
    editor._original_foreign_keys = 1
    monkeypatch.setattr(editor, "_set_foreign_key_state", restored.append)

    editor._restore_foreign_key_state()
    editor._restore_foreign_key_state()

    assert restored == [True]
    assert editor._original_foreign_keys is None


def test_check_failure_is_forwarded_to_base_exit_with_its_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_error = ValueError("check failed")
    editor = _editor(check_error)
    observed: list[tuple[Any, BaseException | None, Any]] = []

    def base_exit(
        _self: BaseDatabaseSchemaEditor,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        observed.append((exc_type, exc_value, traceback))

    monkeypatch.setattr(BaseDatabaseSchemaEditor, "__exit__", base_exit)
    monkeypatch.setattr(editor, "_restore_foreign_key_state", lambda: None)

    with pytest.raises(ValueError, match="check failed") as raised:
        editor.__exit__(None, None, None)

    assert raised.value is check_error
    assert len(observed) == 1
    exc_type, exc_value, check_traceback = observed[0]
    assert exc_type is ValueError
    assert exc_value is check_error
    assert check_traceback is not None
    assert "check_constraints" in _traceback_frame_functions(check_traceback)
    assert "check_constraints" in _traceback_functions(raised.value)


def test_restoration_failure_keeps_base_exit_failure_primary_and_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor()
    body_error = ValueError("body failed")
    exit_error = RuntimeError("base exit failed")
    restoration_error = OSError("restore failed")

    def base_exit(*_args: Any) -> None:
        raise exit_error

    def restore() -> None:
        raise restoration_error

    monkeypatch.setattr(BaseDatabaseSchemaEditor, "__exit__", base_exit)
    monkeypatch.setattr(editor, "_restore_foreign_key_state", restore)

    with pytest.raises(RuntimeError, match="base exit failed") as raised:
        editor.__exit__(ValueError, body_error, body_error.__traceback__)

    assert raised.value is exit_error
    assert raised.value.__cause__ is restoration_error
    assert "base_exit" in _traceback_functions(raised.value)


def test_lone_base_exit_failure_preserves_its_original_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = _editor()
    exit_error = RuntimeError("base exit failed")

    def base_exit(*_args: Any) -> None:
        raise exit_error

    monkeypatch.setattr(BaseDatabaseSchemaEditor, "__exit__", base_exit)
    monkeypatch.setattr(editor, "_restore_foreign_key_state", lambda: None)

    with pytest.raises(RuntimeError, match="base exit failed") as raised:
        editor.__exit__(ValueError, ValueError("body"), None)

    assert raised.value is exit_error
    assert "base_exit" in _traceback_functions(raised.value)
