"""Create and remove real tables for each selected Django regression."""

from collections.abc import Iterator

import pytest
from django.db import connection
from pytest_django.plugin import DjangoDbBlocker

from tests.django_regressions.models import NamedRank, Record


@pytest.fixture(autouse=True)
def regression_tables(django_db_blocker: DjangoDbBlocker) -> Iterator[None]:
    with django_db_blocker.unblock():
        assert connection.settings_dict["ENGINE"] == "django_pyturso"
        with connection.schema_editor() as editor:
            editor.create_model(Record)
            editor.create_model(NamedRank)
        try:
            yield
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(NamedRank)
                editor.delete_model(Record)
