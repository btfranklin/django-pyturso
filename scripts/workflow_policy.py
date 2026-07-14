"""Structured helpers for inspecting GitHub Actions workflows."""

from __future__ import annotations

import shlex
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

WorkflowMapping = dict[str, Any]


@dataclass(frozen=True)
class ActionUse:
    """One executable action reference and its owning job and optional step."""

    job_id: str
    step_index: int | None
    reference: str


def _mapping(value: object, *, location: str) -> WorkflowMapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"{location} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{location} keys must be strings")
    return dict(value)


def _sequence(value: object, *, location: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{location} must be a sequence")
    return list(value)


def load_workflow(path: Path) -> WorkflowMapping:
    """Load a workflow with YAML 1.2 scalar rules and validate its root shape."""
    yaml = YAML(typ="safe")
    yaml.version = (1, 2)
    document = yaml.load(path.read_text(encoding="utf-8"))
    return _mapping(document, location=path.name)


def triggers(workflow: WorkflowMapping) -> WorkflowMapping:
    """Return the workflow's event mapping."""
    return _mapping(workflow.get("on"), location="on")


def permissions(owner: WorkflowMapping, *, location: str = "permissions") -> WorkflowMapping:
    """Return one workflow or job permission mapping."""
    return _mapping(owner.get("permissions"), location=location)


def jobs(workflow: WorkflowMapping) -> dict[str, WorkflowMapping]:
    """Return jobs keyed by their executable job identifiers."""
    raw_jobs = _mapping(workflow.get("jobs"), location="jobs")
    return {
        job_id: _mapping(job, location=f"jobs.{job_id}")
        for job_id, job in raw_jobs.items()
    }


def steps(job: WorkflowMapping, *, job_id: str) -> list[WorkflowMapping]:
    """Return the ordered executable steps for one job."""
    raw_steps = _sequence(job.get("steps"), location=f"jobs.{job_id}.steps")
    return [
        _mapping(step, location=f"jobs.{job_id}.steps[{index}]")
        for index, step in enumerate(raw_steps)
    ]


def job_needs(job: WorkflowMapping, *, job_id: str) -> tuple[str, ...]:
    """Normalize a job's dependency identifiers without changing their order."""
    value = job.get("needs")
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(
        str(item) for item in _sequence(value, location=f"jobs.{job_id}.needs")
    )


def action_uses(workflow: WorkflowMapping) -> list[ActionUse]:
    """Return actual job- and step-level ``uses`` references."""
    found: list[ActionUse] = []
    for job_id, job in jobs(workflow).items():
        job_reference = job.get("uses")
        if job_reference is not None:
            if not isinstance(job_reference, str):
                raise ValueError(f"jobs.{job_id}.uses must be text")
            found.append(ActionUse(job_id, None, job_reference))
        if "steps" not in job:
            continue
        for index, step in enumerate(steps(job, job_id=job_id)):
            reference = step.get("uses")
            if reference is None:
                continue
            if not isinstance(reference, str):
                raise ValueError(f"jobs.{job_id}.steps[{index}].uses must be text")
            found.append(ActionUse(job_id, index, reference))
    return found


def run_lines(step: WorkflowMapping, *, location: str) -> tuple[str, ...]:
    """Return normalized executable lines from one ``run`` step."""
    value = step.get("run")
    if value is None:
        return ()
    if not isinstance(value, str):
        raise ValueError(f"{location}.run must be text")
    return tuple(
        line
        for raw_line in value.splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    )


def job_run_lines(job: WorkflowMapping, *, job_id: str) -> tuple[str, ...]:
    """Return executable lines in step order for one job."""
    return tuple(
        line
        for index, step in enumerate(steps(job, job_id=job_id))
        for line in run_lines(step, location=f"jobs.{job_id}.steps[{index}]")
    )


def command_position(
    job: WorkflowMapping, *, job_id: str, command: str
) -> tuple[int, int]:
    """Locate an exact executable command by step and line index."""
    matches = [
        (step_index, line_index)
        for step_index, step in enumerate(steps(job, job_id=job_id))
        for line_index, line in enumerate(
            run_lines(step, location=f"jobs.{job_id}.steps[{step_index}]")
        )
        if line == command
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"jobs.{job_id} must own exactly one command {command!r}; found {len(matches)}"
        )
    return matches[0]


def action_position(
    job: WorkflowMapping, *, job_id: str, reference: str
) -> tuple[int, int]:
    """Locate an exact step action using the same ordering shape as commands."""
    matches = [
        (index, 0)
        for index, step in enumerate(steps(job, job_id=job_id))
        if step.get("uses") == reference
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"jobs.{job_id} must own exactly one action {reference!r}; found {len(matches)}"
        )
    return matches[0]


def scalar_values(value: object) -> Iterator[str]:
    """Yield parsed scalar strings, excluding comments and YAML syntax."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from scalar_values(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            yield from scalar_values(nested)


def command_starts_with(command: str, prefix: tuple[str, ...]) -> bool:
    """Match the leading shell tokens of a single normalized command line."""
    try:
        tokens = tuple(shlex.split(command, comments=True, posix=True))
    except ValueError:
        return False
    return tokens[: len(prefix)] == prefix


def normalized_expression(value: object, *, location: str) -> str:
    """Normalize insignificant whitespace in one GitHub expression."""
    if not isinstance(value, str):
        raise ValueError(f"{location} must be text")
    return "".join(value.split())
