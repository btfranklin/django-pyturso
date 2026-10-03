# Transactions and Constraints

Django owns transaction boundaries. The driver remains in explicit-autocommit
mode; disabling Django autocommit starts the configured `BEGIN DEFERRED`,
`BEGIN IMMEDIATE`, or `BEGIN CONCURRENT` transaction.
After a manual commit or rollback, the next statement or cursor fetch lazily
starts the next manual transaction. Ordinary and nested `atomic()` blocks use
explicit outer transactions and savepoints.

Turso can delay a statement with result columns until the cursor fetches a row.
This includes writes with `RETURNING`. The backend checks Django's transaction
state before `fetchone()`, `fetchmany()`, `fetchall()`, and each iteration step.
A pending write fetched after a manual commit or rollback belongs to the next
manual transaction and can be rolled back. Fetching within a failed atomic
transaction raises `TransactionManagementError`, including for read cursors.

`executemany()` consumes parameter iterators without retaining the complete batch.
It accepts positional or named parameter rows. An empty iterator is a no-op.

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

If a statement or fetch error ends the engine transaction within `atomic()`, the
backend marks the block for rollback and removes its commit callbacks. Further
statements and fetches cannot start new engine work in that failed block.
Savepoint rollback does not start a new transaction when the engine has already
discarded the transaction and its savepoints.

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
