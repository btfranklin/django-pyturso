"""Keep publication behind verification of the same commit and archives."""

from pathlib import Path

import pytest
import yaml

from scripts.audit_dependencies import JSONValue, _json_value

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _mapping(value: JSONValue) -> dict[str, JSONValue]:
    assert isinstance(value, dict)
    return value


def _mappings(value: JSONValue) -> list[dict[str, JSONValue]]:
    assert isinstance(value, list)
    return [_mapping(item) for item in value]


def _string(value: JSONValue) -> str:
    assert isinstance(value, str)
    return value


def _jobs(document: dict[str, JSONValue]) -> dict[str, dict[str, JSONValue]]:
    return {name: _mapping(job) for name, job in _mapping(document["jobs"]).items()}


def _steps(job: dict[str, JSONValue]) -> list[dict[str, JSONValue]]:
    return _mappings(job["steps"])


def workflow(name: str) -> dict[str, JSONValue]:
    # BaseLoader preserves GitHub's `on` key instead of treating it as a Boolean.
    with (WORKFLOWS / name).open() as source:
        document: object = yaml.load(source, Loader=yaml.BaseLoader)
    return _mapping(_json_value(document))


def test_publication_requires_successful_local_release_verification() -> None:
    publish = workflow("python-publish.yml")
    assert publish["on"] == {"release": {"types": ["published"]}}
    gate = _jobs(publish)["verify-release"]
    assert gate["uses"] == "./.github/workflows/verify-release.yml"
    assert "if" not in gate
    assert "continue-on-error" not in gate
    upload = _jobs(publish)["publish"]
    assert upload["needs"] == "verify-release"
    assert "if" not in upload
    assert "continue-on-error" not in upload
    assert upload["environment"] == "release"
    assert publish["permissions"] == {"contents": "read"}
    assert upload["permissions"] == {"contents": "read", "id-token": "write"}


def test_release_verification_checks_all_platforms_and_mvcc_modes_at_the_event_commit() -> None:
    verify = workflow("verify-release.yml")
    assert "workflow_call" in _mapping(verify["on"])
    assert verify["permissions"] == {"contents": "read"}
    platform = _jobs(verify)["platform-verification"]
    strategy = _mapping(platform["strategy"])
    matrix = _mapping(strategy["matrix"])
    assert {entry["label"] for entry in _mappings(matrix["include"])} == {
        "macos",
        "linux",
        "windows",
    }
    for job in _jobs(verify).values():
        assert "if" not in job
        assert "continue-on-error" not in job
        assert "permissions" not in job
        checkouts = [
            step
            for step in _steps(job)
            if _string(step.get("uses", "")).startswith("actions/checkout@")
        ]
        assert len(checkouts) == 1
        assert _mapping(checkouts[0]["with"])["ref"] == "${{ github.sha }}"
        assert all("continue-on-error" not in step for step in _steps(job))
    commands = [step.get("run") for step in _steps(platform)]
    assert "pdm run check-full" in commands
    mvcc = [step for step in _steps(platform) if step.get("run") == "pdm run test-mvcc"]
    assert len(mvcc) == 2
    assert sum("DJANGO_PYTURSO_MVCC_DB" in _mapping(step.get("env", {})) for step in mvcc) == 1


def test_only_verified_archives_are_transferred_to_publication() -> None:
    verify = workflow("verify-release.yml")
    package = _jobs(verify)["package-verification"]
    assert package["needs"] == "platform-verification"
    steps = _steps(package)
    build = next(index for index, step in enumerate(steps) if step.get("run") == "pdm run build")
    check = next(
        index for index, step in enumerate(steps) if step.get("name") == "Verify tag artifacts"
    )
    assert steps[check]["if"] == "github.ref_type == 'tag'"
    assert steps[check]["run"] == 'pdm run verify-release --expected-version "${GITHUB_REF_NAME#v}"'
    store = steps[-1]
    assert _string(store["uses"]).startswith("actions/upload-artifact@")
    assert "if" not in store
    assert build < check < len(steps) - 1
    assert _mapping(store["with"])["if-no-files-found"] == "error"
    assert _string(_mapping(store["with"])["path"]).splitlines() == ["dist/*.whl", "dist/*.tar.gz"]
    publish = _steps(_jobs(workflow("python-publish.yml"))["publish"])
    assert len(publish) == 2
    download, upload = publish
    assert _string(download["uses"]).startswith("actions/download-artifact@")
    assert download["with"] == {"name": _mapping(store["with"])["name"], "path": "dist"}
    assert _string(upload["uses"]).startswith("pypa/gh-action-pypi-publish@")
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
    job = _jobs(workflow(filename))[job_name]
    assert "if" not in job
    assert "continue-on-error" not in job
    steps = _steps(job)
    audits = [index for index, step in enumerate(steps) if step.get("run") == "pdm run audit"]
    assert len(audits) == 1
    audit = audits[0]
    assert "if" not in steps[audit]
    assert "continue-on-error" not in steps[audit]
    commands = [_string(step.get("run", "")) for step in steps]
    assert commands.index("pdm sync -G dev --clean") < audit
    assert audit < commands.index("pdm run check-full")
    assert all(
        index < audit for index, command in enumerate(commands) if command.startswith("pdm update ")
    )
