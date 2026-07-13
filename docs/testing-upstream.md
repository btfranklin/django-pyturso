# Selected Django upstream tests

The upstream compatibility lane runs an exact, project-owned selection from
Django's test suite against `django_pyturso`. It is a bounded compatibility
signal, not a claim that the complete Django suite passes.

## Pinned source

The lane is pinned to Django tag `6.0.7` at commit
`e2a424605ac2e7e6e799496542fb2997207e2f23`. The runner verifies that commit,
requires an unmodified checkout, verifies the installed Django version is
`6.0.7`, and confirms every configured test label still exists in the pinned
source before execution.

At the 2026-07-13 lock refresh, Django 6.0.7 is both the declared minimum and
the newest stable Django 6 release. The minimum and latest lock lanes therefore
converge on the same upstream source today; they remain separate resolution
artifacts so a later Django 6 release cannot enter support without an explicit
manifest/provenance audit.

Run the smoke profile with:

```bash
pdm run python scripts/run_django_upstream.py --profile smoke
```

By default, the runner fetches the pinned tag into a disposable checkout,
verifies that the tag resolves to the pinned commit, and uses a separate
disposable directory for test databases. It does not copy Django source into
this repository. To reuse a previously fetched, clean checkout at the exact
commit:

```bash
pdm run python scripts/run_django_upstream.py \
  --profile smoke \
  --checkout /path/to/django-checkout
```

Use `--list` to validate and display the lane without running it. Use one or
more `--category` options to run a narrower backend, schema, introspection,
transactions, or query slice.

## Expectation policy

`tests/manifests/upstream-expectations.toml` is the source of truth. Each entry
contains an exact Django test method label, a category, a profile, its relevance
to the backend contract, and an expected project outcome. The profile also
records accepted pass, skip, and failure counts; the runner rejects count drift
before invoking Django:

- `pass` labels are run normally and must pass.
- `skip` labels are omitted by default and must carry a project-owned blocker
  code and explanation. They are work still to resolve, not accepted failures.

The lane does not load or translate Django's SQLite expected-failure or skip
lists. A test is selected because it exercises this backend's v1 contract, and
every omission encoded in the manifest is an explicit `django_pyturso`
decision. `--probe-skips` deliberately includes skipped labels so a maintainer
can test whether their blockers have been removed; a successful probe should
be followed by changing those entries to `pass`.

## Current smoke profile

The smoke profile contains 30 passing labels across all five categories:

- Backend wrapper identity, version reporting, initialization, and execute
  wrappers.
- Base schema-editor default handling, schema SQL logging, field alteration, and
  field renaming.
- Primary-key and constraint parsing plus live table, column, relation, index,
  and constraint introspection.
- Durable atomic-block behavior, outer commits, and nested rollback behavior.
- Insert `RETURNING`, bulk insert, raw SQL annotation, Unicode, and microsecond
  query behavior.

On July 13, 2026, the pinned lane passed all 30 labels in 0.314 seconds on
macOS arm64 with CPython 3.14.6, Django 6.0.7, and pyturso 0.6.1:

```text
Found 30 test(s).
Ran 30 tests in 0.314s
OK
```

This is intentionally the bounded smoke profile; the complete upstream suite
was not run.

## Intentional upstream difference

One additional schema label, `schema.tests.SchemaTests.test_add_field`, is
recorded as `UPSTREAM-INTENTIONAL-SCHEMA-REMAKE-NULLABLE-ADD`. With pyturso
0.6.1, raw `ALTER TABLE ADD COLUMN ... NULL` stores the column as `NOT NULL`.
The backend therefore intentionally uses Django's table-remake path so the
added column has correct nullable semantics.

The upstream test confirms the resulting field type and nullability, but also
contains a SQLite-specific assertion that adding this nullable field executes
no `CREATE TABLE`. That assertion fails because the required Turso workaround
does create a replacement table. The skip records this deliberate
implementation difference rather than treating correct nullability as a
backend defect or hiding the label behind Django's SQLite skip machinery.

The July 13, 2026 `--probe-skips` run executed all 31 labels: 30 passed and this
one failed at Django's no-`CREATE TABLE` assertion on `schema/tests.py:665`
(`AssertionError: True is not False`). The normal lane excludes the documented
difference and remains green.

## Updating the lane

When adding coverage, select exact test methods from the pinned checkout and
add them to the manifest with the narrowest accurate category. The runner's
source validation will reject stale module, class, or method names. Changing
the Django tag or commit is a separate provenance decision: update both source
fields together, verify the installed dependency matches, and rerun every
configured label before recording a new result.
