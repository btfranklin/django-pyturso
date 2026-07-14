"""Release evidence generation regression tests."""

from pathlib import Path

import pytest

from scripts import generate_release_evidence


def test_mutation_counts_reject_missing_generated_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generate_release_evidence, "ROOT", tmp_path)

    with pytest.raises(RuntimeError, match="mutation results are missing"):
        generate_release_evidence._mutation_counts()


def test_remote_platform_matrix_evidence_covers_every_native_cell() -> None:
    assert generate_release_evidence._remote_matrix_executed() is True
