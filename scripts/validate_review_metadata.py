"""Validate pull-request review classification and commit-bound evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

FIELD_PATTERN = re.compile(r"^- (?P<name>[^:]+):\s*(?P<value>.*)$", re.MULTILINE)
SHA_PATTERN = re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE)
REQUIRED_MAJOR_FIELDS = {
    "Deep codebase review report and reviewed commit",
    "Finding disposition ledger",
    "Reviewer-confirmed closure",
}
REQUIRED_STRUCTURAL_FIELDS = {
    "Structural clarity review report and reviewed commit",
}
DEPENDABOT_LOGINS = {"app/dependabot", "dependabot[bot]"}


def _fields(body: str) -> dict[str, str]:
    return {
        match.group("name").strip(): match.group("value").strip()
        for match in FIELD_PATTERN.finditer(body)
    }


def validate(body: str, head_sha: str) -> list[str]:
    fields = _fields(body)
    errors: list[str] = []
    classifications: dict[str, bool] = {}
    for name in ("Major code change", "Major structural change"):
        value = fields.get(name, "").lower()
        match = re.match(r"^(yes|no)\b(.+)$", value)
        if not match:
            errors.append(f"{name} must be yes/no with a rationale")
            continue
        classifications[name] = match.group(1) == "yes"

    required = set()
    if classifications.get("Major code change"):
        required.update(REQUIRED_MAJOR_FIELDS)
    if classifications.get("Major structural change"):
        required.update(REQUIRED_MAJOR_FIELDS | REQUIRED_STRUCTURAL_FIELDS)
    for name in sorted(required):
        value = fields.get(name, "")
        if not value or value.lower() == "n/a" or "<!--" in value:
            errors.append(f"{name} is required for this classification")
        elif "reviewed commit" in name.lower() and not SHA_PATTERN.search(value):
            errors.append(f"{name} must include a full commit SHA")

    final_tested = fields.get("Final tested commit", "")
    if not SHA_PATTERN.search(final_tested):
        errors.append("Final tested commit must include a full commit SHA")
    elif head_sha.lower() not in final_tested.lower():
        errors.append("Final tested commit must match the pull-request head SHA")
    return errors


def _event(path: Path) -> tuple[str, str, str] | None:
    event: dict[str, Any] = json.loads(path.read_text())
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    body = pull_request.get("body") or ""
    head = pull_request.get("head") or {}
    author = pull_request.get("user") or {}
    return str(body), str(head.get("sha") or ""), str(author.get("login") or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, default=os.environ.get("GITHUB_EVENT_PATH"))
    arguments = parser.parse_args()
    if arguments.event is None:
        print("Review metadata validation skipped outside a GitHub event.")
        return 0
    event = _event(arguments.event)
    if event is None:
        print("Review metadata validation skipped for a non-pull-request event.")
        return 0
    body, head_sha, author_login = event
    if author_login in DEPENDABOT_LOGINS:
        print("Review metadata validation skipped for Dependabot pull request.")
        return 0
    errors = validate(body, head_sha)
    if errors:
        print("Review metadata validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Review metadata validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
