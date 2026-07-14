# Post-v1 roadmap

The v1 compatibility release is limited to local embedded Turso through
`django_pyturso`. The following work is deliberately outside its release path.

## Extension boundaries

- `django_pyturso.functions` may provide explicitly imported, stable Turso
  expressions such as UUID7, enhanced regular expressions, and high-precision
  time functions.
- `django_pyturso.contrib.vector` is the only future owner of vector fields,
  indexes, validation, expressions, system checks, and migration serialization.
- `django_pyturso.contrib.fts` may model Turso/Tantivy indexes and explicit
  match, score, and highlight expressions. It must not imitate SQLite FTS APIs.
- Remote sync, cloud transports, replicas, encryption, and networked behavior
  require a separate distribution and `ENGINE`; they cannot become permissive
  options on the local backend.
- Async support waits for a public Django async database-backend interface.

Future integrations must use Django's documented expression, field, index,
migration, and system-check seams. They ship only when their full support
contract is ready; the backend must not contain runtime switches or dormant
activation paths.

## Delivery order

1. Transparent native improvements that preserve Django-visible behavior,
   including temporal precision and a future proven test-database snapshot API.
2. Explicit ORM functions, beginning with a small UUID7 surface.
3. Optional vector and FTS contrib integrations with their own schema and
   migration contracts.
4. Separate operational backends for sync or remote transports; concurrency,
   callable-based retry, encryption, and async require independent designs.

`generate_series()` and operational controls remain cursor/raw-SQL or explicit
service/management-command concerns until Django offers suitable public seams.

## Capability release gate

Each future integration must independently prove:

- no imports, schema, startup work, or behavior change before the integration
  ships as part of the supported API;
- a clear pre-execution failure when a required driver primitive is absent;
- stable constructors, `deconstruct()` output, migration serialization, and
  safe forward/backward migrations;
- model/system checks using stable `django_pyturso.E...` identifiers;
- focused behavior, migration, and compatibility tests; and
- documentation of portability, storage format, operations, and rollback.

None of this roadmap is part of the v1 implementation or verification plan.
