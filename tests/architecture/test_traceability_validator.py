"""Traceability validator contract tests."""

from __future__ import annotations

from pathlib import Path

from scripts.validate_traceability import validate


def _workspace(tmp_path: Path, *, docs_reference: str, test_selector: str) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "contract.md").write_text(
        "# Contract\n\n## Supported path\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_contract.py").write_text(
        "def test_supported_path():\n    pass\n", encoding="utf-8"
    )
    manifest = tmp_path / "traceability.toml"
    manifest.write_text(
        "\n".join(
            [
                "schema_version = 1",
                "[[requirement]]",
                'id = "SAMPLE-CONTRACT-001"',
                'behavior = "The sample path is supported."',
                'classification = "parity"',
                'modes = ["memory"]',
                f'tests = ["{test_selector}"]',
                f'docs = ["{docs_reference}"]',
                "phase = 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return manifest


def test_validator_resolves_markdown_anchors_and_test_nodes(
    tmp_path: Path,
) -> None:
    manifest = _workspace(
        tmp_path,
        docs_reference="docs/contract.md#supported-path",
        test_selector="tests/test_contract.py::test_supported_path",
    )
    # The sample manifest intentionally doesn't contain the repository's required IDs.
    errors = validate(root=tmp_path, manifest=manifest)
    assert not [error for error in errors if not error.startswith("required traceability entry")]


def test_validator_rejects_dead_anchors_and_nodes(tmp_path: Path) -> None:
    manifest = _workspace(
        tmp_path,
        docs_reference="docs/contract.md#missing",
        test_selector="tests/test_contract.py::test_missing",
    )
    errors = validate(root=tmp_path, manifest=manifest)
    assert (
        "SAMPLE-CONTRACT-001 references missing documentation anchor: "
        "docs/contract.md#missing"
    ) in errors
    assert (
        "SAMPLE-CONTRACT-001 references missing test node: "
        "tests/test_contract.py::test_missing"
    ) in errors
