"""Tests executed through Django's own test runner."""

from django.test import TestCase, TransactionTestCase

from .models import Entry


class EntryTestCase(TestCase):
    def test_orm_round_trip(self) -> None:
        entry = Entry.objects.create(title="testcase")
        self.assertEqual(Entry.objects.get(pk=entry.pk).title, "testcase")


class EntryTransactionTestCase(TransactionTestCase):
    reset_sequences = True

    def test_sequence_and_flush_path(self) -> None:
        entry = Entry.objects.create(title="transaction")
        self.assertEqual(entry.pk, 1)
