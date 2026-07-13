"""Explicitly selected live-server lifecycle case."""

from urllib.error import HTTPError
from urllib.request import urlopen

from django.test import LiveServerTestCase


class BackendLiveServerCase(LiveServerTestCase):
    def test_server_thread_can_query_a_file_database(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.live_server_url, timeout=5)  # noqa: S310
        self.assertEqual(raised.exception.code, 404)
