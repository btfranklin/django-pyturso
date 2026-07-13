"""Verify release archives and clean-install smoke behavior through PDM."""

from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
import tempfile
import zipfile
from email.message import Message
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NOTICE = "THIRD_PARTY_NOTICES.md"
FORBIDDEN_ARCHIVE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _artifacts() -> list[Path]:
    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError("dist/ must contain exactly one wheel and one sdist")
    return [wheels[0], sdists[0]]


def _archive_names(artifact: Path) -> list[str]:
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            return archive.namelist()
    with tarfile.open(artifact) as archive:
        return archive.getnames()


def _read_metadata(artifact: Path) -> Message:
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise RuntimeError(f"{artifact.name} must contain exactly one METADATA file")
            return BytesParser(policy=default).parsebytes(archive.read(names[0]))
    with tarfile.open(artifact) as archive:
        members = [member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")]
        if len(members) != 1:
            raise RuntimeError(f"{artifact.name} must contain exactly one PKG-INFO file")
        extracted = archive.extractfile(members[0])
        if extracted is None:
            raise RuntimeError(f"{artifact.name} PKG-INFO could not be read")
        return BytesParser(policy=default).parsebytes(extracted.read())


def _verify_archive(artifact: Path) -> Message:
    names = _archive_names(artifact)
    if not any(name.endswith(NOTICE) for name in names):
        raise RuntimeError(f"{artifact.name} does not contain {NOTICE}")
    if not any(
        name.endswith("/django_pyturso/base.py") or name == "django_pyturso/base.py"
        for name in names
    ):
        raise RuntimeError(f"{artifact.name} does not contain the backend package")
    if not any(
        name.endswith("/django_pyturso/py.typed") or name == "django_pyturso/py.typed"
        for name in names
    ):
        raise RuntimeError(f"{artifact.name} does not contain py.typed")
    for name in names:
        path = Path(name)
        if FORBIDDEN_ARCHIVE_PARTS.intersection(path.parts):
            raise RuntimeError(f"{artifact.name} contains cache path {name}")
        if path.suffix in {".pyc", ".db", ".sqlite", ".sqlite3"}:
            raise RuntimeError(f"{artifact.name} contains build debris {name}")
    if artifact.suffix == ".whl":
        if any(Path(name).parts[0] == "tests" for name in names):
            raise RuntimeError(f"{artifact.name} unexpectedly contains tests")
        metadata = _read_metadata(artifact)
        if metadata["Name"] != "django-pyturso":
            raise RuntimeError(f"{artifact.name} has incorrect project metadata")
        if metadata["Requires-Python"].strip() != ">=3.14":
            raise RuntimeError(f"{artifact.name} has incorrect Requires-Python")
        requirements = [value.replace(" ", "") for value in metadata.get_all("Requires-Dist", [])]
        if not any(
            value.startswith("Django") and ">=6.0.7" in value and "<7" in value
            for value in requirements
        ):
            raise RuntimeError(f"{artifact.name} has incorrect Django bounds")
        if not any(
            value.startswith("pyturso") and ">=0.6.1" in value and "<0.7" in value
            for value in requirements
        ):
            raise RuntimeError(f"{artifact.name} has incorrect pyturso bounds")
    return _read_metadata(artifact)


def _verify_metadata_consistency(
    wheel: Message, sdist: Message, *, expected_version: str | None
) -> None:
    for field in ("Name", "Version", "Requires-Python", "License-Expression"):
        if wheel[field] != sdist[field]:
            raise RuntimeError(f"wheel and sdist disagree on {field}")
    wheel_requirements = sorted(
        value.replace(" ", "") for value in wheel.get_all("Requires-Dist", [])
    )
    sdist_requirements = sorted(
        value.replace(" ", "") for value in sdist.get_all("Requires-Dist", [])
    )
    if wheel_requirements != sdist_requirements:
        raise RuntimeError("wheel and sdist disagree on Requires-Dist")
    if expected_version is not None and wheel["Version"] != expected_version:
        raise RuntimeError(
            f"artifact version {wheel['Version']!r} does not match release tag version "
            f"{expected_version!r}"
        )


def _clean_install(artifact: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="django-pyturso-package-") as directory:
        project = Path(directory)
        artifact_uri = artifact.resolve().as_uri()
        (project / "pyproject.toml").write_text(
            "\n".join(
                [
                    "[project]",
                    'name = "django-pyturso-smoke"',
                    'version = "0.0.0"',
                    'requires-python = ">=3.14"',
                    f'dependencies = ["django-pyturso @ {artifact_uri}"]',
                    "",
                ]
            )
        )
        smoke = project / "smoke.py"
        smoke.write_text(
            "\n".join(
                [
                    "import sys",
                    "from pathlib import Path",
                    "from django.conf import settings",
                    "database_name = sys.argv[1]",
                    "settings.configure(",
                    "    DATABASES={'default': "
                    "{'ENGINE': 'django_pyturso', 'NAME': database_name}},",
                    "    DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',",
                    "    INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes'],",
                    "    SECRET_KEY='smoke',",
                    "    USE_TZ=True,",
                    ")",
                    "import django",
                    "django.setup()",
                    "import django_pyturso",
                    "from django.contrib.auth import get_user_model",
                    "from django.core.management import call_command",
                    "from django.db import connection, transaction",
                    "assert Path(django_pyturso.__file__).is_relative_to(Path.cwd())",
                    "call_command('migrate', verbosity=0)",
                    "User = get_user_model()",
                    "User.objects.create_user(username='installed-user', password='secret')",
                    "try:",
                    "    with transaction.atomic():",
                    "        User.objects.create_user(username='rolled-back')",
                    "        raise RuntimeError('rollback')",
                    "except RuntimeError:",
                    "    pass",
                    "assert list(User.objects.values_list('username', flat=True)) "
                    "== ['installed-user']",
                    "with connection.cursor() as cursor:",
                    "    cursor.execute('SELECT 42')",
                    "    assert cursor.fetchone() == (42,)",
                    "assert connection.connection.__class__.__module__ == 'turso.lib'",
                    "connection.close()",
                    "if database_name != ':memory:':",
                    "    database = Path(database_name)",
                    "    database.unlink()",
                    "    for sidecar in database.parent.glob(database.name + '-*'):",
                    "        sidecar.unlink()",
                    "",
                ]
            )
        )
        environment = {**os.environ, "PDM_IGNORE_ACTIVE_VENV": "1"}
        subprocess.run(
            ["pdm", "install", "--project", str(project), "--no-self"],
            check=True,
            env=environment,
        )
        for database_name in (":memory:", str(project / "installed-smoke.db")):
            subprocess.run(
                [
                    "pdm",
                    "run",
                    "--project",
                    str(project),
                    "python",
                    str(smoke),
                    database_name,
                ],
                check=True,
                cwd=project,
                env=environment,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version")
    args = parser.parse_args()
    artifacts = _artifacts()
    metadata = {artifact.suffix: _verify_archive(artifact) for artifact in artifacts}
    _verify_metadata_consistency(
        metadata[".whl"], metadata[".gz"], expected_version=args.expected_version
    )
    for artifact in artifacts:
        _clean_install(artifact)
    print("Wheel and sdist archive checks and clean-install Django smoke tests passed.")


if __name__ == "__main__":
    main()
