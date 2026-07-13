# Property, fault, and stress testing

## Scope

The hardening suites supplement the deterministic contract tests. They use
Hypothesis for bounded input and state-sequence generation, direct fault
injection for post-open cleanup, pytest-timeout for bounded stress execution,
and psutil for local process resource observations.

The suites do not change runtime capability detection or application startup.
They exercise research and CI behavior only.

## Scheduled independence lanes

`.github/workflows/hardening.yml` is preparation for a weekly, manually
dispatchable hardening run. It has no push, pull-request, release, publication,
or deployment trigger. Every job installs through the selected PDM lockfile,
has an explicit timeout, and reports the fixed `HARDENING_SEED` used by ordering
and repetition lanes.

The prepared jobs cover the critical mutation target, bounded stress tests,
three repeated fast-suite runs with recorded `PYTHONHASHSEED` values, minimum
and latest dependency locks, environment-sensitive time and locale checks, and
both Django-runner and pytest ordering perturbations. The workflow is only
configuration until GitHub executes it; local validation does not constitute
platform or scheduled-run evidence.

The same environment and ordering lanes are locally runnable:

```console
pdm run hardening-utc
pdm run hardening-timezones
HARDENING_LOCALE=de_DE.UTF-8 pdm run hardening-locale
pdm run hardening-django-order
pdm run hardening-random-order
HARDENING_REPETITIONS=3 pdm run hardening-repeated-fast
```

`hardening-utc` runs the full ordinary suite excluding the separately owned
upstream, stress, and performance lanes. `hardening-timezones` runs the temporal
group once under non-DST `America/Phoenix` and once under DST-observing
`America/New_York`. `hardening-locale` requires the named locale to be installed
and exercises formatting-sensitive date, time, decimal, quoting, and debug-SQL
paths. The workflow generates `de_DE.UTF-8` before that lane.

The Django ordering command runs the integration project's real `TestCase`
corpus once in reverse and once shuffled with the reported seed. The pytest
command uses `pytest-random-order` with global bucketing and the same explicit
seed. Override the deterministic default only when reproducing or expanding a
run:

```console
HARDENING_SEED=8675309 pdm run hardening-random-order
```

## Property profile

Property tests live under `tests/property/` and use an explicit local profile:

- 40 examples for cursor, value, and identifier properties.
- 30 examples for transaction action sequences.
- At most 24 actions in one transaction sequence.
- `derandomize=True` so the default corpus is stable for a given test and
  Hypothesis version.
- Deadlines disabled because correctness, not machine timing, is the oracle.
- Function-scoped fixture health checks suppressed only because the autouse
  pytest-django blocker is a guard, not mutable per-example test data.

The properties cover format and named placeholder conversion, escaped percent
handling, public cursor round trips for DB-API scalar values, quoted Unicode
identifier round trips, and a reference model for manual commit/rollback/read/
write sequences with lazy transaction re-arming.

The identifier corpus is Unicode but casefold-stable. The minimum `pyturso`
0.6.1/Turso 3.50.4 cell rejects a later reference to a quoted uppercase
non-ASCII identifier such as `"À"` after normalizing the reference to `à`.
This is a recorded engine/driver boundary, not evidence that arbitrary Unicode
case variants round-trip. It must be re-probed before widening identifier
claims.

Run them with:

```console
pdm run pytest -q tests/property
```

## Fault profile

`tests/fault_injection/` replaces only the top-level `turso.connect` call with a
controlled public-shape fake. It injects failure while enabling foreign keys,
foreign-key readback rejection, missing engine version, and malformed engine
version. Every post-open failure must close both the cursor and physical
connection and leave the wrapper detached.

```console
pdm run pytest -q tests/fault_injection
```

## Stress profile

Stress tests live under `tests/stress/`, carry the `stress` marker, and have a
10-second per-test timeout. The defaults are intentionally bounded:

- 40 file connection/open/query/close cycles after one warm-up cycle.
- At most two descriptors and one thread above the post-warm-up baseline.
- No remaining open handle for the database or WAL path.
- One subprocess crash simulation using `os._exit(23)` with an uncommitted
  `BEGIN IMMEDIATE` write, followed by rollback visibility and writability
  checks from a new Django wrapper.

```console
pdm run test-stress
# or only this bounded group
pdm run pytest -q -m stress tests/stress
```

Resource-count tolerances absorb process-level noise without turning a growing
leak into a pass. The result is local evidence; CI must retain platform-specific
results rather than assuming descriptor and thread behavior is identical on
every OS.

## Reproducing failures

Start with the single node ID printed by pytest:

```console
pdm run pytest -q tests/property/test_transaction_sequences.py::test_manual_transaction_sequences_match_the_reference_model
```

Hypothesis prints a minimized failing example. Add its temporary
`@reproduce_failure(...)` decorator only while debugging, or rerun with the
reported seed when one is supplied:

```console
pdm run pytest tests/property --hypothesis-seed=<reported-seed> -vv
```

Remove temporary reproduction decorators after promoting a regression into a
named deterministic example. For stress failures, preserve the OS, kernel,
architecture, Python, Django, `pyturso`, connected engine, timeout, return code,
descriptor/thread counts, and the exact node ID. Do not increase timeouts or
resource tolerances until the failure has been reproduced and classified.
