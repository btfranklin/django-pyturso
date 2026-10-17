"""Keep publication behind verification of the same commit and archives."""

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def workflow(name: str) -> dict[str, Any]:
    # BaseLoader preserves GitHub's `on` key instead of treating it as a Boolean.
    with (WORKFLOWS / name).open() as source:
        document: dict[str, Any] = yaml.load(source, Loader=yaml.BaseLoader)
    return document


def test_publication_requires_successful_local_release_verification() -> None:
    publish = workflow("python-publish.yml")
    assert publish["on"] == {"release": {"types": ["published"]}}
    gate = publish["jobs"]["verify-release"]
    assert gate["uses"] == "./.github/workflows/verify-release.yml"
    assert "if" not in gate
    assert "continue-on-error" not in gate
    upload = publish["jobs"]["publish"]
    assert upload["needs"] == "verify-release"
    assert "if" not in upload
    assert "continue-on-error" not in upload
    assert upload["environment"] == "release"
    assert publish["permissions"] == {"contents": "read"}
    assert upload["permissions"] == {"contents": "read", "id-token": "write"}


def test_release_verification_checks_all_platforms_and_mvcc_modes_at_the_event_commit() -> None:
    verify = workflow("verify-release.yml")
    assert "workflow_call" in verify["on"]
    assert verify["permissions"] == {"contents": "read"}
    platform = verify["jobs"]["platform-verification"]
    assert {entry["label"] for entry in platform["strategy"]["matrix"]["include"]} == {
        "macos", "linux", "windows",
    }
    for job in verify["jobs"].values():
        assert "if" not in job
        assert "continue-on-error" not in job
        assert "permissions" not in job
        checkouts = [
            step for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        ]
        assert len(checkouts) == 1
        assert checkouts[0]["with"]["ref"] == "${{ github.sha }}"
        assert all("continue-on-error" not in step for step in job["steps"])
    commands = [step.get("run") for step in platform["steps"]]
    assert "pdm run check-full" in commands
    mvcc = [step for step in platform["steps"] if step.get("run") == "pdm run test-mvcc"]
    assert len(mvcc) == 2
    assert sum("DJANGO_PYTURSO_MVCC_DB" in step.get("env", {}) for step in mvcc) == 1


def test_only_verified_archives_are_transferred_to_publication() -> None:
    verify = workflow("verify-release.yml")
    package = verify["jobs"]["package-verification"]
    assert package["needs"] == "platform-verification"
    steps = package["steps"]
    build = next(index for index, step in enumerate(steps) if step.get("run") == "pdm run build")
    check = next(
        index for index, step in enumerate(steps)
        if step.get("name") == "Verify tag artifacts"
    )
    assert steps[check]["if"] == "github.ref_type == 'tag'"
    assert steps[check]["run"] == 'pdm run verify-release --expected-version "${GITHUB_REF_NAME#v}"'
    store = steps[-1]
    assert store["uses"].startswith("actions/upload-artifact@")
    assert "if" not in store
    assert build < check < len(steps) - 1
    assert store["with"]["if-no-files-found"] == "error"
    assert store["with"]["path"].splitlines() == ["dist/*.whl", "dist/*.tar.gz"]
    publish = workflow("python-publish.yml")["jobs"]["publish"]["steps"]
    assert len(publish) == 2
    download, upload = publish
    assert download["uses"].startswith("actions/download-artifact@")
    assert download["with"] == {"name": store["with"]["name"], "path": "dist"}
    assert upload["uses"].startswith("pypa/gh-action-pypi-publish@")
    assert "if" not in download and "if" not in upload
    assert all("continue-on-error" not in step for step in publish)


@pytest.mark.parametrize(
    ("filename", "job_name"),
    [
        ("python-package.yml", "quality"),
        ("python-package.yml", "current-dependencies"),
        ("verify-release.yml", "platform-verification"),
    ],
)
def test_runtime_advisory_audit_is_required_before_verification(
    filename: str, job_name: str
) -> None:
    job = workflow(filename)["jobs"][job_name]
    assert "if" not in job
    assert "continue-on-error" not in job
    steps = job["steps"]
    audits = [index for index, step in enumerate(steps) if step.get("run") == "pdm run audit"]
    assert len(audits) == 1
    audit = audits[0]
    assert "if" not in steps[audit]
    assert "continue-on-error" not in steps[audit]
    commands = [step.get("run", "") for step in steps]
    assert commands.index("pdm sync -G dev --clean") < audit
    assert audit < commands.index("pdm run check-full")
    assert all(index < audit for index, command in enumerate(commands) if command.startswith(
        "pdm update "
    ))
