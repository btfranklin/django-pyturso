# Django Test Runner

The backend supports Django's single-process runner with file databases and
exactly `:memory:`. Default file test databases are siblings named
`test_<filename>`; `TEST.NAME` overrides that path. `--keepdb` reuses a cleanly
closed file database.

Test database setup and teardown close the current physical connection before
they switch databases. An open in-memory database does not retain its tables
during test setup, even when the test database name is also `:memory:`. Teardown
also closes in-memory test databases when `--keepdb` is set. A file-backed mirror
closes its current connection before it selects the primary database file.
These switches must occur outside an atomic block and on the connection's thread.

Creating or destroying a file test database removes its database file, WAL
file (`-wal`), and MVCC log file (`-log`). Other files are retained. `--keepdb`
retains all database files for reuse.

File-backed mirrors resolve to the same local file, and file-backed
`LiveServerTestCase` uses separate thread-local connections. In-memory mirrors
and in-memory live-server use fail during setup because separate Turso
connections do not share an in-memory database. Configure a disposable file
database for those paths.

The live-server test reads a stored row over HTTP, changes it in the test thread,
and reads the new value over HTTP. This checks shared file access between threads.

Parallel test database cloning is unsupported and raises `NotSupportedError`.
The backend never copies a live database or uses a stdlib SQLite backup as an
intermediate.

Cascading flush follows foreign-key references through the actual table names.
ASCII letter case does not affect that lookup. Distinct Unicode names remain
distinct.

Both supported database modes also run JSON fixture loading, two
`serialized_rollback` transaction cases, `check --database`, `migrate --plan`,
and `showmigrations --plan`. These paths are regression-tested through the
integration project's real management entry point.
