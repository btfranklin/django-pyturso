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


def test_publish_verifies_attested_provenance_before_upload() -> None:
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    verification = workflow.index("gh attestation verify")
    publication = workflow.index("pypa/gh-action-pypi-publish")
    assert verification < publication
    assert '--signer-workflow "github.com/$GITHUB_REPOSITORY/' in workflow
    assert '--source-ref "refs/tags/$TAG"' in workflow
    assert '--source-digest "$(git rev-parse HEAD)"' in workflow
