# Testing

## Differential SQLite/Turso scenarios

Run the differential lane with:

```bash
pdm run test-differential
```

The lane starts a fresh Python process for each backend and database mode:

- Django's `django.db.backends.sqlite3` reference backend with `:memory:` and a
  disposable local file.
- `django_pyturso` with `:memory:` and a separate disposable local Turso file.

The ordinary scenario processes never open the same file through both engines. Each process
configures Django independently, creates the same model schema, executes the
same public ORM and schema-editor operations, and emits one canonical JSON
observation per scenario. The parent test compares those observations against
`tests/manifests/differential-scenarios.toml`.

### Current catalog

The initial catalog covers:

- Create, refresh, update, delete, and counts.
- Boolean, decimal, UTC datetime, JSON, and null round trips.
- Explicit null ordering and deterministic secondary ordering.
- Foreign-key joins.
- Correlated `Exists` and scalar `Subquery` annotations.
- JSON array-index and nested-boolean lookups.
- Outer transaction rollback, nested savepoint rollback, and outer commit.
- A defaulted field addition through table remake, row preservation, and field
  removal.
- Table, primary-key, foreign-key, unique-constraint, index, and relation
  introspection.

This is a growing behavioral catalog, not a claim that every field or ORM
expression is already certified. Add a scenario when a public support claim is
implemented, and keep unsupported or not-yet-tested behavior out of parity
claims until it has focused contract evidence.

### Classifications

Every manifest entry has exactly one comparison classification:

- `parity`: the canonical observations must be equal.
- `normalized_parity`: values are converted through a named normalizer before
  equality, such as decimal strings, UTC ISO datetimes, binary hex, sorted
  identifiers, or semantic constraint facts.
- `intentional_difference`: equality is forbidden. The manifest contains exact
  `sqlite_expected` and `turso_expected` JSON plus a public rationale.
- `unsupported`: reserved for a scenario outside the current support contract;
  unsupported scenarios are not silently skipped into a passing comparison.

The initial intentional differences are backend identity and `Random`.
`django_pyturso` deliberately reports its own engine/display name while keeping
`vendor = "sqlite"` for SQL-dialect dispatch. Django SQLite registers the
`RAND` compatibility function, while `pyturso` cannot register it, so the Turso
backend rejects Django's `Random` expression with `NotSupportedError` before SQL
execution.

### Adding a scenario

1. Add a backend-neutral observation to `tests/differential/runner.py` using
   Django public APIs.
2. Normalize only nondeterministic representation, never a semantic difference.
3. Add the same identifier and its classification to
   `tests/manifests/differential-scenarios.toml`.
4. For an intentional difference, record exact JSON expectations and explain
   why the difference is part of the contract rather than an implementation
   defect.
5. Run the focused command in both modes. A scenario key missing from either
   backend fails the manifest coverage assertion, so a case cannot disappear
   behind a backend-specific skip.

Failures report the scenario identifier. The subprocess timeout is 30 seconds;
a crash, hang, or unhandled backend error fails the lane with the captured
subprocess diagnostics rather than being normalized into parity.

## Offline shared-file interoperability

A separate corpus deliberately hands one disposable file between fresh
processes: SQLite creates and writes it, Turso reads it, performs a table-remake
migration and writes it, SQLite reads and writes it again, and a final Turso
process verifies normalized rows, columns, and index metadata. No stage overlaps
another driver connection. This proves the supported offline file handoff
boundary without claiming mixed-driver concurrency.

## Package reproduction

`pdm run build` uses `scripts/build_distributions.py` to preserve the backend's
complete tar payload while rewriting the sdist gzip envelope with the configured
`SOURCE_DATE_EPOCH` (or zero when it is absent). `pdm run reproducible-build`
then performs two controlled builds with the same epoch and requires both wheel
and compressed sdist bytes to match exactly. It reports both artifact hashes.
This comparison-only evidence never replaces the separately built artifacts
inspected by `pdm run package-test`.

Package verification reads both wheel `METADATA` and sdist `PKG-INFO`, requires
their project name, version, Python range, license, and runtime requirements to
agree, and can bind that shared version to an expected release-tag version.

After coverage, performance, mutation review, package verification, and SBOM
validation are current, `pdm run release-evidence` writes deterministic artifact,
lockfile, review, and evidence hashes to `artifacts/release/evidence.json` plus
`dist/SHA256SUMS`. The index reports `release_eligible: false` while
`IMPLEMENTATION_PLAN.md` exists and `true` only after the remaining-work ledger
has been removed; generating an index never changes eligibility.
