"""Validate before creating a draft; rebuild and publish from its tag afterward."""

import tomllib
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


def test_publication_only_builds_the_release_tag_and_uploads() -> None:
    publish = workflow("python-publish.yml")
    assert publish["on"] == {"release": {"types": ["published"]}}
    assert publish["permissions"] == {"contents": "read"}
    assert set(_jobs(publish)) == {"publish"}
    upload = _jobs(publish)["publish"]
    assert "needs" not in upload
    assert upload["environment"] == "release"
    assert upload["permissions"] == {"contents": "read", "id-token": "write"}
    steps = _steps(upload)
    checkout, python, pdm, build, publish_step = steps
    assert _string(checkout["uses"]).startswith("actions/checkout@")
    assert checkout["with"] == {
        "ref": "${{ github.event.release.tag_name }}",
        "fetch-depth": "0",
    }
    assert _string(python["uses"]).startswith("actions/setup-python@")
    assert _string(pdm["uses"]).startswith("pdm-project/setup-pdm@")
    assert build["run"] == "pdm build"
    assert _string(publish_step["uses"]).startswith("pypa/gh-action-pypi-publish@")
    assert all("if" not in step and "continue-on-error" not in step for step in steps)
    # A build must not invoke a hidden validation suite through a PDM build hook.
    with (WORKFLOWS.parents[1] / "pyproject.toml").open("rb") as manifest:
        scripts = tomllib.load(manifest)["tool"]["pdm"]["scripts"]
    assert not {"pre_build", "post_build"}.intersection(scripts)


def test_draft_requires_all_reusable_validation_before_creating_a_release() -> None:
    draft = workflow("create-draft-release.yml")
    assert draft["on"] == {"push": {"tags": ["v*.*.*"]}}
    assert draft["permissions"] == {"contents": "read"}
    gate = _jobs(draft)["verify-release"]
    assert gate["uses"] == "./.github/workflows/verify-release.yml"
    create = _jobs(draft)["draft-release"]
    assert create["needs"] == "verify-release"
    assert create["permissions"] == {"contents": "write"}
    for job in (gate, create):
        assert "if" not in job
        assert "continue-on-error" not in job
    steps = _steps(create)
    assert _mapping(steps[0]["with"])["ref"] == "${{ github.sha }}"
    assert _string(steps[-1]["uses"]).startswith("btfranklin/release-notes-scribe@")
    assert _mapping(steps[-1]["with"])["draft"] == "true"
    assert _mapping(steps[-1]["with"])["create_release"] == "true"
    assert all("if" not in step and "continue-on-error" not in step for step in steps)

    verify = workflow("verify-release.yml")
    assert set(_mapping(verify["on"])) == {"workflow_call", "workflow_dispatch"}
    validation = _jobs(verify)["validation"]
    assert validation["uses"] == "./.github/workflows/python-package.yml"
    assert validation["with"] == {"release": "true"}
    security = _jobs(verify)["security"]
    assert security["uses"] == "./.github/workflows/codeql.yml"
    assert _mapping(security["permissions"])["security-events"] == "write"
    for job in (validation, security):
        assert "if" not in job
        assert "continue-on-error" not in job
    assert "workflow_call" in _mapping(workflow("codeql.yml")["on"])


def test_reusable_ci_retains_platform_current_dependency_and_package_checks() -> None:
    ci = workflow("python-package.yml")
    assert "workflow_call" in _mapping(ci["on"])
    jobs = _jobs(ci)
    platform = jobs["quality"]
    strategy = _mapping(platform["strategy"])
    assert strategy["fail-fast"] == "false"
    matrix = _string(_mapping(strategy["matrix"])["os"])
    assert "inputs.release" in matrix
    for runner in ("macos-15", "ubuntu-24.04", "windows-2025"):
        assert runner in matrix
    for job in (platform, jobs["current-dependencies"]):
        assert "if" not in job
        assert "continue-on-error" not in job
        steps = _steps(job)
        assert all("continue-on-error" not in step for step in steps)
        commands = [step.get("run") for step in steps]
        assert "pdm run check-full" in commands
        assert "pdm run test-django-regressions --ds=tests.settings.turso_file" in commands
        mvcc = [step for step in steps if step.get("run") == "pdm run test-mvcc"]
        assert len(mvcc) == 2
        assert sum("DJANGO_PYTURSO_MVCC_DB" in _mapping(step.get("env", {})) for step in mvcc) == 1
    current = [step.get("run") for step in _steps(jobs["current-dependencies"])]
    assert "pdm update --stable --update-eager Django pyturso sqlparse" in current
    assert "pdm update -G dev --stable --update-eager django-stubs" in current
    assert jobs["dependency-review"]["if"] == "github.event_name == 'pull_request'"
    steps = _steps(platform)
    checkout = steps[0]
    assert _mapping(checkout["with"])["fetch-depth"] == "0"
    commands = [step.get("run") for step in steps]
    assert "pdm run build" in commands
    tag_check = next(step for step in steps if step.get("name") == "Verify tag artifacts")
    assert tag_check["if"] == "github.ref_type == 'tag'"
    assert tag_check["shell"] == "bash"
    assert tag_check["run"] == 'pdm run verify-release --expected-version "${GITHUB_REF_NAME#v}"'
    assert commands.index("pdm run build") < steps.index(tag_check)
    branch_check = next(step for step in steps if step.get("name") == "Verify branch artifacts")
    assert branch_check["if"] == "github.ref_type != 'tag'"
    assert branch_check["run"] == "pdm run package-test"


@pytest.mark.parametrize("job_name", ["quality", "current-dependencies"])
def test_runtime_advisory_audit_is_required_before_verification(job_name: str) -> None:
    job = _jobs(workflow("python-package.yml"))[job_name]
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


@pytest.mark.parametrize("filename", ["python-package.yml", "python-publish.yml"])
def test_pdm_uses_supported_python_in_every_install_job(filename: str) -> None:
    pdm_setups = [
        step
        for job in _jobs(workflow(filename)).values()
        for step in _steps(job)
        if _string(step.get("uses", "")).startswith("pdm-project/setup-pdm@")
    ]
    assert pdm_setups
    for setup in pdm_setups:
        assert _mapping(setup["with"]).get("python-version") == "3.14"
