# v1 implementation council review

Reviewed working tree: local pre-release preparation on 2026-07-13. This review
did not publish, push, tag, create a release, or configure PyPI.

## Classification

- Major code change: yes — the complete Django backend contract, lifecycle,
  schema, SQL, tests, and release evidence were implemented.
- Major structural change: yes — backend modules, test architecture,
  traceability, performance, and release preparation were established.
- Required deep review: completed with independent correctness/lifecycle,
  architecture/boundary, and tests/contracts/release lenses.
- Structural-clarity review: completed as an explicit council fallback because
  the named dedicated elegance skill was unavailable in this environment.

## Finding disposition ledger

| Severity | Finding | Disposition and closure evidence |
| --- | --- | --- |
| Medium | Prefix-shaped column names could be falsely identified as JSON | Fixed. Introspection now parses exact `JSON_VALID()` identifier tokens; quoted/unquoted prefix regression passes. |
| Medium | Path-like `:memory:` opened in memory but followed file lifecycle branches | Fixed. Base and creation canonicalize with `os.fspath`; connection and test-lifecycle regressions pass. |
| Medium | Unsupported expressions were rejected by class-name strings | Fixed. Operations uses concrete Django expression classes and a same-name third-party control passes. |
| Medium | Transaction coordination mutated the external driver connection and tolerated a missing wrapper | Fixed. The mandatory reference is attached only to the backend-owned cursor wrapper; no silent path remains. |
| Low | Exact current-contract paths used compatibility-style attribute fallbacks | Fixed. Query limits, schema disposal, and DROP COLUMN declarations are direct. |
| Low | Production capability declarations contained test-only disposition machinery and a dynamic EXPLAIN property | Fixed. Evidence generation is test-owned and EXPLAIN support is static. |
| High | Draft-release assets could be created without the complete verification graph | Fixed. Preflight, platform, and deep verification are all prerequisites; the workflow refuses to run while the remaining-work plan exists. |
| Medium | Traceability accepted dead anchors and weak selectors | Fixed. Markdown anchors, AST nodes, IDs, modes, phases, and schema are validated; dead-reference tests pass. |
| Medium | The focused core command omitted core-path tests | Fixed for the command contract by selecting all of `tests/core`. |
| Medium | Reproducibility ignored the compressed sdist envelope | Fixed. The build normalizes the gzip envelope and compares exact wheel and `.tar.gz` bytes. |
| Medium | Wheel/sdist metadata and tag versions were not bound | Fixed. Both metadata files are compared and the workflow supplies the signed tag version. |
| Medium | Failed table remake could leave the live model primary-key flag mutated | Fixed. The temporary remake body uses a cloned field; injected failure and the 52-test schema/migration group pass. |
| Medium | SBOM was generated without schema/version/dependency binding | Fixed. CycloneDX 1.6, root artifact version, required runtime components, and dependency edges are validated. |
| Medium | Publish preparation verified hashes but not build provenance | Fixed in workflow preparation. Attestations are checked against repository, signer workflow, tag ref, and source digest before the publishing action. |

## Pressure points

- The Path-like memory sentinel classifier is duplicated in base and creation.
  Declined for v1: both copies are short, identical, and directly tested; a
  shared helper would add another ownership seam without changing behavior.
- Aggregate distinct handling retains a defensive `getattr` after an Aggregate
  type check. Declined as non-blocking and behaviorally harmless for v1.
- The test-core name selects the entire core directory rather than every test
  elsewhere carrying the marker. Declined because canonical fast/full gates run
  those tests and the command now matches its documented directory contract.

## Structural-clarity synthesis

The settled backend is legible and Django-native: connection and cursor
ownership is explicit, configuration fails closed, `DatabaseFeatures` contains
static framework declarations only, schema restoration is fail-closed, and
unsupported behavior is rejected at the narrowest public seam. Concrete Django
types, direct BaseDatabase* subclass hooks, exact driver provenance, and the
absence of runtime product switches should be protected.

No blocking correctness, architecture, contract, release-preparation, or
structural-clarity council finding remains. The separate driver/platform and
mutation gates remain governed by `IMPLEMENTATION_PLAN.md` until their own
evidence closes.
