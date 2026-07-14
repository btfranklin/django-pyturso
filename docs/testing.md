# Testing

Run the quick local gate with:

```bash
pdm run check
```

The ordinary suite covers the supported backend behavior, including focused
property and fault-injection regressions. Use these groups when changing their
area:

- `pdm run test-differential` compares a compact ORM, transaction, schema, and
  introspection scenario catalog against Django's SQLite backend.
- `pdm run test-integration` exercises Django's test runner, auth, forms, and
  admin paths.
- `pdm run test-stress` exercises bounded file lifecycle and crash recovery
  checks.

## Differential scenarios

The differential lane starts isolated processes for Django's SQLite backend and
`django_pyturso`, using both in-memory and disposable file databases. It covers
ORM CRUD, scalar values, ordering, joins, subqueries, JSON paths,
transactions, table-remake migrations, and introspection.

The catalog is intentionally focused, not a claim that every Django feature is
supported. Add a scenario when a public support claim changes. The intentional
differences are backend identity and `Random`: the backend keeps
`vendor = "sqlite"` for Django SQL-dialect dispatch but does not register
SQLite's `RAND` compatibility function, so `Random` is rejected before SQL
execution.

## Package verification

`pdm run build` creates the wheel and source distribution. `pdm run package-test`
checks their metadata and clean-installs each artifact into a temporary Django
project using both an in-memory and a file database.
