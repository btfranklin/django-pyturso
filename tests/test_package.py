"""Package metadata checks for the importable backend."""

from email.message import EmailMessage

import pytest

import django_pyturso
from scripts.verify_packages import _verify_metadata_consistency


def test_package_imports() -> None:
    assert django_pyturso.__doc__ == "Django database backend for embedded Turso."


def _metadata(version: str) -> EmailMessage:
    message = EmailMessage()
    message["Name"] = "django-pyturso"
    message["Version"] = version
    message["Requires-Python"] = ">=3.14"
    message["License-Expression"] = "MIT"
    message["Requires-Dist"] = "Django>=6.0.7"
    message["Requires-Dist"] = "pyturso>=0.7.0"
    return message


def test_distribution_metadata_must_match_each_other_and_release_version() -> None:
    wheel = _metadata("1.2.3")
    sdist = _metadata("1.2.3")
    _verify_metadata_consistency(wheel, sdist, expected_version="1.2.3")

    with pytest.raises(RuntimeError, match="release tag version"):
        _verify_metadata_consistency(wheel, sdist, expected_version="1.2.4")

    mismatched_sdist = _metadata("1.2.4")
    with pytest.raises(RuntimeError, match="disagree on Version"):
        _verify_metadata_consistency(wheel, mismatched_sdist, expected_version=None)
