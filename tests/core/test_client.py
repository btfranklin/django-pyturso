"""Database client contract tests."""

import pytest
from django.db import NotSupportedError

from django_pyturso.base import DatabaseWrapper
from tests.support import wrapper_settings

pytestmark = pytest.mark.core


def test_client_rejects_external_shell() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "probe")
    client = wrapper.client
    with pytest.raises(NotSupportedError, match="doesn't provide dbshell"):
        client.runshell(["--version"])
