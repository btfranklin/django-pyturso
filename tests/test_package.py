"""Release-floor checks for the package namespace."""

import gzip
from email.message import EmailMessage
from pathlib import Path

import pytest

import django_pyturso
from scripts.build_distributions import normalize_sdist
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


def test_sdist_gzip_normalization_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    payload = b"deterministic tar payload"
    first.write_bytes(gzip.compress(payload, mtime=1))
    second.write_bytes(gzip.compress(payload, mtime=2))

    normalize_sdist(first, mtime=123)
    normalize_sdist(second, mtime=123)

    assert first.read_bytes() == second.read_bytes()
    assert gzip.decompress(first.read_bytes()) == payload
