# Performance regression lane

## Scope

The performance lane protects representative Django/backend work in three
orders: normalized correctness, query count, then elapsed time. A benchmark is
never accepted merely because incorrect work completed quickly.

This repository supports embedded Turso through top-level `turso.connect()`.
The lane therefore uses a disposable local file through `django-pyturso`; it
does not introduce `turso dev`, an HTTP transport, or the SQLite backend. There
are no HTTP GET surfaces in this backend package, so RequestFactory coverage
and a GET-surface registry are not applicable.

All performance tests carry the `performance` marker and remain outside the
normal fast and full test profiles.

## Deterministic corpus

`tests/performance/scenarios.py` seeds fixed primary keys and values without a
clock, RNG, UUID generator, network access, background task, or mutable external
service. The file-backed corpus contains 5,000 entries, 2,000 records, 50
authors, 40 introspection tables, a 1,000-row write batch, and 500 rows for the
populated-table migration.

| Case | Workload and correctness oracle | Enforced cap |
| --- | --- | ---: |
| `connection_lifecycle` | Two physical opens, initialization/version checks, four persistent queries, and two closes | 8 operations |
| `orm_single_row_crud` | Create, read, update, and delete one model row; compare all states | 9 queries |
| `orm_active_page_500` | First 500 active rows from 5,000 ordered Django model rows; compare count, boundaries, ID sum, and SHA-256 | 1 query |
| `cursor_insert_1000` | Insert 1,000 fixed rows with one `executemany()`; compare count, boundaries, ID sum, and SHA-256 | 1 query |
| `cursor_update_1000` | Update the same 1,000 rows with one `executemany()`; compare count, boundaries, ID sum, and SHA-256 | 1 query |
| `orm_query_families` | Indexed and unindexed filters, ordering, aggregate, `select_related()`, and JSON lookup; compare counts, boundaries, sums, and SHA-256 values | 6 queries |
| `transaction_atomic_savepoint` | Outer transaction with a rolled-back savepoint followed by a committed row; compare final rows | 9 queries |
| `migration_initial` | Apply a Django `CreateModel` operation and inspect the empty table | 57 queries |
| `migration_populated_remake` | Add a defaulted field through Django's schema editor to a populated 500-row table; compare columns, row count, default count, and SHA-256 | 60 queries |
| `introspection_40_tables` | Discover and describe 40 deterministic tables; compare names and column SHA-256 | 81 queries |
| `test_database_lifecycle` | Create, schema-create, flush, and destroy a disposable test database; verify rows and database/WAL removal | 7 operations |

The reviewed semantic artifacts are
`tests/snapshots/performance/correctness.json` and
`tests/snapshots/performance/query-caps.json`. Query counts come from Django's
query-capture machinery. Connection and test-database lifecycle cases use
explicit operation caps because their work occurs at the physical driver and
database-creation boundaries. The higher schema-operation counts are expected,
deterministic ceilings rather than elapsed-time proxies.

The full corpus runs as correctness tests. The two representative timed cases,
`orm_active_page_500` and `cursor_insert_1000`, rerun their correctness and
query-cap assertions before invoking pytest-benchmark, so test ordering cannot
bypass the deterministic gate.

## Correctness-only command

Use the disabled benchmark mode for the quick semantic and query-count lane:

```console
pdm run pytest -q -m performance tests/performance --benchmark-disable
```

This still invokes each benchmark target once after its correctness preflight,
but it does not collect timing statistics.

## Non-strict report mode

Non-strict mode is the default for developer machines and heterogeneous CI. It
records timing without turning machine noise into a test failure.

```console
mkdir -p artifacts/performance
pdm run pytest -q -m performance tests/performance/test_workloads.py \
  --benchmark-only \
  --benchmark-json=artifacts/performance/pytest-benchmark.json
pdm run python -m tests.performance.report \
  artifacts/performance/pytest-benchmark.json \
  artifacts/performance/report
```

The renderer writes `performance-report.json` for automation and
`performance-report.md` for review. Its schema records observed query or
operation counts, configured caps, correctness status, normalized row count and
SHA-256 when supplied, and timing status. Non-strict timing rows are explicitly
reported as `observation-only`; correctness and operation caps remain enforced
by pytest.

## Strict local timing mode

Strict rendering applies only checked-in stable-case budgets:

```console
pdm run python -m tests.performance.report \
  artifacts/performance/pytest-benchmark.json \
  artifacts/performance/strict-report \
  --strict
```

`tests/snapshots/performance/timing-budgets.json` currently gates only
`orm_active_page_500` at a 1.0 ms maximum median. An unbudgeted case remains
`observation-only` even in the strict report; query caps still fail normally.

The budget is evidence for the calibrated local machine, not a portable latency
promise. A strict CI job must use a comparable stable runner or establish and
review its own runner-class baseline before treating this file as authoritative.

## Calibration decision

Five independent local benchmark processes were run on 2026-07-13 on Darwin
25.5.0 arm64 with CPython 3.14.6:

| Case | Median samples, ms | Cross-run CV | Maximum / cross-run median | Decision |
| --- | --- | ---: | ---: | --- |
| `orm_active_page_500` | 0.515, 0.441, 0.468, 0.475, 0.427 | 6.6% | 1.10 | Stable enough for conservative 1.0 ms local budget |
| `cursor_insert_1000` | 37.579, 37.918, 37.638, 39.515, 57.685 | 18.6% | 1.52 | No timing gate; observation-only |

The write case also showed large within-run mean/median differences consistent
with file-system or synchronization noise. A checked-in timing limit would not
truthfully distinguish product regression from local-machine variance. Its
snapshot and one-query cap provide deterministic regression protection until a
stable runner proves otherwise.

## Accepting changes

Correctness and timing changes are separate maintenance actions:

1. For intentional semantic output changes, inspect the full normalized result,
   update `correctness.json`, and run the correctness-only command. Do not alter
   timing budgets in the same step unless timing behavior also intentionally
   changed and was recalibrated.
2. For an intentional timing change, run at least five independent benchmark
   processes on the target stable runner. A case is budget-eligible only when
   cross-run CV is at most 10% and maximum/median is at most 1.25.
3. Set a conservative maximum median that leaves machine-noise headroom while
   still detecting a material regression. Record the samples and environment in
   `timing-budgets.json`.
4. Render both non-strict and strict reports and retain the raw
   pytest-benchmark JSON with the review evidence.

Do not refresh snapshots automatically after a failure and do not increase a
budget merely to make a noisy run pass.
