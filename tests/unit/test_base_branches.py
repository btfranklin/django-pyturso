"""Focused branch tests for connection, constraint, and lifecycle fault paths."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
import turso
from django.db import DatabaseError, NotSupportedError
from django.db.transaction import TransactionManagementError

from django_pyturso.base import DatabaseWrapper
from tests.core.test_connection import wrapper_settings

pytestmark = pytest.mark.core


class TransactionConnection:
    def __init__(self, *, in_transaction: bool) -> None:
        self.in_transaction = in_transaction
        self.closed = False
        self.executed: list[str] = []

    def execute(self, statement: str) -> None:
        self.executed.append(statement)

    def rollback(self) -> None:
        self.in_transaction = False

    def close(self) -> None:
        self.closed = True


class StickyRollbackConnection(TransactionConnection):
    def rollback(self) -> None:
        pass


class FailingExecuteConnection(TransactionConnection):
    def execute(self, statement: str) -> None:
        raise turso.DatabaseError("injected usability failure")


class FailingStateConnection(TransactionConnection):
    @property
    def in_transaction(self) -> bool:
        raise turso.DatabaseError("injected state-read failure")

    @in_transaction.setter
    def in_transaction(self, value: bool) -> None:
        pass


class ReadbackCursor:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row = row

    def __enter__(self) -> ReadbackCursor:
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass

    def execute(self, statement: str) -> None:
        pass

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row


def attach(wrapper: DatabaseWrapper, connection: object) -> None:
    wrapper.connection = cast(Any, connection)


def test_inconsistent_atomic_state_is_rejected() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "atomic_state")
    attach(wrapper, TransactionConnection(in_transaction=False))
    wrapper.autocommit = False
    wrapper.in_atomic_block = True
    wrapper.commit_on_exit = True

    with pytest.raises(TransactionManagementError, match="no longer active"):
        wrapper._ensure_transaction()


def test_disabling_autocommit_does_not_restart_active_transaction() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "active_transaction")
    physical = TransactionConnection(in_transaction=True)
    attach(wrapper, physical)

    wrapper._set_autocommit(False)

    assert physical.executed == []


@pytest.mark.parametrize("row", [None, (2,)])
def test_invalid_foreign_key_state_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    row: tuple[object, ...] | None,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "invalid_fk_state")
    monkeypatch.setattr(wrapper, "cursor", lambda: ReadbackCursor(row))

    with pytest.raises(DatabaseError, match="valid foreign-key state"):
        wrapper._read_foreign_key_state()


def test_constraint_state_changes_require_successful_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "constraint_readback")
    states = iter((1, 1))
    monkeypatch.setattr(wrapper, "_read_foreign_key_state", lambda: next(states))
    monkeypatch.setattr(wrapper, "cursor", lambda: ReadbackCursor(None))

    with pytest.raises(NotSupportedError, match="did not disable"):
        wrapper.disable_constraint_checking()

    monkeypatch.setattr(wrapper, "_read_foreign_key_state", lambda: 1)
    wrapper.enable_constraint_checking()

    states = iter((0, 0))
    monkeypatch.setattr(wrapper, "_read_foreign_key_state", lambda: next(states))
    with pytest.raises(NotSupportedError, match="did not enable"):
        wrapper.enable_constraint_checking()


def test_omitted_foreign_key_targets_require_matching_primary_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "foreign_key_targets")
    monkeypatch.setattr(
        wrapper.introspection,
        "get_primary_key_columns",
        lambda cursor, table: [],
    )
    rows = [(0, 0, "parent", "parent_id", None)]

    with pytest.raises(DatabaseError, match="do not match the target primary key"):
        wrapper._resolve_foreign_key_targets(object(), "parent", rows)


def test_omitted_foreign_key_targets_reject_invalid_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "foreign_key_sequence")
    monkeypatch.setattr(
        wrapper.introspection,
        "get_primary_key_columns",
        lambda cursor, table: ["id"],
    )
    rows = [(0, 1, "parent", "parent_id", None)]

    with pytest.raises(DatabaseError, match="Invalid foreign-key sequence 1"):
        wrapper._resolve_foreign_key_targets(object(), "parent", rows)


def test_source_identity_rejects_fully_shadowed_rowid_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "source_identity")
    monkeypatch.setattr(
        wrapper.introspection,
        "get_primary_key_columns",
        lambda cursor, table: [],
    )
    monkeypatch.setattr(
        wrapper.introspection,
        "get_table_description",
        lambda cursor, table: [
            SimpleNamespace(name="rowid"),
            SimpleNamespace(name="_rowid_"),
            SimpleNamespace(name="oid"),
        ],
    )

    with pytest.raises(DatabaseError, match="no primary key or unshadowed rowid"):
        wrapper._source_identity(object(), "child", '"child"')


def test_is_usable_reports_driver_error() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "unusable")
    attach(wrapper, FailingExecuteConnection(in_transaction=False))

    assert wrapper.is_usable() is False


def test_rollback_close_noops_without_connection() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "no_connection")

    wrapper._rollback_active_transaction_for_close()


def test_rollback_close_rejects_sticky_transaction() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "sticky_transaction")
    physical = StickyRollbackConnection(in_transaction=True)
    attach(wrapper, physical)

    with pytest.raises(DatabaseError, match="remained in a transaction"):
        wrapper._rollback_active_transaction_for_close()

    assert physical.closed is True
    assert wrapper.connection is None


def test_close_noops_when_already_closed_in_transaction() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "closed_transaction")
    physical = TransactionConnection(in_transaction=False)
    attach(wrapper, physical)
    wrapper.closed_in_transaction = True

    wrapper.close()

    assert wrapper.connection is physical
    wrapper._force_close()


def test_successful_health_check_marks_connection_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "healthy")
    physical = TransactionConnection(in_transaction=False)
    attach(wrapper, physical)
    wrapper.health_check_enabled = True
    wrapper.health_check_done = False
    monkeypatch.setattr(wrapper, "is_usable", lambda: True)

    wrapper.close_if_health_check_failed()

    assert wrapper.health_check_done is True
    assert wrapper.connection is physical


def test_file_obsolescence_uses_base_lifecycle() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(NAME="local.db"), "file_lifecycle")

    wrapper.close_if_unusable_or_obsolete()


def test_memory_obsolescence_noops_without_connection() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "memory_lifecycle")

    wrapper.close_if_unusable_or_obsolete()


def test_memory_state_read_failure_forces_close(monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "state_read_failure")
    physical = FailingStateConnection(in_transaction=False)
    attach(wrapper, physical)
    wrapper.autocommit = True
    monkeypatch.setattr(wrapper, "get_autocommit", lambda: True)

    wrapper.close_if_unusable_or_obsolete()

    assert physical.closed is True
    assert wrapper.connection is None


def test_recoverable_memory_error_clears_error_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "recoverable_error")
    physical = TransactionConnection(in_transaction=False)
    attach(wrapper, physical)
    wrapper.autocommit = True
    wrapper.errors_occurred = True
    monkeypatch.setattr(wrapper, "get_autocommit", lambda: True)
    monkeypatch.setattr(wrapper, "is_usable", lambda: True)

    wrapper.close_if_unusable_or_obsolete()

    assert wrapper.errors_occurred is False
    assert wrapper.health_check_done is True


def test_healthy_memory_without_expiry_remains_open(monkeypatch: pytest.MonkeyPatch) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(CONN_MAX_AGE=None), "no_expiry")
    physical = TransactionConnection(in_transaction=False)
    attach(wrapper, physical)
    wrapper.autocommit = True
    wrapper.close_at = None
    monkeypatch.setattr(wrapper, "get_autocommit", lambda: True)

    wrapper.close_if_unusable_or_obsolete()

    assert wrapper.connection is physical


def test_memory_thread_sharing_is_rejected() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "memory_threads")

    with pytest.raises(NotSupportedError, match="cannot be shared across threads"):
        wrapper.inc_thread_sharing()


def test_file_thread_sharing_uses_base_counter() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(NAME="local.db"), "file_threads")

    wrapper.inc_thread_sharing()

    assert wrapper.allow_thread_sharing is True
    wrapper.dec_thread_sharing()
    assert wrapper.allow_thread_sharing is False
