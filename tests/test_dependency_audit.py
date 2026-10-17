"""Keep the runtime dependency floor and advisory gate effective."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from scripts import audit_dependencies

ROOT = Path(__file__).resolve().parents[1]


def test_sqlparse_security_floor_is_declared_locked_and_installed() -> None:
    with (ROOT / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)["project"]
    requirements = {
        canonicalize_name(requirement.name): requirement
        for requirement in map(Requirement, project["dependencies"])
    }
    requirement = requirements[canonicalize_name("sqlparse")]
    assert "0.5.5" not in requirement.specifier
    assert version("sqlparse") in requirement.specifier
    with (ROOT / "pdm.lock").open("rb") as source:
        packages = tomllib.load(source)["package"]
    locked = next(package for package in packages if package["name"] == "sqlparse")
    assert locked["version"] in requirement.specifier
    assert locked["version"] == version("sqlparse")


def test_audit_uses_the_complete_locked_runtime_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = subprocess.run
    exported: Path | None = None

    def intercept(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal exported
        if command[:3] != [sys.executable, "-m", "pip_audit"]:
            return run(command, **kwargs)
        exported = Path(command[command.index("--requirement") + 1])
        content = exported.read_text()
        requirements = [
            Requirement(line.removesuffix("\\").strip())
            for line in content.splitlines()
            if line and not line.startswith(("#", " "))
        ]
        actual = {
            canonicalize_name(requirement.name): str(requirement.specifier)
            for requirement in requirements
        }
        with (ROOT / "pdm.lock").open("rb") as source:
            packages = tomllib.load(source)["package"]
        expected = {
            canonicalize_name(package["name"]): f"=={package['version']}"
            for package in packages if "default" in package["groups"]
        }
        assert actual == expected
        assert "pip-audit" not in actual
        assert "django-pyturso" not in actual
        assert "--hash=sha256:" in content
        assert {"--require-hashes", "--disable-pip", "--strict"}.issubset(command)
        assert command[command.index("--vulnerability-service") + 1] == "pypi"
        assert not {"--fix", "--dry-run", "--ignore-vuln"}.intersection(command)
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.audit_dependencies.subprocess.run", intercept)
    audit_dependencies.main()
    assert exported is not None
    assert not exported.exists()


@pytest.mark.parametrize(
    ("failed_stage", "returncode", "expected_calls"),
    [("lock", 1, 1), ("export", 2, 2), ("audit", 1, 3), ("audit", 2, 3)],
)
def test_audit_rejects_stale_locks_export_errors_advisories_and_scan_errors(
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: str,
    returncode: int,
    expected_calls: int,
) -> None:
    calls: list[list[str]] = []
    exported: Path | None = None

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal exported
        calls.append(command)
        assert kwargs["check"] is True
        stage = command[1] if command[0] == "pdm" else "audit"
        if stage == "export":
            exported = Path(command[command.index("--output") + 1])
        if stage == failed_stage:
            raise subprocess.CalledProcessError(returncode, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.audit_dependencies.subprocess.run", run)
    with pytest.raises(subprocess.CalledProcessError) as captured:
        audit_dependencies.main()
    assert captured.value.returncode == returncode
    assert len(calls) == expected_calls
    if exported is not None:
        assert not exported.parent.exists()
