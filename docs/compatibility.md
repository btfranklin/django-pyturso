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

## Temporal aggregates

`Sum` and `Avg` reject date, datetime, and time fields. These values are
stored as text, so a numeric aggregate can return a misleading result.

`TruncHour`, `TruncMinute`, and `TruncSecond` can return a `TimeField` from
either a `TimeField` or `DateTimeField` input. The time result has whole-second
precision, as required by these truncation units.

## Driver I/O exception defect

`pyturso` 0.7.0 raises an extension `turso.IoError` for directory and
permission-denied database opens, but that class is outside the driver's
exported PEP 249 exception hierarchy. Django's normal database-error wrapper
therefore cannot recognize it. The backend translates only this audited
connection-open defect into Django `OperationalError`, preserving the original
exception as its cause. Other driver exceptions continue through Django's
normal wrapper without a backend translation layer.

## Schema introspection

Table introspection and `inspectdb` omit Turso's internal tables and tables with
the reserved `sqlite_` prefix. The filters match these prefixes literally, so
similar user table names, such as `sqlitereports_entry`, remain visible.
Cascade flush uses the same table discovery to find all related user tables.
The backend requires Django 6.1.2 or later. Foreign-key inspection returns the
Django 6.1 relation metadata, including database deletion actions.
`inspectdb` preserves actions such as `ON DELETE CASCADE`.

Introspection preserves the column order in named and unnamed table-level
`UNIQUE` constraints. The `inspectdb` command includes composite uniqueness
rules in the generated model's `unique_together` setting.
Quoted column and constraint names retain their actual names, including escaped
double quotes, single quotes, and backticks. `inspectdb` retains column uniqueness
for these names. Single-quoted values in `CHECK` expressions remain string values.
Constraint references use the declared column names when ASCII letter case
differs. Distinct Unicode column names remain distinct, including for JSON fields.
Schema lookup also ignores ASCII case in table and index names.
`COLLATE` and sort modifiers in a table-level `UNIQUE` constraint are not column
references. Introspection preserves only the ordered column list for that rule.
Function names and collation names in a `CHECK` constraint are not column
references. Introspection reports only the columns used by that expression.
SQL literals such as `NULL`, `TRUE`, and `CURRENT_DATE`, and syntax words such
as `AND` and `CASE`, do not refer to columns. Words such as `END`, `LIKE`, and
`GLOB` can also be column names. Introspection distinguishes their column and
syntax uses from their position in the expression.
Column collation lookup ignores `COLLATE` text in default values, comments, and
nested expressions such as `CHECK` conditions. `inspectdb` reports only the
column's declared collation and preserves quoted column and collation names.
Character lengths come only from the declared column type. Text in names,
defaults, comments, and checks cannot set a length. Quoted table names that
contain parentheses or commas do not change how column definitions are read.
Table constraint names cannot set column lengths. Quoted column names that are
SQL keywords, such as `CONSTRAINT`, still retain their declared lengths.

## Schema alterations

Foreign keys use the database deletion actions declared by `models.DB_CASCADE`,
`models.DB_SET_NULL`, and `models.DB_SET_DEFAULT`. Model creation, field addition,
and table remakes preserve these actions. Forward and reverse migrations apply
changes to the action. `DB_SET_DEFAULT` requires a database default and a matching
parent row when that default is not `NULL`.
Ordinary `models.CASCADE` keeps Django's Python deletion policy. Its database
foreign key uses `NO ACTION`.
The schema deletion tests use local files in both WAL and MVCC mode.

A column rename that also changes `db_index` remakes the table. This preserves
stored rows and applies the requested index state.
When a referenced unique column is renamed during a table remake, related tables
are also remade. Their foreign keys use the new column name. Forward and reverse
migrations preserve rows when the rename also changes nullability or `db_index`.
