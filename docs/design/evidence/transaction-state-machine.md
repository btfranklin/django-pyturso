# Transaction state machine

## Scope

This document records the accepted Phase 0C transaction contract between
Django 6.0.7, `django-pyturso`, and the synchronous public `pyturso` 0.6.1
DB-API. It is backed by `tests/core/transactions/test_state_machine.py` on the
connected Turso 3.50.4 engine.

The driver connection is always opened with `isolation_level=None`. Django,
not the driver's incomplete implicit-DML recognition, owns every transaction
boundary.

## Invariants

- Wrapper autocommit on implies no active engine transaction during normal
  operation.
- Disabling autocommit executes the configured `BEGIN DEFERRED` or
  `BEGIN IMMEDIATE` immediately.
- A successful driver commit or rollback ends the engine transaction but does
  not change Django's wrapper-level autocommit flag.
- While wrapper autocommit remains off, the next cursor execution lazily issues
  the configured `BEGIN` if the engine transaction ended.
- The same cursor path is used when Django creates a savepoint. Therefore an
  `atomic()` block entered after a low-level manual commit or rollback re-arms
  the transaction before creating its savepoint.
- A missing engine transaction inside an ordinary outer `atomic()` block is
  state drift. It raises `TransactionManagementError` rather than silently
  starting a replacement transaction.
- Enabling autocommit while the engine transaction is active raises
  `TransactionManagementError`. The caller must explicitly commit or roll
  back first.
- All SQL passes through the same transaction guard, including statements
  beginning with `WITH` and batches passed to `executemany()`.

## States

| State | Wrapper autocommit | `in_atomic_block` | `commit_on_exit` | Engine transaction |
| --- | --- | --- | --- | --- |
| A: normal autocommit | On | No | — | Inactive |
| M: manual active | Off | No | — | Active |
| G: manual gap after commit/rollback | Off | No | — | Inactive |
| O: ordinary outer `atomic()` | Off | Yes | Yes | Active |
| S: nested `atomic()` | Off | Yes | Yes | Active with savepoint |
| P: `atomic()` inside manual mode | Off | Yes | No | Active with savepoint |
| C: closed inside transaction | Off | Yes until block exit | Either | Rolled back and physically closed |

State G is intentional and short-lived. Django's low-level transaction API
keeps autocommit off after `commit()` and `rollback()`, while the Turso driver
correctly ends the physical transaction. The next cursor or savepoint entry
moves G back to M by issuing `BEGIN`.

## Transitions

| Operation | From | To | Required observation |
| --- | --- | --- | --- |
| `set_autocommit(False)` | A | M | Explicit configured `BEGIN`; engine becomes active |
| Statement | M | M | Statement executes in the current transaction |
| Manual `commit()` | M | G | Persist work; engine becomes inactive; wrapper remains off |
| Manual `rollback()` | M | G | Discard work; engine becomes inactive; wrapper remains off |
| Cursor execution | G | M | Lazy configured `BEGIN` occurs before the statement |
| Enter `atomic()` | A | O | Django calls the explicit begin-under-autocommit path |
| Enter nested `atomic()` | O/S | S | Django creates a savepoint |
| Exit successful nested block | S | O/S | Savepoint is released |
| Exit failed nested block | S | O/S | Roll back to and release savepoint; inner callbacks removed |
| Exit successful outer block | O | A | Commit, enable autocommit, then run queued callbacks |
| Exit failed outer block | O | A | Roll back and enable autocommit; callbacks discarded |
| Enter `atomic()` | G | P | Lazy `BEGIN`, then create a savepoint |
| Exit `atomic()` | P | M | Release savepoint; manual outer transaction remains active |
| `set_autocommit(True)` | G | A | Allowed; commit hooks run if a manual commit armed them |
| `set_autocommit(True)` | M | — | Rejected until explicit commit or rollback |
| Close inside atomic | O/S/P | C | Explicit rollback, physical close, Django broken-transaction flags preserved |

## Verified sequences

The focused suite verifies:

- Disable autocommit, perform a CTE-prefixed write, reject premature enable,
  commit, re-arm on the next write, roll back, re-arm again, commit, and enable
  autocommit. Only committed rows remain.
- Enter `atomic()` immediately after both a manual commit and a manual
  rollback. Savepoint creation re-arms the engine transaction in both cases.
- Commit an outer `atomic()` block, roll back an inner savepoint, preserve the
  outer row, discard the inner row, run the outer `on_commit()` callback, and
  discard the inner callback.
- Roll back DDL and DML together when an outer block fails.
- Roll back before explicit close in manual mode and before a close inside an
  atomic block.
- Clear pending commit callbacks on every close request, including a
  lifecycle-preserving in-memory close.

## Failure behavior

If the engine reports no transaction during an ordinary outer atomic block,
the cursor guard raises `TransactionManagementError`. If rollback during close
raises, the wrapper forcibly closes and detaches the physical connection,
clears callbacks, and re-raises the rollback error. If rollback returns but the
engine still reports an active transaction, the wrapper treats that as the
same unrecoverable failure and disposes the connection.

At request-boundary cleanup, wrapper/settings autocommit mismatch and an active
engine transaction while wrapper autocommit is on are invalid state. The
backend explicitly rolls back any observable active transaction and forcibly
disposes the connection. It never preserves that state merely because the
database is `:memory:`.

## Evidence boundary

This evidence covers the public, synchronous, single-process wrapper contract.
Two-connection `DEFERRED`/`IMMEDIATE` contention, deferred foreign-key commit
failures, commit/begin fault injection, and process-crash recovery remain
separate hardening evidence; they are not inferred from these passing tests.
