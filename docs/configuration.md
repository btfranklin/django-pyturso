# Configuration

Configure the backend with a local path or exactly `:memory:`:

```python
DATABASES = {
    "default": {
        "ENGINE": "django_pyturso",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"transaction_mode": "DEFERRED"},
    }
}
```

`transaction_mode` accepts `DEFERRED` (the default), `IMMEDIATE`, or
`CONCURRENT`. `CONCURRENT` requires an explicit `journal_mode` of `MVCC`.
Both options accept case-insensitive strings.

`journal_mode` accepts `WAL` or `MVCC`. If omitted, the backend preserves the
database journal mode. An explicit value is verified during connection setup.
The backend can enable MVCC, but rejects conversion from MVCC back to WAL.
`os.PathLike` names, relative paths, and absolute paths are accepted.

Paths use normal operating-system semantics: traversal components and symlinks
are accepted, and the backend does not impose a project-directory sandbox. See
[Security and supply chain](security.md) for application responsibilities and
the verified path-safety cases.

Empty names, URL schemes, `file:` URIs, credentials, network locations,
`EXCLUSIVE`, other experimental features, VFS/encryption settings, callbacks, remote
sync, SQLite-driver options, and unknown options fail during connection setup.
The backend always calls synchronous top-level `turso.connect()` with
`isolation_level=None`, enables and verifies foreign keys, and validates the
version reported by the connected engine.

## Concurrent writes with MVCC

```python
DATABASES = {
    "default": {
        "ENGINE": "django_pyturso",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "journal_mode": "MVCC",
            "transaction_mode": "CONCURRENT",
        },
    }
}
```

MVCC is a persistent database setting. Removing the option does not undo it.
Use one process for each MVCC database. Connections in that process can share
one file, but separate web workers must not share the MVCC database. Stop the
application before a separate process runs migrations against that file.
In-memory databases remain private to each connection.

`transaction.atomic()` and manual transactions use `BEGIN CONCURRENT`.
Autocommit statements retain normal driver behavior. MVCC permits overlapping
writers; it does not provide `select_for_update()` row locks. See
[Transactions and constraints](transactions.md) for conflicts and schema work.
