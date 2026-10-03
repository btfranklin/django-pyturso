"""Explicitly selected live-server lifecycle case."""

from urllib.request import urlopen

from django.test import LiveServerTestCase

from tests.project.models import Entry


class BackendLiveServerCase(LiveServerTestCase):
    def test_server_thread_can_query_a_file_database(self) -> None:
        entry = Entry.objects.create(pk=1, title="first value")

        with urlopen(f"{self.live_server_url}/entry-title/", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.read().decode(), "first value")

        entry.title = "updated value"
        entry.save(update_fields=["title"])

        with urlopen(f"{self.live_server_url}/entry-title/", timeout=5) as response:  # noqa: S310
            self.assertEqual(response.read().decode(), "updated value")
