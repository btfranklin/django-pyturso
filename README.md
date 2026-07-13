# django-pyturso

`django-pyturso` is a Django database backend for the embedded Turso database
engine exposed by `pyturso`. It will let a Django project use its ordinary ORM,
migrations, forms, admin, and transaction APIs against a local Turso database
file.

This repository is deliberately scoped to embedded, local Turso. It does not
provide Turso Cloud access, libSQL-over-HTTP support, replication, sync, or a
project-specific compatibility layer.

## Status

The pre-release backend is implemented and passes the local ORM, migration,
transaction, auth/admin/forms, test-runner, differential, selected Django
upstream, stress, performance-correctness, security, and clean-install package
lanes. The local release-candidate preparation is complete; publication and
remote deployment remain separate, explicitly authorized operations.

The v1 contract intentionally excludes writing non-NULL Django `BinaryField`
values because the stable `pyturso` 0.6 line does not expose the required PEP
249 `Binary()` constructor. The backend deliberately does not patch or wrap the
real `turso` module. See the compatibility document before evaluating the
package.

## Quickstart

```bash
pdm install --group dev
pdm run check
```

Configure a Django database with no external service:

```python
DATABASES = {
    "default": {
        "ENGINE": "django_pyturso",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

The package requires CPython 3.14 or later and targets Django 6 and embedded
local Turso through `pyturso`. Current verification evidence was produced on
CPython 3.14. Cloud transports, remote sync, SQLite fallbacks, compatibility
shims, and experimental engine features are excluded.

## Navigation

- [Architecture](docs/architecture.md)
- [Backend contract](docs/design/backend-contract.md)
- [Configuration](docs/configuration.md)
- [Compatibility status](docs/compatibility.md)
- [Test runner](docs/test-runner.md)
- [Testing and evidence](docs/testing.md)
- [Security and supply chain](docs/security.md)
- [Performance](docs/performance.md)
- [Post-v1 roadmap](docs/roadmap.md)
- [Native platform CI deployment guide](NATIVE_PLATFORM_CI.md)
- [Review policy](docs/review-policy.md)
- [Documentation index](docs/index.md)
- [Agent operating guide](AGENTS.md)
