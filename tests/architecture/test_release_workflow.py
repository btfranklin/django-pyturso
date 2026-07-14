"""Release-workflow safety contracts."""

from pathlib import Path

from scripts.workflow_policy import (
    action_position,
    action_uses,
    command_position,
    command_starts_with,
    job_needs,
    job_run_lines,
    jobs,
    load_workflow,
    permissions,
    scalar_values,
    steps,
    triggers,
)

ROOT = Path(__file__).parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
DRAFT_WORKFLOW = WORKFLOW_ROOT / "create-draft-release.yml"
VERIFY_WORKFLOW = WORKFLOW_ROOT / "verify-release.yml"
PUBLISH_WORKFLOW = WORKFLOW_ROOT / "python-publish.yml"
TAG_TRIGGER = {"push": {"tags": ["v*.*.*"]}}


def test_draft_release_is_the_only_standard_tag_triggered_creator() -> None:
    workflow = load_workflow(DRAFT_WORKFLOW)
    workflow_jobs = jobs(workflow)

    assert workflow["name"] == "Create Draft Release"
    assert triggers(workflow) == TAG_TRIGGER
    assert permissions(workflow) == {"contents": "write"}
    assert set(workflow_jobs) == {"draft-release"}
    assert job_needs(workflow_jobs["draft-release"], job_id="draft-release") == ()

    creator_steps = [
        step
        for step in steps(workflow_jobs["draft-release"], job_id="draft-release")
        if step.get("uses") == "btfranklin/release-notes-scribe@v0"
    ]
    assert len(creator_steps) == 1
    assert creator_steps[0]["with"] == {
        "openai_api_key": "${{ secrets.OPENAI_API_KEY }}",
        "github_token": "${{ secrets.GITHUB_TOKEN }}",
        "include_github_generated_notes": "true",
    }
    assert not any(
        command_starts_with(line, ("pdm", "run", "verify-release"))
        for line in job_run_lines(workflow_jobs["draft-release"], job_id="draft-release")
    )
    creator_owners = [
        (path.name, use.job_id)
        for path in sorted(WORKFLOW_ROOT.glob("*.yml"))
        for use in action_uses(load_workflow(path))
        if use.reference == "btfranklin/release-notes-scribe@v0"
    ]
    assert creator_owners == [("create-draft-release.yml", "draft-release")]


def test_draft_and_verification_run_independently_from_the_same_tag() -> None:
    draft = load_workflow(DRAFT_WORKFLOW)
    verification = load_workflow(VERIFY_WORKFLOW)

    assert triggers(draft) == triggers(verification) == TAG_TRIGGER
    assert set(triggers(draft)) == {"push"}
    assert set(triggers(verification)) == {"push"}


def test_verify_release_owns_exact_tag_evidence_without_release_capability() -> None:
    workflow = load_workflow(VERIFY_WORKFLOW)
    workflow_jobs = jobs(workflow)

    assert workflow["name"] == "Verify Release"
    assert permissions(workflow) == {"contents": "read"}
    assert set(workflow_jobs) == {
        "preflight",
        "platform-verification",
        "deep-verification",
        "verify-release",
    }
    assert job_needs(workflow_jobs["preflight"], job_id="preflight") == ()
    assert job_needs(
        workflow_jobs["platform-verification"], job_id="platform-verification"
    ) == ("preflight",)
    assert job_needs(workflow_jobs["deep-verification"], job_id="deep-verification") == (
        "preflight",
    )
    assert job_needs(workflow_jobs["verify-release"], job_id="verify-release") == (
        "preflight",
        "platform-verification",
        "deep-verification",
    )

    assert permissions(
        workflow_jobs["verify-release"], location="jobs.verify-release.permissions"
    ) == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }
    for job_id, job in workflow_jobs.items():
        if "permissions" in job:
            assert permissions(job, location=f"jobs.{job_id}.permissions").get("contents") != (
                "write"
            )
    assert not any("${{ secrets." in value for value in scalar_values(workflow))
    assert all(
        use.reference != "btfranklin/release-notes-scribe@v0"
        for use in action_uses(workflow)
    )
    assert not any(
        command_starts_with(line, ("gh", "release", "create"))
        for job_id, job in workflow_jobs.items()
        for line in job_run_lines(job, job_id=job_id)
    )

    tag_identity = 'test "$(git rev-list -n 1 "$TAG")" = "$GITHUB_SHA"'
    assert command_position(
        workflow_jobs["preflight"], job_id="preflight", command=tag_identity
    ) < command_position(
        workflow_jobs["preflight"], job_id="preflight", command='git verify-tag "$TAG"'
    )
    assert command_position(
        workflow_jobs["verify-release"], job_id="verify-release", command=tag_identity
    ) < command_position(
        workflow_jobs["verify-release"],
        job_id="verify-release",
        command='git verify-tag "$TAG"',
    )


def test_verify_release_commands_have_exact_job_ownership_and_order() -> None:
    workflow_jobs = jobs(load_workflow(VERIFY_WORKFLOW))
    deep_job = workflow_jobs["deep-verification"]
    deep_commands = (
        "pdm run coverage-check",
        "pdm run test-differential",
        "pdm run test-upstream",
        "pdm run test-stress",
        "pdm run test-performance",
        "pdm run security",
        "pdm run reproducible-build",
        "pdm run mutation-critical",
        "pdm run mutation-results",
    )
    positions = [
        command_position(deep_job, job_id="deep-verification", command=command)
        for command in deep_commands
    ]
    assert positions == sorted(positions)
    for other_job_id in ("preflight", "platform-verification", "verify-release"):
        other_lines = job_run_lines(workflow_jobs[other_job_id], job_id=other_job_id)
        assert not set(deep_commands) & set(other_lines)

    release_job = workflow_jobs["verify-release"]
    assert command_position(
        release_job, job_id="verify-release", command="pdm run build"
    ) < command_position(
        release_job,
        job_id="verify-release",
        command='pdm run verify-release --expected-version "${TAG#v}"',
    )
    assert command_position(
        release_job, job_id="verify-release", command="pdm run audit"
    ) < command_position(
        release_job, job_id="verify-release", command="pdm run sbom"
    ) < command_position(
        release_job, job_id="verify-release", command="cd dist"
    ) < action_position(
        release_job,
        job_id="verify-release",
        reference="actions/attest-build-provenance@v4",
    )


def test_publish_is_the_only_release_published_trusted_publishing_job() -> None:
    workflow = load_workflow(PUBLISH_WORKFLOW)
    workflow_jobs = jobs(workflow)
    publish = workflow_jobs["publish"]

    assert triggers(workflow) == {"release": {"types": ["published"]}}
    assert permissions(workflow) == {"contents": "read"}
    assert set(workflow_jobs) == {"publish"}
    assert publish["environment"] == "release"
    assert permissions(publish, location="jobs.publish.permissions") == {"id-token": "write"}
    assert job_needs(publish, job_id="publish") == ()

    ordered_positions = (
        action_position(publish, job_id="publish", reference="actions/checkout@v7"),
        action_position(publish, job_id="publish", reference="actions/setup-python@v6"),
        action_position(publish, job_id="publish", reference="pdm-project/setup-pdm@v4"),
        command_position(publish, job_id="publish", command="pdm build"),
        action_position(
            publish,
            job_id="publish",
            reference="pypa/gh-action-pypi-publish@release/v1",
        ),
    )
    assert ordered_positions == tuple(sorted(ordered_positions))

    owners = [
        (path.name, use.job_id)
        for path in sorted(WORKFLOW_ROOT.glob("*.yml"))
        for use in action_uses(load_workflow(path))
        if use.reference == "pypa/gh-action-pypi-publish@release/v1"
    ]
    assert owners == [("python-publish.yml", "publish")]
