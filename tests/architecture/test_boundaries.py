"""Mechanical package-boundary checks.

These checks parse Python syntax rather than searching repository text. This
keeps documentation, error messages, provenance notes, and the explicitly
allowlisted differential reference backend out of the runtime boundary.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "django_pyturso"
FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "httpx",
    "grpc",
    "libsql",
    "libsql_client",
    "requests",
    "socket",
    "sqlite3",
    "turso_client",
    "websockets",
}
FORBIDDEN_IMPORT_PREFIXES = {"http.client", "urllib.request"}


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def boundary_violations(source: str, *, filename: str = "<source>") -> list[str]:
    """Return actionable runtime-boundary violations from Python source."""
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []
    protected_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                bound_name = alias.asname or root
                if root in FORBIDDEN_IMPORT_ROOTS or any(
                    alias.name == prefix or alias.name.startswith(f"{prefix}.")
                    for prefix in FORBIDDEN_IMPORT_PREFIXES
                ):
                    violations.append(
                        f"line {node.lineno}: forbidden runtime import {alias.name!r}"
                    )
                if alias.name == "turso":
                    protected_names.add(bound_name)
                    if alias.asname != "Database":
                        violations.append(
                            f"line {node.lineno}: top-level turso must be imported as Database"
                        )
                elif alias.name.startswith("turso."):
                    violations.append(
                        f"line {node.lineno}: private or implementation turso import {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS or any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            ):
                violations.append(f"line {node.lineno}: forbidden runtime import {module!r}")
            if module == "turso" or module.startswith("turso."):
                violations.append(
                    f"line {node.lineno}: import driver symbols only through top-level turso"
                )
            if module == "django.db.backends.sqlite3" or module.startswith(
                "django.db.backends.sqlite3."
            ):
                violations.append(
                    f"line {node.lineno}: forbidden Django SQLite backend import {module!r}"
                )
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                violations.append(
                    f"line {node.lineno}: dynamic imports are forbidden in runtime code"
                )
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "setattr"
                and node.args
                and _root_name(node.args[0]) in protected_names
            ):
                violations.append(
                    f"line {node.lineno}: monkey-patching imported driver objects is forbidden"
                )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and _root_name(node.func) == "importlib"
            ):
                violations.append(
                    f"line {node.lineno}: dynamic imports are forbidden in runtime code"
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets: list[ast.expr]
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            else:
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and _root_name(target) in protected_names:
                    violations.append(
                        f"line {node.lineno}: monkey-patching imported driver objects is forbidden"
                    )

    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, (ast.Name, ast.Attribute)):
            continue
        targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                violations.append(
                    f"line {node.lineno}: module-level compatibility aliases are forbidden"
                )

    return violations


def test_runtime_package_respects_database_boundary() -> None:
    violations = [
        f"{path.relative_to(SOURCE_ROOT)}: {violation}"
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        for violation in boundary_violations(path.read_text(), filename=str(path))
    ]
    assert not violations, "Runtime architecture boundary violations:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("import sqlite3\n", "forbidden runtime import"),
        ("from django.db.backends.sqlite3.base import DatabaseWrapper\n", "SQLite backend"),
        ("from turso.lib import Connection\n", "top-level turso"),
        ("import libsql_client\n", "forbidden runtime import"),
        ("import requests\n", "forbidden runtime import"),
        ("import turso as Database\nDatabase.connect = lambda: None\n", "monkey-patching"),
        ("import turso as Database\nsetattr(Database, 'connect', None)\n", "monkey-patching"),
        ("from urllib.request import urlopen\n", "forbidden runtime import"),
        ("old_backend = NewBackend\n", "compatibility aliases"),
        ("__import__('sqlite3')\n", "dynamic imports"),
    ],
)
def test_boundary_failures_are_actionable(source: str, expected: str) -> None:
    assert any(expected in violation for violation in boundary_violations(source))
