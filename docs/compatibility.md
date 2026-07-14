# Compatibility Status

## Current verified slice

The backend opens local files and exactly `:memory:` through the synchronous
top-level `turso.connect()` API. It verifies foreign-key enforcement and the
connected engine version, translates Django placeholders, and exercises the
ordinary ORM against representative scalar fields.

## Intentional BinaryField exclusion

`pyturso` 0.7.0 does not expose the PEP 249 `Binary()` constructor. Django's
`BinaryField.get_db_prep_value()` calls `connection.Database.Binary()` before a
database backend operation hook can adapt the value. Therefore writes of
non-NULL `BinaryField` values are intentionally outside v1 while retaining the rules
that `Database` is the real top-level `turso` module and that the backend adds
no monkey patch, facade, compatibility shim, or field replacement.

Creating and introspecting `BinaryField` columns and storing `NULL` remain in
scope. Writing a binary payload does not. Applications that require binary
payload storage must not use this backend for that field in v1.

The audited 0.7.0 release likewise has no top-level `turso.Binary`, so the v1
exclusion remains in force.

## Driver I/O exception defect

`pyturso` 0.7.0 raises an extension `turso.IoError` for directory and
permission-denied database opens, but that class is outside the driver's
exported PEP 249 exception hierarchy. Django's normal database-error wrapper
therefore cannot recognize it. The backend translates only this audited
connection-open defect into Django `OperationalError`, preserving the original
exception as its cause. Other driver exceptions continue through Django's
normal wrapper without a backend translation layer.
