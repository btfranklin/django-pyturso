# Temporal SQL Evidence

This records the Phase 2 temporal decision for CPython 3.14.6, Django 6.0.7,
`pyturso` 0.6.1, and connected Turso 3.50.4. The executable evidence is in
`tests/core/test_operations.py`.

## Supported contract

Database-side temporal operations accept either no timezone conversion or the
explicit timezone name `UTC`. They preserve Django's tuple parameter contract.

The following extraction names execute through native `strftime()` and integer
conversion:

- `year`, `iso_year`, `quarter`, `month`, and `day`.
- ISO `week`, Django `week_day`, and `iso_week_day`.
- `hour`, `minute`, and `second`.

Date truncation supports `year`, `quarter`, `month`, `week`, and `day`.
Datetime truncation supports those date units plus `hour`, `minute`, and
`second`. Time truncation supports `hour`, `minute`, and `second`.

The date-only paths use Turso's native SQLite-compatible date functions. The
datetime and time paths use the connected engine's high-precision time
extension:

1. Parse stored ISO text with `time_parse()` after normalizing the separator and
   appending `Z`.
2. Apply `time_trunc()` for the requested unit.
3. Format with `time_fmt_iso()`, remove the UTC suffix, and restore Django's
   space-separated datetime representation.

`datetime_cast_date_sql()` uses native `date()`. `datetime_cast_time_sql()` uses
the time extension and returns nine fractional digits when the input has
microseconds, for example `18:42:31.123456000`. Django's public `parse_time()`
conversion returns the exact expected `datetime.time(..., microsecond=123456)`;
the additional zero precision is lossless.

## Parameter duplication correction

Quarter and week date SQL embed the input expression twice. The operations
method now duplicates that expression's parameter tuple in the same order.
Datetime week truncation inherits the corrected tuple from date truncation.

The regression tests execute these paths with a parameterized expression and
assert both the returned tuple and result. Before the correction, Django debug
rendering raised `TypeError: not enough arguments for format string`, and the
driver evaluated the unbound repeated placeholder as `NULL`.

## Intentional rejections

Any named IANA zone other than `UTC`, including `America/Phoenix`,
`Europe/London`, and `Asia/Tokyo`, raises `NotSupportedError` before SQL
execution. Turso has no zoneinfo database in this supported configuration and
`pyturso` cannot register Django's Python timezone functions.

Unknown extraction and truncation units also raise `NotSupportedError` before
SQL execution.

Duration values remain stored as signed integer microseconds, but duration
arithmetic and temporal subtraction are intentionally disabled. Supported
arithmetic connectors and every subtraction request raise `NotSupportedError`
until the full positive/negative, boundary, null, cross-calendar, and precision
matrix passes. An invalid duration connector raises `DatabaseError` separately,
so malformed compiler input isn't mislabeled as an unsupported capability.

Consequently `supports_temporal_subtraction` remains `False`; these tests do not
expand the public feature claim.

## Verification

The focused operations suite exercises all supported extraction, truncation,
and cast branches against a real Turso connection, plus UTC/no-zone handling,
named-zone rejection, value adapters/converters, duration rejection, and SQL
parameter preservation.

The verification command is:

```bash
pdm run coverage erase
pdm run coverage run --branch -m pytest -q tests/core/test_operations.py
pdm run coverage report -m src/django_pyturso/operations.py
```

Current result: 63 tests pass, with 256 of 256 statements and 96 of 96 branches
covered in `operations.py`.
