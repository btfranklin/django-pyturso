"""Executable security-policy validation tests."""

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from scripts import validate_security
from scripts.validate_sbom import validate_document
from scripts.workflow_policy import action_uses, jobs, load_workflow, permissions, triggers


def _write_exception(path: Path, *, expires_on: str, include_owner: bool = True) -> None:
    owner = 'owner = "maintainer"\n' if include_owner else ""
    path.write_text(
        """
schema_version = 1

[[exception]]
package = "example"
issue_type = "advisory"
identifier = "GHSA-example"
affected_range = "<2"
rationale = "Not reachable through the backend."
"""
        + owner
        + f"""compensating_control = "Input path is disabled."
approved_on = 2026-07-01
expires_on = {expires_on}
"""
    )


def _write_workflow(path: Path, action_reference: str) -> None:
    path.write_text(
        "\n".join(
            [
                "name: Test",
                "# uses: actions/checkout@v7.0.0",
                "on: [push]",
                "permissions:",
                "    contents: read",
                "jobs:",
                "    test:",
                "        runs-on: ubuntu-24.04",
                "        steps:",
                f"            - uses: {action_reference}",
                "            - run: 'echo \"uses: actions/setup-python@v6.1.0\"'",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_repository_security_policy_is_valid() -> None:
    validate_security.validate_exceptions()
    validate_security.validate_dependency_review_policy()
    validate_security.validate_runtime_licenses()
    validate_security.validate_workflows()


def test_dependabot_auto_merge_enrolls_only_dependabot_without_checkout() -> None:
    workflow = load_workflow(
        Path(__file__).parents[2] / ".github" / "workflows" / "dependabot-auto-merge.yml"
    )
    assert triggers(workflow) == {
        "pull_request_target": {"types": ["opened", "reopened"]}
    }
    assert permissions(workflow) == {
        "contents": "write",
        "pull-requests": "write",
    }
    assert set(jobs(workflow)) == {"enable-auto-merge"}
    assert action_uses(workflow) == []
    validate_security._validate_dependabot_auto_merge(workflow)


def test_workflow_policy_accepts_human_readable_action_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_workflow(tmp_path / "sample.yml", "actions/checkout@v7")
    monkeypatch.setattr(validate_security, "WORKFLOW_ROOT", tmp_path)

    validate_security.validate_workflows()


def test_workflow_policy_accepts_release_major_action_channel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_workflow(tmp_path / "sample.yml", "pypa/gh-action-pypi-publish@release/v1")
    monkeypatch.setattr(validate_security, "WORKFLOW_ROOT", tmp_path)

    validate_security.validate_workflows()


def test_workflow_policy_does_not_accept_commented_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sample.yml"
    path.write_text(
        "\n".join(
            [
                "name: Test",
                "on: [push]",
                "# permissions:",
                "#     contents: read",
                "jobs:",
                "    test:",
                "        runs-on: ubuntu-24.04",
                "        steps:",
                "            - uses: actions/checkout@v7",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(validate_security, "WORKFLOW_ROOT", tmp_path)

    with pytest.raises(ValueError, match="permissions must be a mapping"):
        validate_security.validate_workflows()


def test_workflow_policy_rejects_commit_sha_action_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_workflow(tmp_path / "sample.yml", f"actions/checkout@{'0' * 40}")
    monkeypatch.setattr(validate_security, "WORKFLOW_ROOT", tmp_path)

    with pytest.raises(ValueError, match="commit SHA pins are forbidden"):
        validate_security.validate_workflows()


def test_workflow_policy_rejects_minor_or_patch_action_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_workflow(tmp_path / "sample.yml", "actions/checkout@v7.0.0")
    monkeypatch.setattr(validate_security, "WORKFLOW_ROOT", tmp_path)

    with pytest.raises(ValueError, match="minor, patch, and commit SHA pins are forbidden"):
        validate_security.validate_workflows()


def test_expired_security_exception_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "exceptions.toml"
    _write_exception(manifest, expires_on="2026-07-02")
    monkeypatch.setattr(validate_security, "EXCEPTIONS_PATH", manifest)
    with pytest.raises(ValueError, match="expired on 2026-07-02"):
        validate_security.validate_exceptions(today=dt.date(2026, 7, 13))


def test_incomplete_security_exception_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "exceptions.toml"
    _write_exception(manifest, expires_on="2026-08-01", include_owner=False)
    monkeypatch.setattr(validate_security, "EXCEPTIONS_PATH", manifest)
    with pytest.raises(ValueError, match="missing=.*owner"):
        validate_security.validate_exceptions(today=dt.date(2026, 7, 13))


def test_sbom_is_bound_to_artifact_version_and_runtime_components() -> None:
    expected_components = {"django": "6.0.7", "pyturso": "0.7.0"}
    document: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "metadata": {
            "component": {
                "bom-ref": "root",
                "name": "django-pyturso",
                "type": "library",
                "version": "1.2.3",
            }
        },
        "components": [
            {"bom-ref": "django", "name": "Django", "version": "6.0.7"},
            {"bom-ref": "pyturso", "name": "pyturso", "version": "0.7.0"},
        ],
        "dependencies": [
            {"ref": "root", "dependsOn": ["django", "pyturso"]},
            {"ref": "django"},
            {"ref": "pyturso"},
        ],
    }

    assert (
        validate_document(
            document,
            expected_version="1.2.3",
            expected_components=expected_components,
        )
        == []
    )
    errors = validate_document(
        document,
        expected_version="1.2.4",
        expected_components=expected_components,
    )
    assert errors == [
        "SBOM root version '1.2.3' does not match artifact version '1.2.4'"
    ]

    document["components"][0]["version"] = "0.0.0"
    errors = validate_document(
        document,
        expected_version="1.2.3",
        expected_components=expected_components,
    )
    assert len(errors) == 1
    assert errors[0].startswith("SBOM runtime components do not match the production lock")
