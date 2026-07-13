# Architecture

## Purpose

`django-pyturso` is a standalone Django database backend that makes the
embedded Turso engine available through Django's standard database API.

## Layers

```text
Django ORM, migrations, admin, and test runner
                 |
django_pyturso Django database backend
                 |
pyturso DB-API driver
                 |
embedded Turso database file
```

The backend owns Django-facing connection setup, cursor behavior, transaction
semantics, introspection, schema editing, creation, operations, and static
Django capability declarations. `pyturso` owns the database engine and DB-API
connection.

## Boundaries

- The package supports local database files and in-memory databases only.
- It must use `pyturso`, never Python's `sqlite3` driver.
- It must not proxy to libSQL, use HTTP, or require Turso Cloud.
- It must not patch Django or substitute another backend at runtime.
- Django's public database-backend extension interface is the only integration
  seam.

## Owned backend components

`base.py` owns settings, physical connections, cursors, transaction state, and
connection lifecycle. `features.py` declares only verified Django capabilities;
`operations.py` owns SQL generation and value conversion. Introspection,
schema editing, test database creation, and client behavior remain in their
dedicated modules. Runtime product switches and dormant activation paths are forbidden;
supported behavior is fixed by the package version and its documented contract.
