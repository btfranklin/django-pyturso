"""Release-workflow safety contracts."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
DRAFT_WORKFLOW = ROOT / ".github" / "workflows" / "create-draft-release.yml"
VERIFY_WORKFLOW = ROOT / ".github" / "workflows" / "verify-release.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "python-publish.yml"


def test_draft_release_is_the_standard_tag_triggered_creator() -> None:
    workflow = DRAFT_WORKFLOW.read_text(encoding="utf-8")
    assert 'name: Create Draft Release' in workflow
    assert 'tags:\n            - "v*.*.*"' in workflow
    assert 'contents: write' in workflow
    assert 'uses: btfranklin/release-notes-scribe@v0' in workflow


def test_verify_release_carries_exact_tag_evidence_without_releasing() -> None:
    workflow = VERIFY_WORKFLOW.read_text(encoding="utf-8")
    assert 'name: Verify Release' in workflow
    assert 'verify-release:' in workflow
    assert 'test "$(git rev-list -n 1 "$TAG")" = "$GITHUB_SHA"' in workflow
    assert 'pdm run verify-release --expected-version "${TAG#v}"' in workflow
    assert 'gh release create' not in workflow
    assert 'contents: write' not in workflow
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


def test_publish_rebuilds_the_release_for_trusted_publishing() -> None:
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    assert "    release:\n        types: [published]" in workflow
    assert "        environment: release" in workflow
    assert "            id-token: write" in workflow
    assert "actions/checkout@v7" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "pdm-project/setup-pdm@v4" in workflow
    assert "run: pdm build" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
