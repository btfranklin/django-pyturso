"""Compare deterministic wheel and compressed sdist bytes."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATE_EPOCH = "1783900800"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build(destination: Path) -> tuple[Path, Path]:
    environment = {**os.environ, "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH}
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_distributions.py"),
            "--dest",
            str(destination),
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    wheel = next(destination.glob("*.whl"))
    sdist = next(destination.glob("*.tar.gz"))
    return wheel, sdist


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="django-pyturso-reproducible-") as directory:
        root = Path(directory)
        first_wheel, first_sdist = _build(root / "first")
        second_wheel, second_sdist = _build(root / "second")

        first_wheel_bytes = first_wheel.read_bytes()
        second_wheel_bytes = second_wheel.read_bytes()
        if first_wheel_bytes != second_wheel_bytes:
            raise RuntimeError("controlled wheel builds are not byte-for-byte reproducible")

        first_sdist_bytes = first_sdist.read_bytes()
        second_sdist_bytes = second_sdist.read_bytes()
        if first_sdist_bytes != second_sdist_bytes:
            raise RuntimeError("controlled sdist builds are not byte-for-byte reproducible")

        print(f"wheel sha256: {_digest(first_wheel_bytes)}")
        print(f"sdist sha256: {_digest(first_sdist_bytes)}")
        print("Controlled wheel and compressed sdist bytes are reproducible.")


if __name__ == "__main__":
    main()
