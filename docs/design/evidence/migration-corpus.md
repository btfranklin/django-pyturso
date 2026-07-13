# Migration corpus digest

This evidence records a reversible, Django-operation-generated migration corpus
for the Phase 3 schema contract. The executable source of truth is
`tests/core/test_migration_corpus.py`; its committed digest snapshot is
`tests/snapshots/schema/migration-corpus.json`.

## Corpus

The corpus begins with two historical models:

- `Author` has a unique slug, JSON preferences, a date, and a named date index.
- `Article` targets the author's unique slug rather than its primary key. It has
  JSON, datetime, time, and duration values; a composite named unique constraint;
  a named status check; a datetime index; and the implicit foreign-key index.

The forward migration sequence uses Django `ProjectState` and migration
operations to:

1. widen the unique target slug, forcing both the author and its related article
   table through the audited remake path;
2. make the JSON preferences field non-null with a default;
3. widen the article title;
4. replace the status constraint, rename status to lifecycle, and install the
   equivalent lifecycle constraint;
5. add a decimal score with a default and a named non-negative check; and
6. add a composite lifecycle/title index.

Each operation is then executed backward in reverse order. The restored schema
and data digest must exactly equal the initial digest. Finally, both create-model
operations are reversed, and introspection must find neither corpus tables nor
`new__` remake residue.

## Normalization

The digest is SHA-256 over canonical JSON containing the introspected schema and
ORM-read data. Table, column, constraint, and JSON-key ordering is normalized.
Datetimes, dates, and times use ISO-8601; decimals use strings; durations use
seconds. Physical column ordinal drift caused by a remake is deliberately
excluded because it does not change Django's field contract.

| Stage | Schema and data digest |
| --- | --- |
| Initial | `5d568b767d4d9f1776585d038ea7062705bb2494e80b424b6cdfe7990fb9fe8c` |
| Forward | `87be516ae4da3215840fb64e9e755bae2a9237c7f9cc3ab4e5e58ce6cbaef3d7` |
| Backward | `5d568b767d4d9f1776585d038ea7062705bb2494e80b424b6cdfe7990fb9fe8c` |

The forward state also executes negative probes for the score and lifecycle
checks, the author/title unique constraint, and the foreign key. Each is required
to raise `IntegrityError` inside an isolated transaction without changing the
recorded row counts.

## Scope

This corpus intentionally does not write non-NULL `BinaryField` values because
binary payload writes are outside the v1 contract. It tests only the embedded
Turso backend and does not introduce SQLite fallback behavior.
