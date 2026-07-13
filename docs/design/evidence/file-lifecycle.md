# Connection and file lifecycle

## Purpose

This document records the Phase 0C close/disposal decision matrix for local
files and exactly `:memory:`. It complements the raw-driver WAL and sidecar
observations in `driver-platform-matrix.md`; it does not broaden the supported
database-name contract.

The lifecycle has two distinct operations:

- **Preserving close:** ignore a healthy close request for `:memory:` after
  clearing callbacks and rolling back any active manual work. The same physical
  connection remains attached so the database survives Django setup and
  request lifecycle transitions.
- **Forced disposal:** use Django's base close semantics to clear callbacks,
  physically close, and detach the connection outside an atomic block. Inside
  an atomic block, preserve Django's `closed_in_transaction` and
  `needs_rollback` flags until the block exits. Disposing `:memory:` necessarily
  loses the database.

File databases never use preserving close. A normal file close explicitly
rolls back active work before physical closure; it does not depend on implicit
driver rollback-on-close behavior.

## Decision matrix

| Trigger | `:memory:` | File database | Transaction handling |
| --- | --- | --- | --- |
| Explicit close, no active work | Preserve physical connection | Physically close and detach | Clear callbacks |
| Explicit close, manual active work | Preserve after successful rollback | Roll back, physically close, detach | Read back inactive engine state |
| Close inside `atomic()` | Force disposal; database is lost | Force disposal | Explicit rollback first; set Django closed/broken flags |
| Already `closed_in_transaction` | Wait for outer block cleanup | Wait for outer block cleanup | Do not operate on the already closed connection |
| Healthy maximum-age expiry | Preserve, including `CONN_MAX_AGE=0` | Django base expiry closes | No active work expected |
| Wrapper/settings autocommit mismatch | Force disposal | Force disposal | Roll back observable active work first |
| Wrapper autocommit on but engine active | Force disposal | Force disposal | Roll back engine drift first |
| Requested health check fails | Force disposal | Force disposal | Connection is already classified unusable |
| Fatal prior error and usability probe fails | Force disposal | Force disposal | Connection is already classified unusable |
| Prior error but usability probe succeeds | Preserve and clear error state | Preserve and clear error state | Mark health check complete |
| Rollback or rollback-state readback fails during close | Force disposal and re-raise | Force disposal and re-raise | Never reuse uncertain transaction state |

An ordinary in-memory close still clears `run_on_commit`. Ignoring the physical
close must not retain callbacks whose transaction boundary was rolled back or
abandoned.

## Health and obsolescence behavior

Django's base health-check path calls `close()` after a failed usability
probe. That is insufficient for this backend because an ordinary in-memory
close is intentionally preserving. `django-pyturso` therefore owns the health
path and routes a failed probe directly to forced disposal.

For `close_if_unusable_or_obsolete()`:

1. Reset the per-request health-check marker.
2. Force disposal on wrapper/settings autocommit mismatch.
3. Force disposal on the impossible combination of wrapper autocommit on and
   an active Turso transaction.
4. If a prior fatal error occurred, retain the connection only when `SELECT 1`
   succeeds; otherwise force disposal.
5. Treat healthy age expiry as lifecycle-preserving for `:memory:` and as a
   normal physical close for files.

Failed health/fatal probes indicate the physical connection cannot be trusted;
those paths dispose it rather than attempting further application work. The
explicit-close, atomic-close, autocommit-mismatch, and engine-drift paths do
perform observable rollback before physical closure.

## Verified file behavior

The focused Django wrapper test uses a file under pytest's disposable temporary
directory. It creates a table under autocommit, disables autocommit, inserts an
uncommitted row, and closes. The wrapper explicitly rolls back, detaches the
closed physical connection, reconnects through top-level `turso.connect()`, and
observes the table with zero rows.

The raw-driver probe separately observed on Darwin arm64 that:

- Opening the local database created the main file and `-wal` sidecar.
- The journal mode was WAL.
- Passive and truncate checkpoints succeeded.
- Clean close left an 8192-byte main file and a zero-byte WAL file.

These local sizes and sidecar observations are evidence, not deletion rules.
Test-database destruction must delete only artifacts established across the
complete supported platform matrix after clean close/checkpoint behavior is
verified.

## Verified in-memory behavior

The focused suite proves:

- A healthy explicit close preserves both the physical connection and schema.
- Active manual work is rolled back before preservation. Because wrapper
  autocommit remains off, the next query lazily starts a new transaction.
- Healthy age expiry preserves the connection.
- Health failure, fatal error, autocommit mismatch, and wrapper/engine drift
  forcibly detach the connection.
- Close inside `atomic()` explicitly rolls back, closes, sets Django's broken
  transaction state, suppresses queued callbacks, and produces a new empty
  database on the next connection.
- An injected rollback failure still closes and detaches the connection,
  clears callbacks, and propagates the original driver error.

## Remaining lifecycle evidence

This matrix does not claim process-crash recovery, safe live copying, complete
sidecar deletion, in-memory mirror support, cross-thread in-memory access, or
parallel test cloning. Those behaviors retain their explicit unsupported or
later-phase status until their dedicated integration evidence passes.
