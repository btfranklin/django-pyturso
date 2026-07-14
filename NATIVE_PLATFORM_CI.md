# Native Platform CI Evidence

## Verified remote evidence

The native Linux x86_64 and Windows x86_64 matrix completed successfully in
[Python package run 29308634115](https://github.com/btfranklin/django-pyturso/actions/runs/29308634115)
for commit `779d2b301fcdbf578dd8200f55230ba2f028b42f`. All locked and minimum
resolution cells passed, and their four driver-contract artifacts were reviewed.
The durable run, artifact, platform, wheel, and version record is
`docs/design/evidence/remote-platform-matrix.json`; its structure is validated
before release evidence may claim that the remote matrix ran.

This verification did not publish a package, create a tag or GitHub Release, or
upload to PyPI.

## Re-execution prerequisites

Before replacing this evidence with a later run:

1. Confirm GitHub Actions is enabled and GitHub-hosted `ubuntu-24.04` and
   `windows-2025` runners are available as native x86_64 machines.
2. Confirm CPython 3.14 is available through `actions/setup-python` on both
   runners.
3. Keep `pdm.lock` and `pdm.min.lock` committed and synchronized with
   `pyproject.toml`. Do not resolve dependencies ad hoc in the workflow.
4. Do not add publication credentials or repository write permissions. The
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

## Reviewed acceptance record

All four required native cells passed for the same commit. The reviewed
artifacts have these GitHub digests:

| Runner | Resolution | Artifact digest |
| --- | --- | --- |
| `ubuntu-24.04` | locked | `sha256:5b3138a68f70cc97927c5372e6cdf40d26a3d5c23579d52ffba40d683860b688` |
| `ubuntu-24.04` | minimum | `sha256:e37fc87b01886f3c21cc10c151471d7bb52ff5fafb5ba4fd406d1b3a7ff3b8d8` |
| `windows-2025` | locked | `sha256:af9db978426fa61f5bf010f76173383f99084bde9e5dd9229bf75ad293dcd353` |
| `windows-2025` | minimum | `sha256:98b6478c38f95cda8769851183342b6b66f4375cbb58d3f8a7f1d3660afd167b` |

For a future rerun, review all four new artifacts before replacing the durable
record. A failed or incomplete replacement must not alter the verified record.
