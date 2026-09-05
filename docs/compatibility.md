# Compatibility Status

## Current verified slice

The backend opens local files and exactly `:memory:` through the synchronous
top-level `turso.connect()` API. It verifies foreign-key enforcement and the
connected engine version, translates Django placeholders, and exercises the
ordinary ORM against representative scalar fields.

## Regular expressions

The `regex` and `iregex` lookups use Turso's native regular expression engine.
Anchors, groups, and alternatives are supported. The `iregex` lookup enables
case-insensitive matching.

Backreferences, such as `^(a)\1$`, are not supported. The backend declares
`supports_regex_backreferencing = False`. In pyturso 0.7.0, this pattern returns
SQL `NULL`, so a filter does not match the row. It does not raise an error.
Applications must use patterns that the native engine supports.

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

## Schema introspection

Introspection preserves the column order in named and unnamed table-level
`UNIQUE` constraints. The `inspectdb` command includes composite uniqueness
rules in the generated model's `unique_together` setting.
