"""Build distributions and normalize the sdist gzip envelope deterministically."""

from __future__ import annotations

import argparse
import gzip
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize_sdist(path: Path, *, mtime: int) -> None:
    """Rewrite only the gzip envelope while preserving the complete tar payload."""

    tar_bytes = gzip.decompress(path.read_bytes())
    path.write_bytes(gzip.compress(tar_bytes, mtime=mtime))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    destination = args.dest.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(destination)],
        cwd=ROOT,
        check=True,
    )
    source_date_epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    sdists = sorted(destination.glob("*.tar.gz"))
    if len(sdists) != 1:
        raise RuntimeError("build must produce exactly one sdist")
    normalize_sdist(sdists[0], mtime=source_date_epoch)


if __name__ == "__main__":
    main()
