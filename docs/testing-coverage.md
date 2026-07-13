# Branch coverage and mutation policy

## Purpose

Coverage and mutation testing are ratchets, not substitutes for contract
evidence. The coverage lane measures branches and publishes machine-readable,
XML, terminal, and browsable HTML artifacts. The mutation lane challenges only
critical backend modules reached by focused tests.

No source line or branch is excluded by this policy. A future exclusion must
carry a narrow technical reason and explicit review.

## Commands

Measure without enforcing the checked-in floors:

```console
pdm run coverage-measure
```

Measure and enforce the ratchets:

```console
pdm run coverage-check
```

Both commands run the complete offline local profile except the separately
managed `upstream` and `performance` markers. Stress, property, fault,
differential, integration, security, and ordinary contract tests are included.
The runner always attempts to write reports after pytest returns. If pytest
fails, it returns that failure after report generation and does not evaluate
coverage floors.

Artifacts are written to:

- `artifacts/coverage/coverage.json`
- `artifacts/coverage/coverage.xml`
- `artifacts/coverage/html/index.html`

## Initial measured ratchets

The initial 2026-07-13 measurement used CPython 3.14.6, Django 6.0.7,
`pyturso` 0.6.1, and connected Turso 3.50.4 on Darwin arm64. Coverage.py was
configured with `branch = true`; percentages below are its branch-inclusive
line-and-arc metric rather than statement-only coverage.

| Scope | Measured | Checked-in floor | Release target |
| --- | ---: | ---: | ---: |
| Repository | 100.00% | 100.00% | At least 95% |
| `base.py` | 100.00% | 100.00% | Complete critical coverage |
| `operations.py` | 100.00% | 100.00% | Complete critical coverage |
| `schema.py` | 100.00% | 100.00% | Complete critical coverage |

These are measured Phase 2 ratchets, not release-readiness claims. Raising a
floor after adding tests is normal. Lowering one requires a documented
contract/risk review and must never be done merely to make CI pass.

The clean ratchet run passed all 323 selected tests; ten upstream or
performance cases were deselected by the profile. The generated reports and
floor check completed successfully.

## Critical uncovered-branch disposition

Every runtime backend module now has complete statement and branch coverage:
1,387 statements and 526 branches with no missing line, partial branch, or
coverage exclusion. Mutation results remain an independent gate; complete
coverage does not imply that every assertion is mutation-sensitive.

## Mutation tool and scope

`mutmut>=3.6.0` runs under CPython 3.14.6 in the PDM environment. Its checked-in
configuration targets:

- `src/django_pyturso/base.py`
- `src/django_pyturso/operations.py`
- `src/django_pyturso/schema.py`

All mutable lines in those modules are included. An initial attempt to use
mutmut's `mutate_only_covered_lines` optimization generated empty mutation
metadata for this `src/` layout under mutmut 3.6.0, so the policy does not rely
on that optimization. Uncovered logic must appear honestly as `no tests` or a
survivor. Test association uses unit, core, property, and fault-injection
groups; upstream, performance, and stress tests are excluded from per-mutant
execution. Run the complete scheduled/manual lane with:

```console
pdm run mutation-critical
pdm run mutation-results
```

The release threshold is established from a complete run over the configured
critical modules. Every survivor in transaction, conversion, or schema logic requires review;
an unexplained survivor blocks release.

### Complete CPython 3.14 baseline

The final 2026-07-13 critical-module run generated 1,485 mutants: 1,340 were
killed, 143 reviewed non-behavioral mutants survived, and two mutations that
remove dependency-graph loop progress were repeatedly detected by the bounded
test timeout. The survivors comprise 37 equivalent mutations, 77 changes only
to non-contractual diagnostic text, two typing-only mutations, and 27 branches
unreachable under the fixed Django 6 and embedded-`pyturso` contract. No
behavior-changing survivor remains. The exhaustive checked-in review records
every non-killed name exactly once; an old generated workspace is never reused
as release evidence.
