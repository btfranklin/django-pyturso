"""Database client contract tests."""

from typing import cast

import pytest
from django.db import NotSupportedError

from django_pyturso.base import DatabaseWrapper
from django_pyturso.client import DatabaseClient
from tests.support import wrapper_settings

pytestmark = pytest.mark.core


def test_client_rejects_external_shell() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "probe")
    client = cast(DatabaseClient, wrapper.client)
    with pytest.raises(NotSupportedError, match="doesn't provide dbshell"):
        client.runshell(["--version"])
