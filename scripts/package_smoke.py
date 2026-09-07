"""Exercise an installed django-pyturso package in a temporary project."""

from __future__ import annotations

import sys
from pathlib import Path

import django
from django.conf import settings


def main() -> None:
    database_name = sys.argv[1]
    settings.configure(
        DATABASES={"default": {"ENGINE": "django_pyturso", "NAME": database_name}},
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes"],
        SECRET_KEY="smoke",
        USE_TZ=True,
    )
    django.setup()

    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection, transaction

    import django_pyturso

    assert Path(django_pyturso.__file__).is_relative_to(Path.cwd())
    call_command("migrate", verbosity=0)
    User = get_user_model()
    User.objects.create_user(username="installed-user", password="secret")
    try:
        with transaction.atomic():
            User.objects.create_user(username="rolled-back")
            raise RuntimeError("rollback")
    except RuntimeError:
        pass
    assert list(User.objects.values_list("username", flat=True)) == ["installed-user"]
    with connection.cursor() as cursor:
        cursor.execute("SELECT 42")
        assert cursor.fetchone() == (42,)
    assert connection.connection.__class__.__module__ == "turso.lib"
    connection.close()
    if database_name != ":memory:":
        database = Path(database_name)
        database.unlink()
        for sidecar in database.parent.glob(database.name + "-*"):
            sidecar.unlink()


if __name__ == "__main__":
    main()
