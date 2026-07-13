# Django Test Runner

The backend supports Django's single-process runner with file databases and
exactly `:memory:`. Default file test databases are siblings named
`test_<filename>`; `TEST.NAME` overrides that path. `--keepdb` reuses a cleanly
closed file database.

File-backed mirrors resolve to the same local file, and file-backed
`LiveServerTestCase` uses separate thread-local connections. In-memory mirrors
and in-memory live-server use fail during setup because separate Turso
connections do not share an in-memory database. Configure a disposable file
database for those paths.

Parallel test database cloning is unsupported and raises `NotSupportedError`.
The backend never copies a live database or uses a stdlib SQLite backup as an
intermediate.

Both supported database modes also run JSON fixture loading, two
`serialized_rollback` transaction cases, `check --database`, `migrate --plan`,
and `showmigrations --plan`. These paths are regression-tested through the
integration project's real management entry point.
