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

Turso-specific ORM integrations are outside the v1 package surface. When a
future integration is ready, it must ship as an ordinary documented API with a
complete support contract; it must not be hidden behind runtime configuration.
