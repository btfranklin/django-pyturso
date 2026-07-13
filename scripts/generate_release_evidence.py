"""Generate a deterministic index of local release-candidate evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.verify_packages import DIST, _artifacts, _read_metadata

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "release" / "evidence.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_hashes(paths: list[Path]) -> dict[str, str]:
    return {str(path.relative_to(ROOT)): _sha256(path) for path in sorted(paths)}


def _mutation_counts() -> dict[str, int]:
    metadata_paths = sorted(
        (ROOT / "mutants" / "src" / "django_pyturso").glob("*.meta")
    )
    if not metadata_paths:
        raise RuntimeError(
            "mutation results are missing; run `pdm run mutation-critical` first"
        )
    exit_codes: list[int] = []
    for path in metadata_paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        exit_codes.extend(document["exit_code_by_key"].values())
    if not exit_codes:
        raise RuntimeError("mutation result metadata contains no mutants")
    counts = Counter(exit_codes)
    unexpected_codes = set(counts) - {0, 1, 2, -24}
    if unexpected_codes:
        raise RuntimeError(f"unrecognized mutmut exit codes: {sorted(unexpected_codes)}")
    return {
        "generated": len(exit_codes),
        "killed": counts[1],
        "survived": counts[0],
        "timeout": counts[2] + counts[-24],
    }


def build_document() -> dict[str, Any]:
    artifacts = _artifacts()
    wheel = next(artifact for artifact in artifacts if artifact.suffix == ".whl")
    version = _read_metadata(wheel)["Version"]
    if not version:
        raise RuntimeError("wheel metadata does not contain a version")
    coverage = json.loads(
        (ROOT / "artifacts" / "coverage" / "coverage.json").read_text(encoding="utf-8")
    )
    performance = json.loads(
        (ROOT / "artifacts" / "performance" / "report" / "performance-report.json")
        .read_text(encoding="utf-8")
    )
    review_paths = sorted((ROOT / "artifacts" / "reviews").glob("*.md"))
    mutation_review = ROOT / "artifacts" / "reviews" / "mutation-baseline.md"
    if not mutation_review.is_file():
        raise RuntimeError("mutation review ledger is missing")
    mutation = _mutation_counts()
    review_text = mutation_review.read_text(encoding="utf-8")
    if f'{mutation["generated"]:,}' not in review_text:
        raise RuntimeError("mutation review ledger does not match the generated count")
    return {
        "schema_version": 1,
        "package": {"name": "django-pyturso", "version": version},
        "release_eligible": not (ROOT / "IMPLEMENTATION_PLAN.md").exists(),
        "artifacts": _relative_hashes([*artifacts, DIST / "sbom.cdx.json"]),
        "locks": _relative_hashes(
            [ROOT / "pdm.lock", ROOT / "pdm.min.lock", ROOT / "pdm.latest.lock"]
        ),
        "coverage": {
            "percent_covered": coverage["totals"]["percent_covered"],
            "num_statements": coverage["totals"]["num_statements"],
            "num_branches": coverage["totals"]["num_branches"],
        },
        "performance": {
            "schema_version": performance["schema_version"],
            "cases": [case["case_id"] for case in performance["cases"]],
        },
        "mutation": mutation,
        "reviews": _relative_hashes(review_paths),
        "platform_matrix": {
            "evidence_document": _sha256(
                ROOT / "docs" / "design" / "evidence" / "driver-platform-matrix.md"
            ),
            "remote_matrix_executed": False,
        },
    }


def main() -> None:
    document = build_document()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sums = DIST / "SHA256SUMS"
    artifact_paths = [*_artifacts(), DIST / "sbom.cdx.json"]
    sums.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in sorted(artifact_paths)),
        encoding="utf-8",
    )
    status = "eligible" if document["release_eligible"] else "not eligible"
    print(f"Local release evidence index generated ({status}).")


if __name__ == "__main__":
    main()
