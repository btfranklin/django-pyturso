"""Release-candidate workflow safety contract."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "draft-release-notes.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "python-publish.yml"


def test_release_assets_depend_on_complete_local_verification() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "test ! -e IMPLEMENTATION_PLAN.md" in workflow
    assert "needs: [preflight, platform-verification, deep-verification]" in workflow
    for command in (
        "pdm run coverage-check",
        "pdm run test-upstream",
        "pdm run test-stress",
        "pdm run test-performance",
        "pdm run security",
        "pdm run reproducible-build",
        "pdm run mutation-critical",
    ):
        assert command in workflow
    assert '--expected-version "${TAG#v}"' in workflow


def test_publish_rebuilds_the_release_for_trusted_publishing() -> None:
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    assert "  release:\n    types: [published]" in workflow
    assert "    environment: release" in workflow
    assert "      id-token: write" in workflow
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "pdm-project/setup-pdm@v4" in workflow
    assert "run: pdm build" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
