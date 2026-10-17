"""Install the verified native documentation checker for CI."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import platform
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

VERSION = "0.1.0"
# SHA-256 digests from the published release assets.
ARCHIVES = {
    ("Darwin", "arm64"): (
        "aarch64-apple-darwin.tar.gz",
        "e65a90824f58a843142cd872adce0fe46ad6c3990349c85f05cdcf02aeac68d3",
    ),
    ("Darwin", "x86_64"): (
        "x86_64-apple-darwin.tar.gz",
        "9cb141d23a1ce46e5cfe208b242547666d0e64aedac677eacc2c27876379780d",
    ),
    ("Linux", "x86_64"): (
        "x86_64-unknown-linux-gnu.tar.gz",
        "80da73f3a01ab1301539561812d81213112187e71ad4ee630a0d70e95692cd22",
    ),
    ("Windows", "AMD64"): (
        "x86_64-pc-windows-msvc.zip",
        "71c86b87f82180fc43f4f6a8480474a98d0a777cf44fcbe98c404a94935958b6",
    ),
}


def install_archive(data: bytes, checksum: str, destination: Path, *, windows: bool) -> Path:
    """Verify an archive and write only its executable to the destination."""
    if hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError("Perfect Doc archive checksum does not match the release")
    executable = "perfect-doc.exe" if windows else "perfect-doc"
    if windows:
        with zipfile.ZipFile(io.BytesIO(data)) as zipped:
            names = [name for name in zipped.namelist() if PurePosixPath(name).name == executable]
            if len(names) != 1:
                raise ValueError("Perfect Doc archive must contain exactly one executable")
            content = zipped.read(names[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            members = [
                member for member in archive.getmembers()
                if member.isfile() and PurePosixPath(member.name).name == executable
            ]
            if len(members) != 1:
                raise ValueError("Perfect Doc archive must contain exactly one executable")
            stream = archive.extractfile(members[0])
            assert stream is not None
            content = stream.read()
    destination.mkdir(parents=True, exist_ok=True)
    binary = destination / executable
    binary.write_bytes(content)
    binary.chmod(0o755)
    return binary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    system = platform.system()
    target = (system, platform.machine())
    if target not in ARCHIVES:
        parser.error(f"No verified Perfect Doc archive for {target}")
    archive, checksum = ARCHIVES[target]
    url = (
        f"https://github.com/btfranklin/perfect-doc/releases/download/v{VERSION}/"
        f"perfect-doc-{VERSION}-{archive}"
    )
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    binary = install_archive(
        data, checksum, args.destination.resolve(), windows=system == "Windows"
    )
    if github_path := os.environ.get("GITHUB_PATH"):
        with Path(github_path).open("a", encoding="utf-8") as output:
            output.write(f"{binary.parent}\n")
    print(f"Installed {binary}")


if __name__ == "__main__":
    main()
