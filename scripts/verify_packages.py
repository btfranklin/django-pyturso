"""Verify release archives and clean-install smoke behavior through PDM."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
from collections.abc import Iterable
from email.message import Message
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
NOTICE = "THIRD_PARTY_NOTICES.md"
FORBIDDEN_ARCHIVE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _project_metadata() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as manifest:
        project: dict[str, Any] = tomllib.load(manifest)["project"]
    return project


def _normalized_requirements(requirements: Iterable[str]) -> list[str]:
    return sorted(value.replace(" ", "") for value in requirements)


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
    metadata = _read_metadata(artifact)
    if artifact.suffix == ".whl":
        if any(Path(name).parts[0] == "tests" for name in names):
            raise RuntimeError(f"{artifact.name} unexpectedly contains tests")
        project = _project_metadata()
        if metadata["Name"] != project["name"]:
            raise RuntimeError(f"{artifact.name} has incorrect project metadata")
        if metadata.get("Requires-Python", "").replace(" ", "") != project[
            "requires-python"
        ].replace(" ", ""):
            raise RuntimeError(f"{artifact.name} has incorrect Requires-Python")
        requirements = _normalized_requirements(metadata.get_all("Requires-Dist", []))
        if requirements != _normalized_requirements(project["dependencies"]):
            raise RuntimeError(f"{artifact.name} has incorrect Requires-Dist")
    return metadata


def _verify_metadata_consistency(
    wheel: Message, sdist: Message, *, expected_version: str | None
) -> None:
    for field in ("Name", "Version", "Requires-Python", "License-Expression"):
        if wheel[field] != sdist[field]:
            raise RuntimeError(f"wheel and sdist disagree on {field}")
    wheel_requirements = _normalized_requirements(wheel.get_all("Requires-Dist", []))
    sdist_requirements = _normalized_requirements(sdist.get_all("Requires-Dist", []))
    if wheel_requirements != sdist_requirements:
        raise RuntimeError("wheel and sdist disagree on Requires-Dist")
    if expected_version is not None and wheel["Version"] != expected_version:
        raise RuntimeError(
            f"artifact version {wheel['Version']!r} does not match release tag version "
            f"{expected_version!r}"
        )


def _clean_install(artifact: Path) -> None:
    metadata = _project_metadata()
    with tempfile.TemporaryDirectory(prefix="django-pyturso-package-") as directory:
        project = Path(directory)
        artifact_uri = artifact.resolve().as_uri()
        artifact_requirement = f"{metadata['name']} @ {artifact_uri}"
        (project / "pyproject.toml").write_text(
            "\n".join(
                [
                    "[project]",
                    'name = "django-pyturso-smoke"',
                    'version = "0.0.0"',
                    f"requires-python = {json.dumps(metadata['requires-python'])}",
                    f"dependencies = [{json.dumps(artifact_requirement)}]",
                    "",
                ]
            )
        )
        smoke = project / "smoke.py"
        shutil.copyfile(Path(__file__).with_name("package_smoke.py"), smoke)
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
