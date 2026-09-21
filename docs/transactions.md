# Transactions and Constraints

Django owns transaction boundaries. The driver remains in explicit-autocommit
mode; disabling Django autocommit starts the configured `BEGIN DEFERRED`,
`BEGIN IMMEDIATE`, or `BEGIN CONCURRENT` transaction.
After a manual commit or rollback, the next statement lazily starts the next
manual transaction. Ordinary and nested `atomic()` blocks use explicit outer
transactions and savepoints.

Enabling autocommit while work remains active raises
`TransactionManagementError`; callers must choose commit or rollback. Closing
with active work rolls it back. Healthy lifecycle closes preserve an in-memory
database, while broken state, failed health checks, atomic closure, rollback
failure, or wrapper/engine drift forcibly disposes it.

Schema editing disables and verifies foreign-key enforcement before its atomic
DDL work, runs the backend's composite-aware manual checker before commit, and
restores the original enforcement state. Deferred DDL errors roll back the atomic
schema changes before the editor restores foreign-key enforcement. The manual
checker uses the parent column type affinity and collation for each comparison,
including references between columns with different declared types. A failed
restoration disposes the connection so it cannot be reused with constraints
accidentally disabled.

## MVCC transactions

With `journal_mode="MVCC"` and `transaction_mode="CONCURRENT"`, outer atomic
blocks use concurrent transactions. Nested atomic blocks use savepoints.
Writers that change separate rows can commit overlapping transactions.
Conflicting writes can raise `DatabaseError` during a statement or commit.
A conflict can also abort the engine transaction.

Catch the error outside the outer `atomic()` block. If the error is a retryable
conflict, retry the complete transaction with fresh reads and a bounded retry
policy. Do not retry every `DatabaseError`, or retry only the failed statement.
The backend does not replay application code. Put external side effects in
`transaction.on_commit()` or otherwise make them safe to repeat.

The schema editor temporarily uses `IMMEDIATE` transactions, including for
atomic work inside non-atomic migrations. It restores `CONCURRENT` on exit,
including error paths. Enter schema editing outside an active transaction.
Raw DDL inside a concurrent atomic block is not supported. Use the schema
editor for schema changes. Custom data migrations must not start concurrent
writers while the schema editor holds its regular transaction.

MVCC access is limited to one process per database. This mode does not add
row locks, `nowait`, or `skip_locked` support.
