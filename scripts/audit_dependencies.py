"""Check locked runtime dependencies for published security advisories."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    subprocess.run(["pdm", "lock", "--check"], check=True, cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="django-pyturso-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        subprocess.run(
            [
                "pdm", "export", "--prod", "--format", "requirements",
                "--output", str(requirements),
            ],
            check=True,
            cwd=ROOT,
        )
        subprocess.run(
            [
                sys.executable, "-m", "pip_audit",
                "--requirement", str(requirements),
                "--require-hashes", "--disable-pip", "--strict",
                "--vulnerability-service", "pypi", "--progress-spinner", "off",
            ],
            check=True,
            cwd=ROOT,
        )


if __name__ == "__main__":
    main()
