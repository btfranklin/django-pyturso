"""Check the documentation contract and native checker installation."""

import hashlib
import io
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.install_perfect_doc import install_archive

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("broken_target", [None, "docs/missing.md", "docs/index.md#missing"])
def test_documentation_contract_rejects_broken_references(
    tmp_path: Path, broken_target: str | None
) -> None:
    for path in ROOT.glob("*.md"):
        shutil.copyfile(path, tmp_path / path.name)
    shutil.copytree(ROOT / "docs", tmp_path / "docs")
    shutil.copyfile(ROOT / "perfect-doc.toml", tmp_path / "perfect-doc.toml")
    if broken_target:
        with (tmp_path / "README.md").open("a") as document:
            document.write(f"\n[Broken reference]({broken_target})\n")
    executable = shutil.which("perfect-doc")
    assert executable, "Install Perfect Doc before running the documentation tests"
    result = subprocess.run(
        [executable, "--no-banner", "check", "--offline", "."],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert (result.returncode == 0) == (broken_target is None), result.stdout + result.stderr


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("valid_checksum", [False, True])
def test_checker_archive_is_verified_before_installation(
    tmp_path: Path, windows: bool, valid_checksum: bool
) -> None:
    executable = "perfect-doc.exe" if windows else "perfect-doc"
    data = io.BytesIO()
    if windows:
        with zipfile.ZipFile(data, "w") as zipped:
            zipped.writestr(f"release/{executable}", b"binary")
            zipped.writestr("../unwanted", b"not extracted")
    else:
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            for name, content in [(f"release/{executable}", b"binary"), ("../unwanted", b"no")]:
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                archive.addfile(entry, io.BytesIO(content))
    content = data.getvalue()
    checksum = hashlib.sha256(content).hexdigest() if valid_checksum else "0" * 64
    destination = tmp_path / "bin"
    if valid_checksum:
        installed = install_archive(content, checksum, destination, windows=windows)
        assert installed.read_bytes() == b"binary"
        assert list(destination.iterdir()) == [installed]
        assert not (tmp_path / "unwanted").exists()
    else:
        with pytest.raises(ValueError, match="checksum"):
            install_archive(content, checksum, destination, windows=windows)
        assert not destination.exists()
