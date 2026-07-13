"""Fixture and serialized-rollback paths for Django's own runner."""

from django.test import TransactionTestCase

from .models import Entry


class SerializedRollbackCase(TransactionTestCase):
    fixtures = ["entries.json"]
    serialized_rollback = True

    def test_fixture_is_loaded(self) -> None:
        self.assertEqual(Entry.objects.get(pk=100).title, "fixture entry")
        Entry.objects.create(title="transient")

    def test_fixture_is_restored_without_prior_test_data(self) -> None:
        self.assertEqual(Entry.objects.get(pk=100).title, "fixture entry")
        self.assertFalse(Entry.objects.filter(title="transient").exists())
