# Transactions and Constraints

Django owns transaction boundaries. The driver remains in explicit-autocommit
mode; disabling Django autocommit starts `BEGIN DEFERRED` or `BEGIN IMMEDIATE`.
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
restores the original enforcement state. A failed restoration disposes the
connection so it cannot be reused with constraints accidentally disabled.
