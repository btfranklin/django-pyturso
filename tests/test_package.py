"""Package metadata checks for the importable backend."""

import tomllib
import zipfile
from email.message import EmailMessage
from pathlib import Path

import pytest

import django_pyturso
from scripts import verify_packages
from scripts.verify_packages import _verify_metadata_consistency


def test_package_imports() -> None:
    assert django_pyturso.__doc__ == "Django database backend for embedded Turso."


def _metadata(version: str) -> EmailMessage:
    with (verify_packages.ROOT / "pyproject.toml").open("rb") as manifest:
        project = tomllib.load(manifest)["project"]
    message = EmailMessage()
    message["Name"] = project["name"]
    message["Version"] = version
    message["Requires-Python"] = project["requires-python"]
    message["License-Expression"] = "MIT"
    for requirement in project["dependencies"]:
        message["Requires-Dist"] = requirement
    return message


@pytest.fixture
def changed_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "django-pyturso-fixture"\nrequires-python = ">=3.15"\n'
        'dependencies = ["Django>=6.1.0", "pyturso>=0.8.0", "sqlparse>=0.5.9"]\n'
    )
    monkeypatch.setattr(verify_packages, "ROOT", tmp_path)
    return tmp_path


def _wheel(directory: Path, metadata: EmailMessage) -> Path:
    artifact = directory / "django_pyturso-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("django_pyturso/base.py", "")
        archive.writestr("django_pyturso/py.typed", "")
        archive.writestr("django_pyturso-1.2.3.dist-info/THIRD_PARTY_NOTICES.md", "")
        archive.writestr("django_pyturso-1.2.3.dist-info/METADATA", metadata.as_bytes())
    return artifact


def test_wheel_metadata_follows_the_current_project_manifest(changed_manifest: Path) -> None:
    metadata = _metadata("1.2.3")
    requirements = metadata.get_all("Requires-Dist", [])
    del metadata["Requires-Dist"]
    for requirement in reversed(requirements):
        metadata["Requires-Dist"] = requirement.replace(">=", " >= ")
    metadata.replace_header("Requires-Python", ">= 3.15")
    verified = verify_packages._verify_archive(_wheel(changed_manifest, metadata))
    assert verified["Name"] == "django-pyturso-fixture"


@pytest.mark.parametrize("change", ["stale", "missing", "extra", "duplicate"])
def test_wheel_rejects_incorrect_dependency_metadata(
    changed_manifest: Path, change: str
) -> None:
    metadata = _metadata("1.2.3")
    requirements = metadata.get_all("Requires-Dist", [])
    del metadata["Requires-Dist"]
    if change == "stale":
        requirements[0] = "Django>=6.0.0"
    elif change == "missing":
        requirements.pop()
    elif change == "extra":
        requirements.append("unexpected>=1.0")
    else:
        requirements.append(requirements[0])
    for requirement in requirements:
        metadata["Requires-Dist"] = requirement
    with pytest.raises(RuntimeError, match="Requires-Dist"):
        verify_packages._verify_archive(_wheel(changed_manifest, metadata))


def test_clean_install_project_uses_declared_metadata(
    changed_manifest: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configurations: list[tuple[str, list[str]]] = []

    def run(command: list[str], **kwargs: object) -> None:
        if command[1] == "install":
            project_directory = Path(command[command.index("--project") + 1])
            with (project_directory / "pyproject.toml").open("rb") as manifest:
                project = tomllib.load(manifest)["project"]
            configurations.append((project["requires-python"], project["dependencies"]))

    monkeypatch.setattr("scripts.verify_packages.subprocess.run", run)
    artifact = _wheel(changed_manifest, _metadata("1.2.3"))
    verify_packages._clean_install(artifact)
    assert configurations == [
        (">=3.15", [f"django-pyturso-fixture @ {artifact.resolve().as_uri()}"])
    ]


@pytest.mark.parametrize("field", ["Name", "Requires-Python"])
@pytest.mark.parametrize("missing", [False, True])
def test_wheel_rejects_stale_or_missing_declared_metadata(
    changed_manifest: Path, field: str, missing: bool
) -> None:
    metadata = _metadata("1.2.3")
    if missing:
        del metadata[field]
    else:
        metadata.replace_header(field, "stale-value")
    with pytest.raises(RuntimeError, match="project metadata|Requires-Python"):
        verify_packages._verify_archive(_wheel(changed_manifest, metadata))


def test_distribution_metadata_must_match_each_other_and_release_version() -> None:
    wheel = _metadata("1.2.3")
    sdist = _metadata("1.2.3")
    _verify_metadata_consistency(wheel, sdist, expected_version="1.2.3")

    with pytest.raises(RuntimeError, match="release tag version"):
        _verify_metadata_consistency(wheel, sdist, expected_version="1.2.4")

    mismatched_sdist = _metadata("1.2.4")
    with pytest.raises(RuntimeError, match="disagree on Version"):
        _verify_metadata_consistency(wheel, mismatched_sdist, expected_version=None)
