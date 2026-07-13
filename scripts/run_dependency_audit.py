"""Run pip-audit using only active manifest exceptions."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS_PATH = ROOT / "tests" / "manifests" / "security-exceptions.toml"


def _active_advisories(data: dict[str, Any]) -> list[str]:
    today = dt.date.today()
    identifiers: list[str] = []
    for entry in data.get("exception", []):
        if entry["issue_type"] == "advisory" and entry["expires_on"] >= today:
            identifiers.append(entry["identifier"])
    return sorted(set(identifiers))


def main() -> None:
    data = tomllib.loads(EXCEPTIONS_PATH.read_text())
    with tempfile.TemporaryDirectory(prefix="django-pyturso-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        subprocess.run(
            [
                "pdm",
                "export",
                "--prod",
                "--no-extras",
                "--format",
                "requirements",
                "--lockfile",
                str(ROOT / "pdm.lock"),
                "--output",
                str(requirements),
            ],
            cwd=ROOT,
            check=True,
        )
        command = [
            sys.executable,
            "-m",
            "pip_audit",
            "--requirement",
            str(requirements),
            "--strict",
        ]
        for identifier in _active_advisories(data):
            command.extend(["--ignore-vuln", identifier])
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
