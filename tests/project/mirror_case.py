"""Explicitly selected file-backed test-mirror case."""

from django.test import TransactionTestCase

from .models import Entry


class FileMirrorCase(TransactionTestCase):
    databases = {"default", "replica"}

    def test_replica_resolves_to_the_primary_file(self) -> None:
        Entry.objects.using("default").create(title="mirrored")
        self.assertEqual(Entry.objects.using("replica").get().title, "mirrored")
