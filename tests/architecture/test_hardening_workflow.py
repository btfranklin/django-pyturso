"""Scheduled hardening workflow and local-command contract."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.workflow_policy import (
    command_position,
    job_run_lines,
    jobs,
    load_workflow,
    permissions,
    steps,
    triggers,
)

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "hardening.yml"
PYPROJECT = ROOT / "pyproject.toml"
REQUIRED_JOBS = {
    "mutation",
    "stress",
    "repeated-fast",
    "timezones",
    "locale",
    "ordering",
}


def test_hardening_workflow_is_non_release_scheduled_preparation() -> None:
    workflow = load_workflow(WORKFLOW)
    workflow_jobs = jobs(workflow)

    assert triggers(workflow) == {
        "schedule": [{"cron": "41 10 * * 2"}],
        "workflow_dispatch": None,
    }
    assert permissions(workflow) == {"contents": "read"}
    assert workflow["env"]["HARDENING_SEED"] == "20260713"
    assert set(workflow_jobs) == REQUIRED_JOBS
    for job_id, job in workflow_jobs.items():
        assert isinstance(job.get("timeout-minutes"), int), job_id
        assert job["timeout-minutes"] > 0, job_id
        assert "permissions" not in job


def test_hardening_workflow_commands_have_exact_lane_ownership() -> None:
    workflow_jobs = jobs(load_workflow(WORKFLOW))
    owned_commands = {
        "mutation": ("pdm run mutation-critical", "pdm run mutation-results"),
        "stress": ("pdm run test-stress",),
        "repeated-fast": ("pdm run hardening-repeated-fast",),
        "timezones": ("pdm run hardening-utc", "pdm run hardening-timezones"),
        "locale": ("pdm run hardening-locale",),
        "ordering": (
            "pdm run hardening-django-order",
            "pdm run hardening-random-order",
        ),
    }
    for owner, commands in owned_commands.items():
        positions = [
            command_position(workflow_jobs[owner], job_id=owner, command=command)
            for command in commands
        ]
        assert positions == sorted(positions)
        for other_job_id, other_job in workflow_jobs.items():
            if other_job_id != owner:
                assert not set(commands) & set(job_run_lines(other_job, job_id=other_job_id))

    mutation_steps = steps(workflow_jobs["mutation"], job_id="mutation")
    mutation_results = [
        step for step in mutation_steps if step.get("run") == "pdm run mutation-results"
    ]
    assert len(mutation_results) == 1
    assert mutation_results[0].get("if") == "always()"


def test_local_hardening_commands_and_random_order_dependency_are_declared() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = project["tool"]["pdm"]["scripts"]
    for name in (
        "hardening-utc",
        "hardening-timezones",
        "hardening-locale",
        "hardening-django-order",
        "hardening-random-order",
        "hardening-repeated-fast",
    ):
        assert name in scripts
    assert "pytest-random-order>=1.2.0" in project["dependency-groups"]["dev"]
