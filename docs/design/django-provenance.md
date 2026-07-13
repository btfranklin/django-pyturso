# Django Reference-Code Provenance

## Audited upstream release

The implementation reference is Django 6.0.7, signed annotated tag object
`c7b3ee972494d7d9903db3db7cbe2e9ffe20f457`, peeled to commit
[`e2a424605ac2e7e6e799496542fb2997207e2f23`](https://github.com/django/django/commit/e2a424605ac2e7e6e799496542fb2997207e2f23).
The installed wheel's Django backend sources were byte-compared with that
commit before adaptation.

## Component disposition

| Local component | Upstream reference | Disposition |
| --- | --- | --- |
| `base.py` mappings and cursor placeholder conversion | `django/db/backends/sqlite3/base.py`, `_get_varchar_column`, `DatabaseWrapper` constants, `SQLiteCursorWrapper` | Substantially adapted; Turso connection, settings, transactions, and lifecycle implemented locally |
| `operations.py` conversions, conflicts, and JSON index formatting | `django/db/backends/sqlite3/operations.py`, corresponding `DatabaseOperations` methods | Substantially adapted; unavailable Python UDF paths excluded or reimplemented with native SQL |
| `features.py` | `django/db/backends/base/features.py` and `django/db/backends/sqlite3/features.py` | Independently dispositioned against Turso evidence; no SQLite skips or expected failures copied |
| `introspection.py` | `django/db/backends/sqlite3/introspection.py`, `FieldInfo`, `FlexibleFieldLookupDict`, and `DatabaseIntrospection` | Substantially adapted and verified against Turso `sqlite_master`, `table_xinfo`, `table_info`, `foreign_key_list`, `index_list`, and `index_xinfo`; composite keys and Turso expression-index metadata are handled locally |
| `schema.py` | `django/db/backends/sqlite3/schema.py`, `DatabaseSchemaEditor` table-remake and alteration methods | Substantially adapted; local default quoting removes `sqlite3.adapt`, direct Turso pragma handling preserves the original FK state, and failure paths roll back before verified restoration |
| `creation.py` and `client.py` | Django public base-class contracts | Independently implemented; SQLite URI, backup, cloning, and external shell behavior excluded |

No runtime module imports Django's SQLite backend or Python's `sqlite3` module.
No code from Django's `_functions.py`, expected-failure lists, skip lists, or
pre-Django-6 compatibility branches is used.

### Introspection departures

The local introspection implementation retains Django's public return shapes
and SQLite-affinity behavior while owning the Turso-specific query and parsing
decisions. It groups composite foreign-key pragma rows, resolves omitted target
columns from the referenced primary key, preserves composite-primary-key order,
uses `index_xinfo` for ordering and expression indexes, and ignores internal
`sqlite_*` objects. It does not import or call Django's SQLite backend.

### Schema-editor departures

The local editor retains Django 6.0.7's model-state-driven table-remake shape,
including composite primary keys, field additions/removals/alterations, related
table remakes, M2M changes, and constraint recreation. It does not use
`sqlite3.adapt`, `PRAGMA legacy_alter_table`, or the Django SQLite backend at
runtime. It reads and preserves the incoming `PRAGMA foreign_keys` state,
disables checks before Django opens the schema transaction, invokes the
backend's manual checker before commit, rolls failed checks into the atomic
exit, restores and verifies the original state, and disposes a connection whose
constraint state cannot be restored.

## License handling

Adapted source remains subject to Django's BSD 3-Clause terms, reproduced in
`THIRD_PARTY_NOTICES.md`. Original project code remains under the repository's
MIT license. Provenance is reviewed component-by-component whenever the
supported Django 6 release changes.
