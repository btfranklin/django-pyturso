"""Check locked runtime dependencies for published security advisories."""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class AuditError(RuntimeError):
    """The audit cannot establish a clean result."""


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise AuditError(f"PyPI returned an unexpected redirect (HTTP {code}).")


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"PyPI returned a duplicate JSON key: {key!r}.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise AuditError(f"PyPI returned an invalid JSON constant: {value}.")


def _runtime_dependencies(requirements: Path) -> dict[str, Version]:
    dependencies: dict[str, Version] = {}
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        specifiers = list(requirement.specifier)
        if requirement.url or len(specifiers) != 1 or specifiers[0].operator != "==":
            raise AuditError(f"Runtime dependency is not exactly pinned: {line!r}.")
        version = Version(specifiers[0].version)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        name = canonicalize_name(requirement.name, validate=True)
        if name in dependencies:
            raise AuditError(f"Duplicate runtime dependency: {name}.")
        dependencies[name] = version
    if not dependencies:
        raise AuditError("No runtime dependencies were exported for this platform.")
    return dependencies


def _validate_response(data: Any, name: str, version: Version) -> list[str]:
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict):
        raise AuditError(f"PyPI returned invalid release metadata for {name}.")
    info = data["info"]
    if not isinstance(info.get("name"), str) or not isinstance(info.get("version"), str):
        raise AuditError(f"PyPI omitted the release identity for {name}.")
    if (
        canonicalize_name(info["name"], validate=True) != name
        or Version(info["version"]) != version
    ):
        raise AuditError(f"PyPI returned a different release for {name}=={version}.")
    if not isinstance(data.get("vulnerabilities"), list):
        raise AuditError(f"PyPI omitted a valid vulnerability list for {name}=={version}.")

    active: list[str] = []
    for advisory in data["vulnerabilities"]:
        if not isinstance(advisory, dict):
            raise AuditError(f"PyPI returned an invalid advisory for {name}.")
        identifier = advisory.get("id")
        if (
            not isinstance(identifier, str)
            or not identifier
            or any(character.isspace() for character in identifier)
        ):
            raise AuditError(f"PyPI returned an invalid advisory identifier for {name}.")
        for field in ("aliases", "fixed_in"):
            values = advisory.get(field)
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise AuditError(f"PyPI returned an invalid advisory {field} for {name}.")
        for fixed_version in advisory["fixed_in"]:
            Version(fixed_version)
        if "withdrawn" not in advisory:
            raise AuditError(f"PyPI omitted the advisory withdrawal state for {name}.")
        withdrawn = advisory["withdrawn"]
        if withdrawn is None:
            active.append(identifier)
        elif (
            not isinstance(withdrawn, str)
            or re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                withdrawn,
            )
            is None
        ):
            raise AuditError(f"PyPI returned an invalid withdrawal timestamp for {name}.")
        else:
            datetime.datetime.fromisoformat(withdrawn)
    return active


def _audit_release(opener: urllib.request.OpenerDirector, name: str, version: Version) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{urllib.parse.quote(str(version), safe='')}/json"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener.open(request, timeout=15) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise AuditError(f"PyPI returned an unexpected response for {name}.")
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise AuditError(f"PyPI returned too much release data for {name}.")
        data = json.loads(
            body.decode("utf-8"), object_pairs_hook=_unique_keys, parse_constant=_reject_constant
        )
        return _validate_response(data, name, version)
    except (OSError, ValueError) as error:
        raise AuditError(f"Cannot audit {name}=={version}: {error}") from error


def main() -> None:
    subprocess.run(["pdm", "lock", "--check"], check=True, cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="django-pyturso-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        subprocess.run(
            [
                "pdm",
                "export",
                "--prod",
                "--format",
                "requirements",
                "--no-hashes",
                "--output",
                str(requirements),
            ],
            check=True,
            cwd=ROOT,
        )
        dependencies = _runtime_dependencies(requirements)
        opener = urllib.request.build_opener(RejectRedirects())
        vulnerable = False
        for name, version in dependencies.items():
            active = _audit_release(opener, name, version)
            if active:
                vulnerable = True
                print(f"{name}=={version}: {', '.join(sorted(set(active)))}")
        if vulnerable:
            raise AuditError("Known vulnerabilities were found in runtime dependencies.")
        print(f"No known vulnerabilities found in {len(dependencies)} runtime dependencies.")


if __name__ == "__main__":
    main()
