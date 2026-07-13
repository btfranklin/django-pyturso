# Security Policy

## Supported versions

Security fixes are provided for the newest released `django-pyturso` minor
line. The pre-release repository does not yet make a stable support promise.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a
public issue containing exploit details, credentials, private database content,
or unreleased advisory information.

Reports should include the affected version, Python/Django/`pyturso` versions,
platform, minimal reproduction, impact, and any known mitigation. Maintainers
will acknowledge receipt, coordinate validation and remediation privately, and
publish an advisory when users can act safely.

## Dependency and exception policy

Pull requests review new runtime dependencies and licenses; release candidates
run dependency and source security scans. A blocking issue must be fixed before
release. An accepted non-blocking exception must identify the package,
advisory or license, affected range, actual exposure, mitigation, owner,
approval, and expiry date in
`tests/manifests/security-exceptions.toml`. Workflow-only exceptions are not
accepted, and expired exceptions fail the release gate. The full mechanical
policy is documented in `docs/security.md`.
