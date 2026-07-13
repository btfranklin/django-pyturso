# Security and supply chain

`django-pyturso` is a local embedded database backend. Its privileged boundary
is the database file and the SQL passed between Django and `pyturso`; v1 has no
network, cloud, synchronization, credential, or remote transport surface.

## Database paths

`DATABASES[alias]["NAME"]` follows Django's normal filesystem-path semantics.
The backend accepts relative paths, absolute paths, `os.PathLike` values, and
exactly `:memory:`. It rejects URLs and `file:` URIs, but it does not sandbox a
path beneath the project directory, resolve traversal components, or prohibit
symlinks. The operating system and `pyturso` enforce filesystem access and
permissions. Tests cover traversal-shaped relative names, symlinks,
non-regular paths, and permission failures, including cleanup after a failed
open.

The audited `pyturso` 0.6.1 release reports directory and permission open
failures as an extension `turso.IoError` outside its PEP 249 exception
hierarchy. The backend translates only that confirmed driver defect to Django
`OperationalError`, retains the driver error as the exception cause, and leaves
no connected handle behind. See [Compatibility status](compatibility.md).

Applications remain responsible for choosing a trusted path, setting directory
and file permissions, excluding database files and WAL files from web roots,
and protecting backups. A database `NAME` must never come directly from an
untrusted request.

## SQL inputs and package boundaries

Django values are passed as bound parameters. Tests include quote-, comment-,
statement-, wildcard-, and literal-percent-shaped inputs, mapping parameters,
`executemany()`, regular-expression patterns, and identifiers quoted from model
metadata. FTS5 is not exposed by the audited embedded engine, so v1 has no FTS
query-input API; it must receive a new security review before support is added.

AST-based architecture tests scan only runtime Python syntax. They reject the
stdlib and Django SQLite backends, private driver imports, remote client
packages, dynamic imports, and driver monkey patches while allowing those names
in documentation and the explicitly isolated differential reference tests.

Run the local static security contract with:

```console
pdm run security-validate
pdm run security-test
```

## Dependency policy

Pull requests use GitHub dependency review for runtime dependency changes.
High and critical vulnerabilities fail that gate. Runtime licenses must match
the SPDX allowlist in `.github/dependency-review-config.yml`. GitHub dependency
review applies the allowlist to dependency changes, while the local validator
walks the installed production dependency graph and rejects unknown or
unapproved metadata. Release verification uses the committed PDM lock through:

```console
pdm run audit
pdm run sbom
```

The audit exports production dependencies from the committed `pdm.lock` into a
temporary requirements file, then rejects every reported advisory unless an
active advisory exception exists. The SBOM uses the same production-lock
export and writes a reproducible CycloneDX JSON document to
`dist/sbom.cdx.json`. Validation requires CycloneDX 1.6, the locked Django and
`pyturso` components, a complete component reference graph, and a root package
version equal to the built wheel and sdist. Release automation hashes and
attests the SBOM with the exact wheel and sdist; generating these files locally
does not publish them.

`tests/manifests/security-exceptions.toml` is the only exception store. An
exception must name the package, issue type (`advisory` or `license`), advisory
or license identifier, affected range, rationale, owner, compensating control,
approval date, and expiry date. Expired, incomplete, unknown, and duplicate
entries fail `pdm run security-validate`. The dependency-audit runner reads
active advisory identifiers directly from this manifest; workflow-only audit
exceptions are forbidden.

## Workflow policy

All workflow permissions default to read-only repository contents. A job may
elevate only the permission it needs: CodeQL can write security events, release
candidate preparation can write draft-release assets and attestations, and the
publication job can request a PyPI identity token. Pull-request tests receive no
publication secret or write permission.

Every third-party action reference uses a human-readable major release tag such
as `v7` or `v3`; minor, patch, and commit SHA pins are forbidden. The sole
exception is `pypa/gh-action-pypi-publish@release/v1`: PyPA does not publish a
`v1` tag and documents `release/v1` as its maintained major-line channel.
Dependabot proposes GitHub Actions updates for review. CodeQL scans the Python
and workflow source on pull requests, default-branch pushes, and a weekly
schedule.

The tag workflow refuses to proceed while `IMPLEMENTATION_PLAN.md` exists. It
requires locked/minimum platform checks on macOS, Linux, and Windows, a Linux
newest-compatible check, and the complete deep verification job before the
asset-building job can create a draft release. The final artifact check binds
wheel and sdist metadata to each other and to the signed tag version. Preparing
this workflow locally does not execute it or publish anything.

Before a published release can reach the Trusted Publishing step, the publish
workflow verifies the downloaded wheel and sdist attestations against this
repository, the release-candidate workflow identity, the signed tag ref, and
the checked-out commit digest. Hash verification alone is not treated as build
provenance.
