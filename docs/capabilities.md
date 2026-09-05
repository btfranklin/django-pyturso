# Django capability declarations

Django requires every database backend to provide a `DatabaseFeatures` class.
Despite the framework module name, these values are static compatibility facts,
not runtime switches: applications cannot enable, disable, or override backend
behavior through them.

`src/django_pyturso/features.py` contains the backend's deliberate capability
overrides. Focused tests protect the fixed limits and high-risk support
boundaries; ordinary Django defaults remain ordinary defaults. These values are
never changed by connection state, environment variables, database settings,
or installed engine functions.

Temporal operations reject unsupported timezones before SQL execution. The
backend sets Django's `has_zoneinfo_database` flag to true so a valid `NULL`
truncation result does not trigger Django's missing-timezone-data error. This
flag does not enable named timezone conversion; only UTC or no conversion is
supported.

Time extraction preserves Python's six-digit microsecond precision. Its SQL
text representation matches stored `TimeField` values and bound time values.

Turso-specific ORM integrations are outside the v1 package surface. When a
future integration is ready, it must ship as an ordinary documented API with a
complete support contract; it must not be hidden behind runtime configuration.
