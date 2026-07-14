# Native Platform CI Deployment Guide

## Status and boundary

The native platform run is intentionally deferred until this repository has a
GitHub deployment. The workflow design is complete, but no remote workflow has
been executed and no native Linux x86_64 or Windows x86_64 result is claimed.
The existing macOS arm64, Linux arm64, and emulated Linux x86_64 evidence remains
recorded in `docs/design/evidence/driver-platform-matrix.md`.

This procedure is verification only. It must not publish a package, create a
tag or GitHub Release, upload to PyPI, or invoke any release workflow.

## Deployment prerequisites

Before running the matrix:

1. Create or select the authorized GitHub repository and push the prepared
   source only after explicit approval.
2. Confirm GitHub Actions is enabled and GitHub-hosted `ubuntu-24.04` and
   `windows-2025` runners are available as native x86_64 machines.
3. Confirm CPython 3.14 is available through `actions/setup-python` on both
   runners.
4. Keep `pdm.lock` and `pdm.min.lock` committed and synchronized with
   `pyproject.toml`. Do not resolve dependencies ad hoc in the workflow.
5. Do not add publication credentials or repository write permissions. The
   package workflow requires only read access to repository contents.

The prepared matrix lives in `.github/workflows/python-package.yml`. Its
ordinary pull-request or `main` push trigger is sufficient; do not use a tag.

## Required native cells

| Runner | Resolution | Lockfile | Required outcome |
| --- | --- | --- | --- |
| `ubuntu-24.04` | locked | `pdm.lock` | Complete pass and evidence artifact |
| `ubuntu-24.04` | minimum | `pdm.min.lock` | Complete pass and evidence artifact |
| `windows-2025` | locked | `pdm.lock` | Complete pass and evidence artifact |
| `windows-2025` | minimum | `pdm.min.lock` | Complete pass and evidence artifact |

The macOS cells are useful regression evidence but do not replace either native
x86_64 platform. Emulated Linux results also do not satisfy a native cell.
`continue-on-error` must remain absent and the matrix must retain
`fail-fast: false` so every cell produces an independent result.

## Commands and artifacts

Each cell must perform the prepared sequence:

```console
pdm sync -L <pdm.lock-or-pdm.min.lock> -G dev --clean
pdm list --freeze
pdm run check
pdm run python scripts/probes/driver_contract.py \
  --include-disposable-mutations \
  --output driver-platform.json
```

The workflow uploads `driver-platform.json` as
`driver-platform-<runner>-<resolution>`. Preserve the workflow run URL, run ID,
commit SHA, runner image/version, complete test result, dependency listing, and
artifact digest with the downloaded JSON.

For every required cell, the combined workflow record and JSON must establish:

- the native operating system and x86_64 architecture;
- CPython, Django, and `pyturso` versions;
- connected Turso engine version and public DB-API surface;
- successful parameter trials through the documented floor;
- disposable file creation, locking, close, sidecar, and cleanup behavior; and
- a passing exact test result from the same lockfile resolution, retained in
  the workflow job log.

## Acceptance and repository update

The deferred evidence is complete only when all four required native cells pass
for the same commit. Review the downloaded JSON files rather than relying only
on green job summaries. Then:

1. Add the four reviewed rows, run identifiers, commit SHA, and artifact digests
   to `docs/design/evidence/driver-platform-matrix.md`.
2. Update the release evidence generator so `remote_matrix_executed` becomes
   true only from durable reviewed evidence, not from a manually edited claim.
3. Regenerate and validate the local release evidence index against the exact
   reviewed commit and artifacts.
4. Keep publication, tagging, and release creation as separately authorized
   actions.

If any cell fails, retain its logs and JSON if available, leave
`remote_matrix_executed` false, fix the underlying issue locally, and rerun the
entire four-cell native matrix on one new commit.
