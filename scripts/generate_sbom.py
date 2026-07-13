"""Generate a reproducible CycloneDX SBOM in the release artifact directory."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from scripts.verify_packages import _artifacts, _read_metadata

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "sbom.cdx.json"


def main() -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="django-pyturso-sbom-") as directory:
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
        subprocess.run(
            [
                "cyclonedx-py",
                "requirements",
                str(requirements),
                "--pyproject",
                str(ROOT / "pyproject.toml"),
                "--mc-type",
                "library",
                "--output-reproducible",
                "--output-file",
                str(OUTPUT),
            ],
            cwd=ROOT,
            check=True,
        )
    wheel = next(artifact for artifact in _artifacts() if artifact.suffix == ".whl")
    version = _read_metadata(wheel)["Version"]
    if not version:
        raise RuntimeError("wheel metadata does not contain a version")
    document = json.loads(OUTPUT.read_text(encoding="utf-8"))
    root_component = document["metadata"]["component"]
    root_component["version"] = version
    root_ref = root_component["bom-ref"]
    component_refs = sorted(component["bom-ref"] for component in document["components"])
    root_dependency = next(
        dependency for dependency in document["dependencies"] if dependency["ref"] == root_ref
    )
    root_dependency["dependsOn"] = component_refs
    OUTPUT.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
