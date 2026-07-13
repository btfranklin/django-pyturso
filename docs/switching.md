# Switching from SQLite

Switching engines is an offline process boundary:

1. Stop every process that can access the database.
2. Back up the main database and its Turso sidecars.
3. Change `ENGINE` to `django_pyturso` and remove SQLite-only `OPTIONS`.
4. Run `manage.py check` and `manage.py migrate --plan`.
5. Test against a copy before applying migrations to the production file.

Do not mix SQLite and Turso access to the same live file across processes. To
roll back, stop all access again, restore the verified backup if any write or
migration occurred, change `ENGINE`, and rerun checks/tests before reopening
traffic.
