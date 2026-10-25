"""Keep the runtime dependency floor and advisory gate effective."""

from __future__ import annotations

import io
import json
import subprocess
import tomllib
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message
from importlib.metadata import version
from pathlib import Path
from typing import Protocol, TypedDict
from urllib.response import addinfourl

import pytest
from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from scripts import audit_dependencies, verify_packages
from scripts.audit_dependencies import JSONValue

ROOT = Path(__file__).resolve().parents[1]


class ReleaseFixture(TypedDict):
    info: dict[str, str]
    vulnerabilities: list[JSONValue]


type Transform = Callable[[ReleaseFixture], object]


class Serve(Protocol):
    def __call__(
        self,
        transform: Transform = ...,
        *,
        raw: bytes | None = ...,
        status: int = ...,
        content_type: str = ...,
        error: Exception | None = ...,
    ) -> list[str]: ...


class _AuditResponse(addinfourl):
    msg = "test response"


@dataclass(frozen=True)
class LockedPackage:
    name: str
    version: str
    groups: tuple[str, ...]
    marker: str | None


def _locked_packages() -> list[LockedPackage]:
    with (ROOT / "pdm.lock").open("rb") as source:
        packages: object = tomllib.load(source).get("package")
    assert isinstance(packages, list)
    result: list[LockedPackage] = []
    for package in packages:
        assert isinstance(package, dict)
        name: object = package.get("name")
        version: object = package.get("version")
        groups: object = package.get("groups")
        marker: object = package.get("marker")
        assert isinstance(name, str) and isinstance(version, str)
        assert isinstance(groups, list)
        group_names: list[str] = []
        for group in groups:
            assert isinstance(group, str)
            group_names.append(group)
        assert marker is None or isinstance(marker, str)
        result.append(LockedPackage(name, version, tuple(group_names), marker))
    return result


def test_sqlparse_security_floor_is_declared_locked_and_installed() -> None:
    project = verify_packages._project_metadata()
    requirements = {
        canonicalize_name(requirement.name): requirement
        for requirement in map(Requirement, project.dependencies)
    }
    requirement = requirements[canonicalize_name("sqlparse")]
    assert "0.5.5" not in requirement.specifier
    assert version("sqlparse") in requirement.specifier
    packages = _locked_packages()
    locked = next(package for package in packages if package.name == "sqlparse")
    assert locked.version in requirement.specifier
    assert locked.version == version("sqlparse")


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Serve:
    """Replace only HTTPS transport; keep the complete audit and HTTP handlers."""

    def install(
        transform: Transform = lambda data: data,
        *,
        raw: bytes | None = None,
        status: int = 200,
        content_type: str = "application/json",
        error: Exception | None = None,
    ) -> list[str]:
        calls: list[str] = []

        def https_open(
            handler: urllib.request.HTTPSHandler, request: urllib.request.Request
        ) -> _AuditResponse:
            calls.append(request.full_url)
            assert request.host == "pypi.org"
            assert request.get_header("Accept") == "application/json"
            if error is not None:
                raise error
            name, release = request.selector.split("/")[2:4]
            data: ReleaseFixture = {
                "info": {"name": name, "version": release},
                "vulnerabilities": [],
            }
            body = raw if raw is not None else json.dumps(transform(data)).encode()
            headers = Message()
            headers["Content-Type"] = content_type
            if 300 <= status < 400:
                headers["Location"] = "https://example.invalid/advisories"
            return _AuditResponse(io.BytesIO(body), headers, request.full_url, status)

        monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", https_open)
        return calls

    return install


def _advisory(**changes: JSONValue) -> dict[str, JSONValue]:
    return {"id": "PYSEC-2026-1", "aliases": [], "fixed_in": [], "withdrawn": None, **changes}


def test_audit_checks_every_locked_runtime_release(
    serve: Serve, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = serve()
    audit_dependencies.main()
    packages = _locked_packages()
    expected = {
        (canonicalize_name(package.name), package.version)
        for package in packages
        if "default" in package.groups and (not package.marker or Marker(package.marker).evaluate())
    }
    assert {tuple(url.split("/")[4:6]) for url in calls} == expected
    assert len(calls) == len(expected)
    assert "No known vulnerabilities found" in capsys.readouterr().out


@pytest.mark.parametrize("vulnerabilities", [{}, "", None, False, 0, [None], [{}]])
def test_real_audit_rejects_invalid_vulnerability_data(
    serve: Serve, vulnerabilities: JSONValue, capsys: pytest.CaptureFixture[str]
) -> None:
    serve(lambda data: {**data, "vulnerabilities": vulnerabilities})
    with pytest.raises(audit_dependencies.AuditError):
        audit_dependencies.main()
    assert "No known vulnerabilities found" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "transform",
    [
        lambda data: {},
        lambda data: {"error": "feed unavailable"},
        lambda data: [],
        lambda data: {"info": data["info"]},
        lambda data: {**data, "info": None},
        lambda data: {**data, "info": {"name": data["info"]["name"]}},
        lambda data: {**data, "info": {"name": 42, "version": "1.0"}},
        lambda data: {**data, "info": {**data["info"], "name": "another-package"}},
        lambda data: {**data, "info": {**data["info"], "version": "0.0.0"}},
    ],
)
def test_real_audit_rejects_missing_or_wrong_release_data(
    serve: Serve, transform: Transform
) -> None:
    serve(transform)
    with pytest.raises(audit_dependencies.AuditError):
        audit_dependencies.main()


@pytest.mark.parametrize(
    "advisory",
    [
        _advisory(id=""),
        _advisory(id=42),
        _advisory(id="bad\nidentifier"),
        _advisory(aliases="CVE-2026-1"),
        _advisory(aliases=[None]),
        _advisory(fixed_in={}),
        _advisory(fixed_in=["not-a-version"]),
        _advisory(withdrawn=""),
        _advisory(withdrawn=False),
        _advisory(withdrawn="2026-10-17"),
        _advisory(withdrawn="2026-99-99T00:00:00Z"),
        {"id": "PYSEC-2026-1", "aliases": [], "fixed_in": []},
    ],
)
def test_real_audit_rejects_malformed_advisory_records(
    serve: Serve, advisory: dict[str, JSONValue]
) -> None:
    serve(lambda data: {**data, "vulnerabilities": [advisory]})
    with pytest.raises(audit_dependencies.AuditError):
        audit_dependencies.main()


def test_real_audit_rejects_active_advisories_even_without_a_fix(
    serve: Serve, capsys: pytest.CaptureFixture[str]
) -> None:
    serve(
        lambda data: (
            {**data, "vulnerabilities": [_advisory()]}
            if data["info"]["name"] == "sqlparse"
            else data
        )
    )
    with pytest.raises(audit_dependencies.AuditError, match="Known vulnerabilities"):
        audit_dependencies.main()
    output = capsys.readouterr().out
    assert "sqlparse==0.6.0: PYSEC-2026-1" in output
    assert "No known vulnerabilities found" not in output


@pytest.mark.parametrize("offset", ["+00:60", "-00:99", "+01:99", "-01:60", "+24:00", "-24:00"])
def test_real_audit_rejects_invalid_withdrawal_offsets(
    serve: Serve, offset: str, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = serve(
        lambda data: (
            {**data, "vulnerabilities": [_advisory(withdrawn=f"2026-10-17T00:00:00{offset}")]}
            if data["info"]["name"] == "sqlparse"
            else data
        )
    )
    with pytest.raises(audit_dependencies.AuditError, match="invalid withdrawal timestamp"):
        audit_dependencies.main()
    assert any("/sqlparse/" in url for url in calls)
    assert "No known vulnerabilities found" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "withdrawn",
    [
        "2026-10-17T00:00:00Z",
        "2026-10-17T00:00:00+00:00",
        "2026-10-17T00:00:00-00:00",
        "2026-10-17T00:00:00+23:59",
        "2026-10-17T00:00:00-23:59",
        "2026-10-17T00:00:00.123456+01:59",
    ],
)
def test_real_audit_accepts_valid_withdrawn_advisories(
    serve: Serve, withdrawn: str, capsys: pytest.CaptureFixture[str]
) -> None:
    serve(lambda data: {**data, "vulnerabilities": [_advisory(withdrawn=withdrawn)]})
    audit_dependencies.main()
    assert "No known vulnerabilities found" in capsys.readouterr().out


@pytest.mark.parametrize(
    "raw",
    [
        b"not JSON",
        b"\xff",
        b'{"vulnerabilities":{},"vulnerabilities":[]}',
        b'{"vulnerabilities":NaN}',
    ],
)
def test_real_audit_rejects_invalid_or_ambiguous_json(serve: Serve, raw: bytes) -> None:
    serve(raw=raw)
    with pytest.raises(audit_dependencies.AuditError):
        audit_dependencies.main()


@pytest.mark.parametrize("status", [204, 301, 302, 307, 308, 404, 429, 500])
def test_real_audit_rejects_errors_and_redirects(serve: Serve, status: int) -> None:
    calls = serve(status=status)
    with pytest.raises(audit_dependencies.AuditError):
        audit_dependencies.main()
    assert len(calls) == 1


def test_real_audit_rejects_wrong_content_type(serve: Serve) -> None:
    serve(content_type="text/html")
    with pytest.raises(audit_dependencies.AuditError):
        audit_dependencies.main()


def test_real_audit_rejects_large_responses(serve: Serve, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_dependencies, "MAX_RESPONSE_BYTES", 16)
    serve()
    with pytest.raises(audit_dependencies.AuditError, match="too much"):
        audit_dependencies.main()


def test_real_audit_rejects_timeouts(serve: Serve) -> None:
    serve(error=TimeoutError("feed timeout"))
    with pytest.raises(audit_dependencies.AuditError, match="feed timeout"):
        audit_dependencies.main()


@pytest.mark.parametrize("failed_stage", ["lock", "export"])
def test_failed_collection_does_not_query_the_feed(
    monkeypatch: pytest.MonkeyPatch, serve: Serve, failed_stage: str
) -> None:
    calls = serve()

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["check"] is True
        if command[1] == failed_stage:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("scripts.audit_dependencies.subprocess.run", run)
    with pytest.raises(subprocess.CalledProcessError):
        audit_dependencies.main()
    assert calls == []


@pytest.mark.parametrize(
    "content",
    [
        "",
        "sqlparse>=0.6.0",
        "sqlparse==0.6.*",
        "sqlparse @ https://example.invalid/a.whl",
        "sqlparse==0.6.0\nsqlparse==0.5.5",
    ],
)
def test_invalid_runtime_inventory_is_rejected(tmp_path: Path, content: str) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(content)
    with pytest.raises((audit_dependencies.AuditError, ValueError)):
        audit_dependencies._runtime_dependencies(requirements)
