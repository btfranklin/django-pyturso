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

`transaction_mode` accepts `DEFERRED` (the default) or `IMMEDIATE`.
`os.PathLike` names, relative paths, and absolute paths are accepted.

Paths use normal operating-system semantics: traversal components and symlinks
are accepted, and the backend does not impose a project-directory sandbox. See
[Security and supply chain](security.md) for application responsibilities and
the verified path-safety cases.

Empty names, URL schemes, `file:` URIs, credentials, network locations,
`EXCLUSIVE`, experimental features, VFS/encryption settings, callbacks, remote
sync, SQLite-driver options, and unknown options fail during connection setup.
The backend always calls synchronous top-level `turso.connect()` with
`isolation_level=None`, enables and verifies foreign keys, and validates the
version reported by the connected engine.
