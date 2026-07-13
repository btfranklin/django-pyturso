"""Validate the executable support traceability index."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "manifests" / "support-traceability.toml"
REQUIRED = {"id", "behavior", "classification", "modes", "tests", "docs", "phase"}
CLASSIFICATIONS = {"parity", "enhanced", "intentional_difference", "unsupported"}
DATABASE_MODES = {"memory", "file"}
IDENTIFIER_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]+-[0-9]{3}$")
REQUIRED_IDS = {
    "ARCH-NATIVE-001",
    "BINARYFIELD-DRIVER-001",
    "CONFIG-REJECT-001",
    "CONNECTION-LOCAL-001",
    "CONSTRAINTS-001",
    "DJANGO-USER-PATHS-001",
    "DIFFERENTIAL-PARITY-001",
    "DRIVER-CONTRACT-001",
    "DJANGO-CAPABILITY-DECLARATIONS-001",
    "INTROSPECTION-001",
    "ORM-SCALARS-001",
    "PACKAGE-INSTALL-001",
    "PERFORMANCE-REGRESSION-001",
    "RESILIENCE-001",
    "SCHEMA-MIGRATIONS-001",
    "SECURITY-SUPPLY-001",
    "TEMPORAL-SQL-001",
    "TEST-RUNNER-001",
    "TRANSACTION-STATE-001",
    "UPSTREAM-DJANGO-001",
}


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^#{1,6}\s+(?P<title>.+?)\s*#*\s*$", line)
        if match is None:
            continue
        title = match.group("title").strip().lower()
        slug = re.sub(r"[^\w\- ]", "", title, flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug)
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def _resolve_test_node(path: Path, node_parts: list[str]) -> bool:
    if not node_parts:
        return True
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body: list[ast.stmt] = tree.body
    for raw_part in node_parts:
        part = raw_part.split("[", 1)[0]
        match = next(
            (
                node
                for node in body
                if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name == part
            ),
            None,
        )
        if match is None:
            return False
        body = match.body if isinstance(match, ast.ClassDef) else []
    return True


def _validate_test_selector(root: Path, identifier: str, selector: Any) -> list[str]:
    if not _is_nonempty_text(selector):
        return [f"{identifier} has an invalid empty test selector"]
    path_text, *node_parts = str(selector).split("::")
    if Path(path_text).is_absolute() or ".." in Path(path_text).parts:
        return [f"{identifier} test selector must be repository-relative: {selector}"]
    test_path = root / path_text
    if not test_path.is_file():
        return [f"{identifier} references missing test: {selector}"]
    if test_path.suffix != ".py" or not (
        path_text.startswith("tests/") or path_text.startswith("scripts/")
    ):
        return [
            f"{identifier} test selector is not a Python test or verification script: "
            f"{selector}"
        ]
    try:
        resolved = _resolve_test_node(test_path, node_parts)
    except SyntaxError as error:
        return [f"{identifier} test selector could not be parsed: {selector}: {error}"]
    if not resolved:
        return [f"{identifier} references missing test node: {selector}"]
    return []


def _validate_doc_reference(root: Path, identifier: str, reference: Any) -> list[str]:
    if not _is_nonempty_text(reference):
        return [f"{identifier} has an invalid empty documentation reference"]
    path_text, separator, anchor = str(reference).partition("#")
    if Path(path_text).is_absolute() or ".." in Path(path_text).parts:
        return [f"{identifier} documentation reference must be repository-relative: {reference}"]
    docs_path = root / path_text
    if not docs_path.is_file():
        return [f"{identifier} references missing docs: {reference}"]
    if separator:
        if not anchor:
            return [f"{identifier} has an empty documentation anchor: {reference}"]
        if docs_path.suffix.lower() != ".md" or anchor not in _markdown_anchors(docs_path):
            return [f"{identifier} references missing documentation anchor: {reference}"]
    return []


def validate(*, root: Path = ROOT, manifest: Path = MANIFEST) -> list[str]:
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return [f"cannot read traceability manifest: {error}"]

    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("traceability schema_version must be 1")
    unknown_top_level = set(data) - {"schema_version", "requirement"}
    if unknown_top_level:
        errors.append(f"unknown traceability top-level keys: {sorted(unknown_top_level)}")
    requirements = data.get("requirement", [])
    if not isinstance(requirements, list) or not requirements:
        return errors + ["manifest has no requirements"]

    seen: set[str] = set()
    for index, raw_requirement in enumerate(requirements, start=1):
        if not isinstance(raw_requirement, dict):
            errors.append(f"requirement {index} must be a TOML table")
            continue
        requirement = dict(raw_requirement)
        missing = REQUIRED - set(requirement)
        unknown = set(requirement) - REQUIRED
        if missing or unknown:
            errors.append(
                f"requirement {index} has missing={sorted(missing)} unknown={sorted(unknown)}"
            )
            continue
        identifier = requirement["id"]
        if not _is_nonempty_text(identifier) or not IDENTIFIER_PATTERN.fullmatch(identifier):
            errors.append(f"requirement {index} has an invalid id: {identifier!r}")
            continue
        if identifier in seen:
            errors.append(f"duplicate requirement id: {identifier}")
        seen.add(identifier)
        if not _is_nonempty_text(requirement["behavior"]):
            errors.append(f"{identifier} has an empty behavior")
        if requirement["classification"] not in CLASSIFICATIONS:
            errors.append(f"{identifier} has an invalid classification")
        modes = requirement["modes"]
        if (
            not isinstance(modes, list)
            or not modes
            or any(mode not in DATABASE_MODES for mode in modes)
            or len(modes) != len(set(modes))
        ):
            errors.append(f"{identifier} has invalid or duplicate database modes")
        phase = requirement["phase"]
        if not isinstance(phase, int) or isinstance(phase, bool) or phase < 0:
            errors.append(f"{identifier} has an invalid phase")

        tests = requirement["tests"]
        if not isinstance(tests, list) or not tests:
            errors.append(f"{identifier} has no test selector")
        else:
            for selector in tests:
                errors.extend(_validate_test_selector(root, identifier, selector))
        docs = requirement["docs"]
        if not isinstance(docs, list) or not docs:
            errors.append(f"{identifier} has no documentation reference")
        else:
            for reference in docs:
                errors.extend(_validate_doc_reference(root, identifier, reference))

    for identifier in sorted(REQUIRED_IDS - seen):
        errors.append(f"required traceability entry is missing: {identifier}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Traceability validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    requirement_count = len(tomllib.loads(MANIFEST.read_text(encoding="utf-8"))["requirement"])
    print(f"Traceability validation passed for {requirement_count} requirements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
