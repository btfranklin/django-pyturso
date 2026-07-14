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

## Dependency policy

Pull requests review new runtime dependencies and licenses. A reported security
issue that affects the package must be fixed before release. See
`docs/security.md` for the package's local-database boundary.
