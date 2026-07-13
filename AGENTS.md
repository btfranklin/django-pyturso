# Repository Guide

## Start Here

- Package purpose and quickstart: `README.md`
- Backend boundaries and dependency direction: `docs/architecture.md`
- Initial implementation contract: `docs/design/backend-contract.md`
- Deferred native CI procedure: `NATIVE_PLATFORM_CI.md`
- Documentation map: `docs/index.md`

## Project Shape

- Importable backend package: `src/django_pyturso/`
- Tests: `tests/`
- Package and tooling configuration: `pyproject.toml`

## Commands

- Install: `pdm install --group dev`
- Lint: `pdm run lint`
- Type check: `pdm run typecheck`
- Test: `pdm run test`
- Full check: `pdm run check`

## Working Rules

- Use PDM; direct dependencies use `>=` constraints.
- Target Django 6 and local embedded Turso through `pyturso` only.
- Implement Django's documented backend interface directly. Do not add shims,
  aliases, monkey patches, cloud transports, or an SQLite fallback.
- Keep Django compatibility claims covered by tests and update `docs/` whenever
  supported behavior or configuration changes.
