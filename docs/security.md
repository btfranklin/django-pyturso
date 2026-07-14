# Security

`django-pyturso` is a local embedded database backend. Its security boundary is
the database file and the SQL passed between Django and `pyturso`; it has no
network, cloud, synchronization, credential, or remote-transport surface.

## Database paths

`DATABASES[alias]["NAME"]` follows Django's normal filesystem-path semantics.
The backend accepts relative paths, absolute paths, `os.PathLike` values, and
exactly `:memory:`. It rejects URLs and `file:` URIs. The operating system and
`pyturso` enforce filesystem access and permissions, so applications must choose
a trusted path, set appropriate permissions, and keep database and WAL files
out of web roots.

`pyturso` 0.7.0 reports directory and permission open failures as an extension
`turso.IoError` outside its PEP 249 exception hierarchy. The backend translates
only that driver defect to Django `OperationalError` and leaves no connected
handle behind.

## SQL and dependencies

Django values are passed as bound parameters. The backend's placeholder
conversion preserves quoted identifiers, comments, and literal text so they
cannot create or consume bindings.

GitHub dependency review checks pull requests that change runtime dependencies,
and CodeQL scans the Python and workflow source. Releases use PyPI Trusted
Publishing; no PyPI token is stored in this repository.
