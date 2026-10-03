"""Django transaction regressions. See docs/testing/django-regressions.md."""

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.transaction import TransactionManagementError

from tests.django_regressions.models import Record

pytestmark = pytest.mark.core


def test_force_atomic_rollback() -> None:
    with transaction.atomic():
        Record.objects.create(name="Tintin")
        assert not transaction.get_rollback()
        transaction.set_rollback(True)
    assert not Record.objects.exists()


def test_recover_merged_atomic_with_manual_savepoint() -> None:
    with transaction.atomic():
        row = Record.objects.create(name="Tintin")
        sid = transaction.savepoint()
        with pytest.raises(DatabaseError):
            with transaction.atomic(savepoint=False):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT no_such_col FROM django_regression_record")
        assert transaction.get_rollback()
        transaction.set_rollback(False)
        transaction.savepoint_rollback(sid)
    assert list(Record.objects.all()) == [row]


def test_integrity_error_blocks_queries_until_atomic_rollback() -> None:
    original = Record.objects.create(name="Haddock")
    with transaction.atomic():
        duplicate = Record(id=original.pk, name="Calculus")
        with pytest.raises(IntegrityError):
            duplicate.save(force_insert=True)
        with pytest.raises(TransactionManagementError) as caught:
            duplicate.save(force_update=True)
        assert isinstance(caught.value.__cause__, IntegrityError)
    assert Record.objects.get(pk=original.pk).name == "Haddock"
