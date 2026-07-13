# Embedded Turso backend contract

This is the authoritative v1 product boundary for `django-pyturso`.

## Runtime and dependency boundary

- CPython `>=3.14`, Django `>=6.0.7,<7`, and the audited
  `pyturso>=0.6.1,<0.7` line.
- Synchronous connections opened only with the real top-level
  `turso.connect()` API supplied by `pyturso`.
- Local filesystem paths and exactly `:memory:`. Relative paths, absolute paths,
  path-like objects, traversal components, and normal filesystem symlinks use
  operating-system semantics; the backend does not create a path sandbox.
- `DEFERRED` and `IMMEDIATE` transaction modes. Django owns transaction
  boundaries with driver implicit transaction handling disabled.

URLs, `file:` URIs, credentials, remote/cloud transports, sync, replicas,
encryption, driver callbacks, unknown options, and experimental engine modes
are rejected before use.

## Supported Django surface

The verified core covers:

- normal ORM create/read/update/delete, bulk insert, conflict update/ignore,
  insert/update returning, filtering, ordering, joins, subqueries, JSON paths,
  aggregates allowed by the static Django capability declarations, positional
  and named bound parameters, and empty `executemany()` batches as no-ops;
- auto/integer, Boolean, character/text, date, datetime, time, decimal, float,
  duration storage, UUID, JSON, IP address, file-path/name, nullable field
  values represented by the backend's field mapping, and `BinaryField` columns
  storing `NULL`;
- explicit manual transactions, outer and nested `atomic()` blocks,
  savepoints, rollback/commit, deferred foreign keys, and close/failure paths;
- Django-generated tables, indexes, unique/check/foreign-key constraints,
  table-remake alterations, forward/backward migrations, introspection, and
  sequence reset;
- auth, content types, sessions, admin, forms, fixtures, management commands,
  and single-process Django test databases; and
- file-backed mirrors and live servers, plus safe `--keepdb` reuse.

Every Django 6.0.7 `BaseDatabaseFeatures` member has an explicit static
disposition. These are framework compatibility facts, not runtime switches.
The declarations in `features.py`, the traceability manifest, and their tests
are the executable detail behind this summary.

## Intentional differences and conservative rejections

- `pyturso` 0.6.1 stores raw `ALTER TABLE ADD COLUMN ... NULL` as `NOT NULL`.
  The schema editor therefore remakes the table to preserve Django nullability.
- Named timezone conversion is rejected; database-side temporal operations are
  supported only without conversion or in UTC.
- Duration values are stored as integer microseconds, but duration arithmetic
  and temporal subtraction remain disabled until a complete equivalence matrix
  passes.
- Window expressions, select-for-update, generated columns, database comments,
  deferrable unique constraints, covering indexes, and other capabilities
  declared false in `features.py` are not supported merely because a narrow SQL
  example may execute.
- In-memory databases cannot be shared between Turso connections, so mirrors,
  live-server thread sharing, and parallel cloning require a file database or
  fail before unsafe use. Parallel test cloning is not supported in v1.
- `dbshell` is unsupported because `pyturso` provides no matching local shell
  contract.

## Intentional BinaryField exclusion

Writes of non-NULL `BinaryField` values are not supported in v1:
`BinaryField.get_db_prep_value()` requires the PEP 249 `Database.Binary()`
constructor, while the real top-level `turso` module in `pyturso` 0.6.1 does
not provide it. The backend will not patch or wrap that module and will not add
a compatibility field, compiler facade, or SQLite fallback.

Schema creation, introspection, and `NULL` storage remain supported. Binary
payload writes are an explicit product exclusion rather than unfinished release
work. A future contract may reconsider the boundary only after a supported
driver exposes the required constructor and complete round-trip evidence passes.

## Explicit exclusions

- Turso Cloud, libSQL-over-HTTP, remote sync, replicas, and invisible network
  work.
- Vector, Turso FTS, UUID7, and other Turso-specific ORM abstractions.
- Older Python/Django lines, stdlib SQLite connections, runtime backend
  substitution, compatibility shims, aliases, and monkey patches.
- Generated columns, experimental concurrency, encryption, and async driver
  adaptation.

Future optional work is recorded in `docs/roadmap.md`; it cannot expand this
contract implicitly.

## Release condition

Local release-candidate eligibility requires every authoritative verification
gate to pass for the exact prepared artifacts. Publication, tagging, pushing,
remote CI execution, and GitHub Release creation are separate external actions
and are not part of local preparation.
