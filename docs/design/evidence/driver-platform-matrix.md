# Driver and platform evidence

## Purpose

This document records reproducible Phase 0A evidence for the public `pyturso`
DB-API surface. It describes observations, not backend policy. Backend
compatibility declarations and lifecycle decisions require their own
Django-level evidence.

The evidence was collected with the versioned
`scripts/probes/driver_contract.py` runner. Its default mode opens only a private
`:memory:` connection and performs read-only queries. The explicitly opted-in
mode also mutates a separate in-memory database and a database under an
auto-removed temporary directory. The runner cannot accept a caller database.

```console
pdm run python scripts/probes/driver_contract.py
pdm run python scripts/probes/driver_contract.py \
  --include-disposable-mutations \
  --output driver-evidence.json
```

The JSON contract is identified by schema version `1`, probe ID
`django-pyturso.driver-contract`, and probe revision `phase-0a-v1`. The full
function inventory and exact error messages remain in its JSON output; this
document keeps the reviewed conclusions compact.

## Current platform matrix

Remote evidence last refreshed on 2026-07-14 from
[Python package run 29308634115](https://github.com/btfranklin/django-pyturso/actions/runs/29308634115)
for commit `779d2b301fcdbf578dd8200f55230ba2f028b42f`.

| OS/kernel | Architecture | Python | Django | `pyturso` | Connected engine | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Darwin 25.5.0 | arm64 | CPython 3.14.6 | 6.0.7 | 0.6.1 | 3.50.4 | Local Phase 0A probe passed |
| Linux 6.12.76-linuxkit | arm64 | CPython 3.14.6 | 6.0.7 | 0.6.1 | 3.50.4 | Disposable Docker probe passed |
| Linux 6.12.76-linuxkit | x86_64 | CPython 3.14.6 | 6.0.7 | 0.6.1 | 3.50.4 | Docker probe passed under emulation |
| Linux 6.17.0-1018-azure | x86_64 | CPython 3.14.6 | 6.0.7 | 0.6.1 | 3.50.4 | Native `ubuntu-24.04`, locked, passed |
| Linux 6.17.0-1018-azure | x86_64 | CPython 3.14.6 | 6.0.7 | 0.6.1 | 3.50.4 | Native `ubuntu-24.04`, minimum, passed |
| Windows 10.0.26100 | AMD64 | CPython 3.14.6 | 6.0.7 | 0.6.1 | 3.50.4 | Native `windows-2025`, locked, passed |
| Windows 10.0.26100 | AMD64 | CPython 3.14.6 | 6.0.7 | 0.6.1 | 3.50.4 | Native `windows-2025`, minimum, passed |

The Darwin and Linux arm64 rows are native to the host architecture. The Linux
x86_64 row used Docker's architecture emulation, so it proves wheel resolution
and the probe contract but is not a substitute for native-runner timing,
locking, or recovery evidence. The remote run's four reviewed artifacts now
provide that native Linux/Windows evidence; see
[`remote-platform-matrix.json`](remote-platform-matrix.json) for their artifact
identities, digests, and wheel tags. The matrix must not hide a failing cell
with `continue-on-error`.

Local process details were Darwin kernel
`25.5.0: Tue Jun 9 22:28:29 PDT 2026; xnu-12377.121.10~1/RELEASE_ARM64_T6030`,
processor `arm`, timezone `MST`, and locale `C.UTF-8`.

Both Linux probes ran from the read-only checkout in disposable
`python:3.14-slim` containers. PDM resolved the committed production lock into
container-local environments. They reported Linux kernel `6.12.76-linuxkit`,
timezone `UTC`, locale `C`/`UTF-8`, the same connected engine and function
inventory (245 rows, 227 names), the same selected capability results, passing
999/1000/32766/32767 parameter trials, and safe disposable file cleanup. The
resolved pyturso wheels were `manylinux2014_aarch64` and
`manylinux2014_x86_64`, respectively.

## Distribution and wheel evidence

| Distribution | Installed version | Wheel tag | Generator | Pure Python |
| --- | --- | --- | --- | --- |
| Django | 6.0.7 | `py3-none-any` | setuptools 83.0.0 | Yes |
| `pyturso` | 0.6.1 | `cp314-cp314-macosx_11_0_arm64` | maturin 1.13.3 | No |

The installed distributions did not contain `direct_url.json`; their wheel
metadata and installed versions are therefore the local artifact identity.

Historical upstream references were resolved directly rather than relying on a
mutable branch:

- Django tag `6.0.7`: annotated tag object
  `c7b3ee972494d7d9903db3db7cbe2e9ffe20f457`, peeled commit
  [`e2a424605ac2e7e6e799496542fb2997207e2f23`](https://github.com/django/django/commit/e2a424605ac2e7e6e799496542fb2997207e2f23).
- Turso tag `v0.6.1`: commit
  [`45251e60bc6b06d62ae14402fdf51986af07251e`](https://github.com/tursodatabase/turso/commit/45251e60bc6b06d62ae14402fdf51986af07251e).

These references establish the exact upstream release identities consulted for
this probe. They do not yet claim that backend source was copied or adapted;
source provenance is maintained separately.

## Public DB-API surface

The top-level `turso` module reported DB-API level `2.0`, `threadsafety = 1`,
`paramstyle = "qmark"`, and no PEP 249 `Binary` constructor. The public
synchronous connect signature was:

```text
(database: str, *, experimental_features: str | None = None,
 vfs: str | None = None, encryption: EncryptionOpts | None = None,
 isolation_level: str | None = "DEFERRED",
 extra_io: Callable[[], None] | None = None) -> Connection
```

All standard DB-API exception classes were present. `InterfaceError` derives
directly from `Error`; `DataError`, `OperationalError`, `IntegrityError`,
`InternalError`, `ProgrammingError`, and `NotSupportedError` derive from
`DatabaseError`, which derives from `Error`. A duplicate unique value raised
`turso.lib.IntegrityError`. A competing file write raised
`turso.lib.OperationalError` with `database is locked`.

The connection exposed `in_transaction`, `isolation_level`, `autocommit`,
cursor creation, execute methods, commit, rollback, and close. It did not expose
`backup`, `create_function`, `create_aggregate`, `create_collation`, `getlimit`,
`setlimit`, or `set_authorizer`.

A research-only isolated PDM probe of `pyturso` 0.7.0rc22 on 2026-07-13 also
reported DB-API level `2.0`, `threadsafety = 1`, `paramstyle = "qmark"`, and no
top-level `turso.Binary`. That prerelease is outside the supported dependency
range and does not change the v1 binary-payload exclusion.

Although the declared parameter style is qmark, the driver accepted both a
two-element qmark tuple and a named-binding mapping; both `2 + 3` probes
returned `5`. Backend-generated SQL should still use its documented qmark
contract unless a separate decision establishes a need for named bindings.

## Connected engine and capability inventory

The module metadata reported SQLite `3.45.0` and `(3, 45, 0)`, while
`SELECT sqlite_version()` on the connection returned `3.50.4`. Connected
engine metadata is therefore the only observed value suitable for enforcing an
engine floor.

`PRAGMA function_list` returned 245 rows covering 227 distinct names. Read-only
trials made two important qualifications to that catalog:

| Capability trial | Local result |
| --- | --- |
| Native `REGEXP` operator | Passed |
| `uuid7()` | Passed; returned 16 bytes |
| `time_now()` | Passed; returned 13 bytes |
| Vector cosine distance | Passed |
| `generate_series(1, 3)` | Passed, though not listed by `function_list` |
| `regexp_like()` | Absent: `no such function` |
| `percentile()` | Absent: `no such function` |

Consequently, `PRAGMA function_list` is useful read-only evidence for scalar
and aggregate names but is not a complete inventory of table-valued modules.
Research and CI may retain explicit behavior trials. Application connection
startup must not run this broader trial set.

## Pragma evidence

| Pragma | Local query result |
| --- | --- |
| `foreign_keys` | Accepted |
| `foreign_key_list` | Accepted |
| `journal_mode` | Accepted; `wal` |
| `table_info` / `table_xinfo` | Accepted |
| `index_list` / `index_info` | Accepted |
| `compile_options` | Rejected as an invalid pragma name |
| `defer_foreign_keys` | Rejected as an invalid pragma name |
| `legacy_alter_table` | Rejected as an invalid pragma name |
| `max_variable_number` | Rejected as an invalid pragma name |

An empty table or index result means the pragma syntax was accepted against the
probe's intentionally absent schema object; it is not yet a semantic
introspection test.

## Transaction and cursor basics

On an explicit-autocommit connection, `in_transaction` was initially false,
became true after `BEGIN`, and returned to false after `commit()`. A savepoint,
insert, rollback-to, and release sequence preserved only the row inserted
before the explicit transaction. `INSERT ... RETURNING` returned `(1, "kept")`.

After `close()`, both direct execution and execution through a newly requested
cursor raised `turso.lib.DatabaseError` with `Internal error: Connection
closed`. Repeated `commit()` and `rollback()` calls returned normally. These
are raw-driver facts only; Django wrapper close policy is specified by the
separate state-machine evidence.

## Disposable file lifecycle and locking

The local file probe observed:

- Connecting created `probe.sqlite3` and `probe.sqlite3-wal`; journal mode was
  `wal`.
- A second connection immediately read the first connection's committed row.
- While the first connection held `BEGIN IMMEDIATE` and an uncommitted insert,
  the second connection still saw only the committed row.
- A competing insert from the second connection raised
  `turso.lib.OperationalError: database is locked`.
- `PRAGMA wal_checkpoint(PASSIVE)` returned `(0, 3, 3)` and
  `PRAGMA wal_checkpoint(TRUNCATE)` returned `(0, 0, 0)`.
- After both connections closed, the main file was 8192 bytes and the WAL file
  remained present at zero bytes. The temporary directory was then removed.

The reviewed native Linux and Windows artifacts independently reproduced these
file, lock, close, sidecar, and cleanup observations for both committed
resolutions. Crash recovery, checkpoint policy, sidecar backup rules, and
multi-process access require later dedicated evidence.

## Parameter floor

Parameterized `VALUES` statements containing 999, 1000, 32766, and 32767
qmark parameters all succeeded locally and returned the expected count.
All required native locked/minimum cells now reproduce these results. v1 keeps
999 as its intentional conservative cross-platform floor; raising it requires a
separate compatibility decision rather than merely more evidence.

## Regression coverage

`tests/driver_contract/test_driver_probe.py` invokes the real CLI in both
modes. It asserts schema identity and safe default scope, connected-engine and
public DB-API basics, bindings, `RETURNING`, transaction state, savepoint
rollback, exception types, closed-connection behavior, WAL mode,
two-connection isolation, write locking, the 999-parameter floor, and temporary
directory cleanup.
