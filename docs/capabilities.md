# Django capability declarations

Django requires every database backend to provide a `DatabaseFeatures` class.
Despite the framework module name, these values are static compatibility facts,
not runtime switches: applications cannot enable, disable, or override backend
behavior through them.

`src/django_pyturso/features.py` explicitly declares every public Django 6.0.7
database capability. The declarations are fixed for a released backend version,
covered by compatibility tests, and never changed by connection probes,
environment variables, database settings, or installed engine functions.

Turso-specific ORM integrations are outside the v1 package surface. When a
future integration is ready, it must ship as an ordinary documented API with a
complete support contract; it must not be hidden behind runtime configuration.
