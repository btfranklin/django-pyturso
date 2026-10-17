# Security

`django-pyturso` is a local embedded database backend. Its security boundary is
the database file and the SQL passed between Django and `pyturso`; it has no
network, cloud, synchronization, credential, or remote-transport surface.

## Database paths

`DATABASES[alias]["NAME"]` follows Django's normal filesystem-path semantics.
The backend accepts relative paths, absolute paths, `os.PathLike` values, and
exactly `:memory:`. It rejects URLs and `file:` URIs. The operating system and
`pyturso` enforce filesystem access and permissions, so applications must choose
a trusted path, set appropriate permissions, and keep database, WAL, and MVCC
log files out of web roots.

`pyturso` 0.7.0 reports directory and permission open failures as an extension
`turso.IoError` outside its PEP 249 exception hierarchy. The backend translates
only that driver defect to Django `OperationalError` and leaves no connected
handle behind.

## SQL and dependencies

Django values are passed as bound parameters. The backend's placeholder
conversion preserves quoted identifiers, comments, and literal text so they
cannot create or consume bindings.

GitHub dependency review checks pull requests that change runtime dependencies,
and CodeQL scans the Python and workflow source.
The package requires `sqlparse>=0.6.0` to exclude releases with known SQL parser
denial-of-service defects.

Run `pdm run audit` to check the locked runtime dependencies against PyPI's
advisory data. This command checks the lockfile, exports exact versions
through PDM, then queries PyPI's release JSON API. It does not resolve or install
packages. It excludes development tools and the local package.
Platform markers select the runtime dependencies for the current platform.
Known vulnerabilities, incomplete collection, and service errors fail the check.
Each response must identify the requested package and version and contain a
valid vulnerability list. Invalid advisory records, withdrawal timestamps,
duplicate JSON keys, oversized responses, and redirects also fail the check.
Only advisories with a valid withdrawal timestamp are excluded.
The command requires network access; the offline aggregate checks do not run it.

CI runs this check on pull requests and pushes to `main`, for both locked and
current runtime dependencies. Release verification also runs it on each
supported platform before package publication can proceed.
Releases use PyPI Trusted Publishing; no PyPI token is stored in this repository.
