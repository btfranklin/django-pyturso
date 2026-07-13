# Schema Constraint Lifecycle

This records the normative foreign-key state protocol implemented by
`DatabaseSchemaEditor` for Django 6.0.7, `pyturso` 0.6.1, and connected Turso
3.50.4.

## Entry

1. Ensure the physical connection exists.
2. Read `PRAGMA foreign_keys` and accept only `0` or `1`.
3. Preserve that original value on the editor instance.
4. If enforcement was enabled, execute `PRAGMA foreign_keys = OFF` and read it
   back before Django opens the schema transaction.
5. Fail before schema work when Turso cannot verify the disabled state. This
   also rejects entry from a transaction in which the pragma cannot change.
6. Enter Django's normal atomic schema context only after the disabled state is
   verified.

The editor never executes `PRAGMA legacy_alter_table`.

## Successful exit

1. Invoke `connection.check_constraints()` before allowing the atomic context
   to commit. The wrapper owns the composite-aware manual checker because Turso
   doesn't expose `PRAGMA foreign_key_check` through the supported driver.
2. Feed a checker failure into Django's atomic exit so schema and copied data
   roll back together.
3. Let Django execute deferred schema SQL and close the atomic context.
4. Restore the exact original `PRAGMA foreign_keys` value and read it back.

The schema editor deliberately calls the public wrapper hook rather than
duplicating FK introspection. The wrapper checker is active and raises before
the atomic schema context can commit invalid copied data.

## Manual foreign-key checking

The wrapper does not use `PRAGMA foreign_key_check`. It reads
`PRAGMA foreign_key_list` for each selected table, groups rows by foreign-key
identifier, and resolves omitted target columns against the target primary key
in declared key order. Each relationship is checked with a quoted `NOT EXISTS`
anti-join whose child predicate requires every source component to be non-null.
This preserves SQLite/Turso `MATCH SIMPLE` behavior: all-null and partially-null
composite keys are ignored.

The first violation raises Django `IntegrityError` with the source table,
stable source identity, source columns and values, and target table and columns.
Declared primary-key columns provide the identity when available; otherwise an
unshadowed `rowid`, `_rowid_`, or `oid` alias is used. Ambiguous omitted targets
or tables without a stable identity fail clearly rather than producing a
misleading result.

The public constraint toggles read the current state before changing it and
read back every requested change. A call that transitions enforcement from on
to off returns `True`; an already-disabled state returns `False`, allowing
Django's context manager to preserve the caller's original state.

## Exceptional exit

An exception from schema work is passed to Django's atomic exit first, which
rolls back the migration. The editor then restores and verifies the original
foreign-key state. A checker exception created during nominal exit is explicitly
re-raised after rollback and restoration.

If rollback/atomic exit itself fails, that failure remains primary. If state
restoration also fails, the editor preserves the primary exception, chains the
restoration failure, and physically disposes the connection. If restoration is
the only failure, it is raised after disposal. No connection with unverified FK
state is returned for reuse.

## Table-remake sequence

For alterations that Turso cannot perform safely in place, the editor:

1. Renders an isolated model with the target schema.
2. Creates `new__<table>` with the target fields, indexes, and constraints.
3. Copies mapped values, applying quoted effective defaults and null-to-nonnull
   coercion where required.
4. Drops only the old table and removes stale deferred statements.
5. Renames the new table to the original name.
6. Executes the recreated deferred SQL against the final table.

Direct column rename and drop are used only under the same conservative
conditions as the audited Django 6.0.7 reference. Primary, unique, indexed, and
foreign-key columns continue through table remake. Local literal quoting handles
booleans, finite numerics, strings, binary data, and date/time values without
stdlib SQLite adapters.

## Verification

Focused tests cover verified disable/readback and restoration, rowid and
primary-key identities, table scoping, composite `MATCH SIMPLE` semantics,
omitted target columns, quoted/non-ASCII identifiers, detailed violations,
rollback after a manual-check failure, connection disposal and exception
precedence after a restoration failure, forward/backward migration operations,
table remakes with data preservation and check constraints, cleanup of
temporary tables, and local default quoting.
