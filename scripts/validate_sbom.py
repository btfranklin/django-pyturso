"""Validate and bind the release SBOM to the built distributions."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from scripts.verify_packages import DIST, ROOT, _artifacts, _read_metadata

SBOM = DIST / "sbom.cdx.json"


def _normalize_name(name: str) -> str:
    return name.casefold().replace("_", "-").replace(".", "-")


def expected_runtime_components() -> dict[str, str]:
    completed = subprocess.run(
        [
            "pdm",
            "export",
            "--prod",
            "--no-extras",
            "--no-hashes",
            "--lockfile",
            str(ROOT / "pdm.lock"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    components: dict[str, str] = {}
    for raw_line in completed.stdout.splitlines():
        line = raw_line.partition(";")[0].strip()
        if not line or line.startswith("#"):
            continue
        name, separator, version = line.partition("==")
        if not separator or not name or not version:
            raise RuntimeError(f"unexpected production lock export line: {raw_line!r}")
        components[_normalize_name(name)] = version
    if not components:
        raise RuntimeError("production lock export contains no components")
    return components


def validate_document(
    document: dict[str, Any],
    *,
    expected_version: str,
    expected_components: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    if document.get("bomFormat") != "CycloneDX":
        errors.append("SBOM bomFormat must be CycloneDX")
    if document.get("specVersion") != "1.6":
        errors.append("SBOM specVersion must be 1.6")
    metadata = document.get("metadata")
    component = metadata.get("component", {}) if isinstance(metadata, dict) else {}
    if component.get("name") != "django-pyturso":
        errors.append("SBOM root component must be django-pyturso")
    if component.get("type") != "library":
        errors.append("SBOM root component must be a library")
    if component.get("version") != expected_version:
        errors.append(
            f"SBOM root version {component.get('version')!r} does not match "
            f"artifact version {expected_version!r}"
        )
    components = document.get("components")
    if not isinstance(components, list):
        errors.append("SBOM components must be a list")
        components = []
    actual_components = {
        _normalize_name(str(item.get("name", ""))): str(item.get("version", ""))
        for item in components
        if isinstance(item, dict)
    }
    if actual_components != expected_components:
        errors.append(
            "SBOM runtime components do not match the production lock: "
            f"expected={expected_components!r} actual={actual_components!r}"
        )
    component_refs = {
        str(item["bom-ref"])
        for item in components
        if isinstance(item, dict) and item.get("bom-ref")
    }
    root_ref = component.get("bom-ref")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list):
        errors.append("SBOM dependencies must be a list")
        dependencies = []
    dependency_refs = {
        str(item["ref"])
        for item in dependencies
        if isinstance(item, dict) and item.get("ref")
    }
    if root_ref not in dependency_refs:
        errors.append("SBOM dependency graph is missing the root component")
    root_dependencies: list[str] = next(
        (
            [str(ref) for ref in item.get("dependsOn", [])]
            for item in dependencies
            if isinstance(item, dict) and item.get("ref") == root_ref
        ),
        [],
    )
    if set(root_dependencies) != component_refs:
        errors.append("SBOM root dependency edges do not match the runtime components")
    missing_refs = component_refs - dependency_refs
    if missing_refs:
        errors.append(f"SBOM dependency graph is missing component refs: {sorted(missing_refs)}")
    return errors


def main() -> None:
    artifacts = _artifacts()
    wheel = next(artifact for artifact in artifacts if artifact.suffix == ".whl")
    version = _read_metadata(wheel)["Version"]
    if not version:
        raise RuntimeError("wheel metadata does not contain a version")
    document = json.loads(SBOM.read_text(encoding="utf-8"))
    errors = validate_document(
        document,
        expected_version=version,
        expected_components=expected_runtime_components(),
    )
    if errors:
        raise RuntimeError("SBOM validation failed:\n- " + "\n- ".join(errors))
    print(f"CycloneDX 1.6 SBOM is valid and bound to django-pyturso {version}.")


if __name__ == "__main__":
    main()
