"""Validate security exceptions and GitHub workflow policy."""

from __future__ import annotations

import datetime as dt
import importlib.metadata
import re
import tomllib
from collections import deque
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS_PATH = ROOT / "tests" / "manifests" / "security-exceptions.toml"
DEPENDENCY_REVIEW_PATH = ROOT / ".github" / "dependency-review-config.yml"
WORKFLOW_ROOT = ROOT / ".github" / "workflows"

REQUIRED_EXCEPTION_FIELDS = {
    "package",
    "issue_type",
    "identifier",
    "affected_range",
    "rationale",
    "owner",
    "compensating_control",
    "approved_on",
    "expires_on",
}
ALLOWED_ISSUE_TYPES = {"advisory", "license"}
CLASSIFIER_LICENSES = {
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
}
ACTION_VERSION = re.compile(
    r"^\s*(?:-\s+)?uses:\s+(?P<action>[^\s@]+)@(?P<version>v\d+|release/v\d+)\s*$"
)


def _require_nonempty_text(entry: dict[str, Any], field: str, index: int) -> None:
    value = entry[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"security exception {index} field {field!r} must be nonempty text")


def validate_exceptions(*, today: dt.date | None = None) -> None:
    data = tomllib.loads(EXCEPTIONS_PATH.read_text())
    if data.get("schema_version") != 1:
        raise ValueError("security exceptions schema_version must be 1")
    unknown_top_level = set(data) - {"schema_version", "exception"}
    if unknown_top_level:
        raise ValueError(f"unknown security exception manifest keys: {sorted(unknown_top_level)}")
    entries = data.get("exception", [])
    if not isinstance(entries, list):
        raise ValueError("security exception entries must use [[exception]] tables")
    current_date = today or dt.date.today()
    identities: set[tuple[str, str, str]] = set()
    for index, raw_entry in enumerate(entries, start=1):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"security exception {index} must be a table")
        missing = REQUIRED_EXCEPTION_FIELDS - set(raw_entry)
        unknown = set(raw_entry) - REQUIRED_EXCEPTION_FIELDS
        if missing or unknown:
            details = f"missing={sorted(missing)} unknown={sorted(unknown)}"
            raise ValueError(f"security exception {index} has {details}")
        entry = dict(raw_entry)
        for field in REQUIRED_EXCEPTION_FIELDS - {"approved_on", "expires_on"}:
            _require_nonempty_text(entry, field, index)
        if entry["issue_type"] not in ALLOWED_ISSUE_TYPES:
            raise ValueError(f"security exception {index} issue_type must be advisory or license")
        approved_on = entry["approved_on"]
        expires_on = entry["expires_on"]
        if not isinstance(approved_on, dt.date) or not isinstance(expires_on, dt.date):
            raise ValueError(
                f"security exception {index} approval and expiry must be TOML local dates"
            )
        if expires_on <= approved_on:
            raise ValueError(f"security exception {index} must expire after approval")
        if expires_on < current_date:
            raise ValueError(f"security exception {index} expired on {expires_on.isoformat()}")
        identity = (entry["package"].casefold(), entry["issue_type"], entry["identifier"])
        if identity in identities:
            raise ValueError(f"duplicate security exception {identity!r}")
        identities.add(identity)


def validate_dependency_review_policy() -> None:
    text = DEPENDENCY_REVIEW_PATH.read_text()
    required_lines = {
        "fail-on-severity: high",
        "  - runtime",
        "- MIT",
        "- BSD-3-Clause",
        "- PSF-2.0",
    }
    missing = sorted(line for line in required_lines if line not in text)
    if missing:
        raise ValueError(f"dependency-review policy is missing required settings: {missing}")
    if "license-check: true" not in text:
        raise ValueError("dependency-review license-check must remain enabled")


def _allowed_licenses() -> set[str]:
    text = DEPENDENCY_REVIEW_PATH.read_text()
    match = re.search(r"^allow-licenses:\n(?P<items>(?:  - .+\n?)+)", text, re.MULTILINE)
    if match is None:
        raise ValueError("dependency-review policy must define allow-licenses")
    return {line.removeprefix("  - ").strip() for line in match.group("items").splitlines()}


def _distribution_license(distribution: importlib.metadata.Distribution) -> str | None:
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return expression.strip()
    declared = distribution.metadata.get("License")
    if declared:
        return declared.strip()
    for classifier in distribution.metadata.get_all("Classifier", []):
        if classifier in CLASSIFIER_LICENSES:
            return CLASSIFIER_LICENSES[classifier]
    return None


def _runtime_distributions() -> list[importlib.metadata.Distribution]:
    pending = deque(["django-pyturso"])
    found: dict[str, importlib.metadata.Distribution] = {}
    while pending:
        name = canonicalize_name(pending.popleft())
        if name in found:
            continue
        distribution = importlib.metadata.distribution(name)
        found[name] = distribution
        for raw_requirement in distribution.requires or []:
            requirement = Requirement(raw_requirement)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            pending.append(requirement.name)
    return [found[name] for name in sorted(found)]


def _active_license_exceptions() -> set[tuple[str, str]]:
    data = tomllib.loads(EXCEPTIONS_PATH.read_text())
    today = dt.date.today()
    return {
        (canonicalize_name(entry["package"]), entry["identifier"])
        for entry in data.get("exception", [])
        if entry["issue_type"] == "license" and entry["expires_on"] >= today
    }


def validate_runtime_licenses() -> None:
    allowed = _allowed_licenses()
    exceptions = _active_license_exceptions()
    rejected: list[str] = []
    for distribution in _runtime_distributions():
        package = canonicalize_name(distribution.metadata["Name"])
        license_id = _distribution_license(distribution) or "UNKNOWN"
        if license_id not in allowed and (package, license_id) not in exceptions:
            rejected.append(f"{package}=={distribution.version}: {license_id}")
    if rejected:
        raise ValueError(
            "runtime dependencies have unknown or unapproved licenses: " + ", ".join(rejected)
        )


def validate_workflows() -> None:
    workflows = sorted(WORKFLOW_ROOT.glob("*.yml"))
    if not workflows:
        raise ValueError("no GitHub workflows found")
    for path in workflows:
        text = path.read_text()
        expected_contents_permission = (
            "write" if path.name == "create-draft-release.yml" else "read"
        )
        if f"permissions:\n    contents: {expected_contents_permission}" not in text:
            raise ValueError(
                f"{path.name} must default to contents: {expected_contents_permission}"
            )
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "uses:" not in line:
                continue
            target = line.split("uses:", 1)[1].strip()
            if target.startswith(("./", "docker://")):
                continue
            if not ACTION_VERSION.match(line):
                raise ValueError(
                    f"{path.name}:{lineno} action must use a major release channel such as "
                    "v4 or release/v1; minor, patch, and commit SHA pins are forbidden"
                )
        if path.name == "python-package.yml":
            if "secrets." in text or re.search(r"^\s+\w[\w-]*:\s+write\s*$", text, re.MULTILINE):
                raise ValueError(
                    "pull-request workflow must not receive secrets or write permission"
                )
            if "actions/dependency-review-action@" not in text:
                raise ValueError("pull-request workflow must run dependency review")
        if path.name == "codeql.yml" and "language: [python, actions]" not in text:
            raise ValueError("CodeQL must scan both Python and GitHub Actions workflows")


def main() -> None:
    validate_exceptions()
    validate_dependency_review_policy()
    validate_runtime_licenses()
    validate_workflows()
    print("Security exceptions, dependency policy, and workflows are valid.")


if __name__ == "__main__":
    main()
