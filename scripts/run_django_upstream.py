#!/usr/bin/env python3
"""Run the project-owned Django upstream compatibility lane."""

from __future__ import annotations

import argparse
import ast
import contextlib
import os
import shlex
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "tests/manifests/upstream-expectations.toml"
ALLOWED_CATEGORIES = frozenset({"backend", "schema", "introspection", "transactions", "query"})
ALLOWED_OUTCOMES = frozenset({"pass", "skip"})


class ConfigurationError(ValueError):
    """Raised when the upstream lane configuration isn't internally consistent."""


@dataclass(frozen=True)
class Source:
    repository: str
    tag: str
    commit: str
    installed_version: str


@dataclass(frozen=True)
class Runner:
    settings: str
    parallel: int
    default_profile: str
    expected_passes: int
    expected_skips: int
    expected_failures: int


@dataclass(frozen=True)
class Expectation:
    label: str
    category: str
    profile: str
    outcome: str
    relevance: str
    reason_code: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class Manifest:
    source: Source
    runner: Runner
    expectations: tuple[Expectation, ...]


def _required_string(table: dict[str, Any], key: str, context: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{context}.{key} must be a non-empty string")
    return value


def _required_table(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ConfigurationError(f"{key} must be a table")
    return cast(dict[str, Any], value)


def _required_count(table: dict[str, Any], key: str, context: str) -> int:
    value = table.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigurationError(f"{context}.{key} must be a non-negative integer")
    return value


def _optional_string(table: dict[str, Any], key: str, context: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{context}.{key} must be a non-empty string when present")
    return value


def load_manifest(path: Path) -> Manifest:
    with path.open("rb") as stream:
        document = tomllib.load(stream)

    if document.get("schema_version") != 1:
        raise ConfigurationError("schema_version must be 1")

    source_table = _required_table(document, "source")
    source = Source(
        repository=_required_string(source_table, "repository", "source"),
        tag=_required_string(source_table, "tag", "source"),
        commit=_required_string(source_table, "commit", "source"),
        installed_version=_required_string(source_table, "installed_version", "source"),
    )
    if len(source.commit) != 40 or any(
        character not in "0123456789abcdef" for character in source.commit
    ):
        raise ConfigurationError("source.commit must be a lowercase 40-character Git object ID")

    runner_table = _required_table(document, "runner")
    parallel = runner_table.get("parallel")
    if not isinstance(parallel, int) or isinstance(parallel, bool) or parallel < 1:
        raise ConfigurationError("runner.parallel must be a positive integer")
    runner = Runner(
        settings=_required_string(runner_table, "settings", "runner"),
        parallel=parallel,
        default_profile=_required_string(runner_table, "default_profile", "runner"),
        expected_passes=_required_count(runner_table, "expected_passes", "runner"),
        expected_skips=_required_count(runner_table, "expected_skips", "runner"),
        expected_failures=_required_count(runner_table, "expected_failures", "runner"),
    )
    if runner.expected_failures:
        raise ConfigurationError("runner.expected_failures must remain zero; failures are blockers")

    raw_expectations = document.get("expectation")
    if not isinstance(raw_expectations, list) or not raw_expectations:
        raise ConfigurationError("expectation must contain at least one array-table entry")

    expectations: list[Expectation] = []
    seen_labels: set[str] = set()
    for index, raw_expectation in enumerate(raw_expectations, start=1):
        if not isinstance(raw_expectation, dict):
            raise ConfigurationError(f"expectation #{index} must be a table")
        table = cast(dict[str, Any], raw_expectation)
        context = f"expectation #{index}"
        expectation = Expectation(
            label=_required_string(table, "label", context),
            category=_required_string(table, "category", context),
            profile=_required_string(table, "profile", context),
            outcome=_required_string(table, "outcome", context),
            relevance=_required_string(table, "relevance", context),
            reason_code=_optional_string(table, "reason_code", context),
            reason=_optional_string(table, "reason", context),
        )
        if expectation.label in seen_labels:
            raise ConfigurationError(f"duplicate expectation label: {expectation.label}")
        seen_labels.add(expectation.label)
        if expectation.category not in ALLOWED_CATEGORIES:
            raise ConfigurationError(
                f"{expectation.label}: category must be one of {sorted(ALLOWED_CATEGORIES)}"
            )
        if expectation.outcome not in ALLOWED_OUTCOMES:
            raise ConfigurationError(
                f"{expectation.label}: outcome must be one of {sorted(ALLOWED_OUTCOMES)}"
            )
        if expectation.outcome == "skip" and not (expectation.reason_code and expectation.reason):
            raise ConfigurationError(
                f"{expectation.label}: skipped expectations require reason_code and reason"
            )
        expectations.append(expectation)

    default_expectations = [
        expectation for expectation in expectations if expectation.profile == runner.default_profile
    ]
    actual_passes = sum(expectation.outcome == "pass" for expectation in default_expectations)
    actual_skips = sum(expectation.outcome == "skip" for expectation in default_expectations)
    if (actual_passes, actual_skips) != (runner.expected_passes, runner.expected_skips):
        raise ConfigurationError(
            "runner accepted counts do not match the default profile: "
            f"expected {runner.expected_passes} pass/{runner.expected_skips} skip, "
            f"found {actual_passes} pass/{actual_skips} skip"
        )

    return Manifest(source=source, runner=runner, expectations=tuple(expectations))


def _run_git(arguments: Sequence[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def verify_checkout(checkout: Path, source: Source) -> None:
    if not (checkout / ".git").exists():
        raise ConfigurationError(f"Django checkout is not a Git worktree: {checkout}")
    actual_commit = _run_git(["rev-parse", "HEAD"], cwd=checkout)
    if actual_commit != source.commit:
        raise ConfigurationError(
            f"Django checkout HEAD is {actual_commit}; expected {source.commit}"
        )
    if status := _run_git(["status", "--porcelain"], cwd=checkout):
        raise ConfigurationError(f"Django checkout has local changes:\n{status}")
    if not (checkout / "tests/runtests.py").is_file():
        raise ConfigurationError(f"Django test runner not found under {checkout}")


def create_checkout(destination: Path, source: Source) -> None:
    _run_git(["init", "--quiet", str(destination)])
    _run_git(["remote", "add", "origin", source.repository], cwd=destination)
    _run_git(
        ["fetch", "--quiet", "--depth=1", "origin", f"refs/tags/{source.tag}"],
        cwd=destination,
    )
    fetched_commit = _run_git(["rev-parse", "FETCH_HEAD^{commit}"], cwd=destination)
    if fetched_commit != source.commit:
        raise ConfigurationError(
            f"Django tag {source.tag} resolves to {fetched_commit}; expected {source.commit}"
        )
    _run_git(["checkout", "--quiet", "--detach", fetched_commit], cwd=destination)
    verify_checkout(destination, source)


@contextlib.contextmanager
def checkout_context(requested_checkout: Path | None, source: Source) -> Iterator[Path]:
    if requested_checkout is not None:
        checkout = requested_checkout.resolve()
        verify_checkout(checkout, source)
        yield checkout
        return

    with tempfile.TemporaryDirectory(prefix="django-pyturso-upstream-source-") as directory:
        checkout = Path(directory)
        create_checkout(checkout, source)
        yield checkout


def verify_installed_django(expected_version: str) -> None:
    import django

    installed_version = django.get_version()
    if installed_version != expected_version:
        raise ConfigurationError(
            f"installed Django version is {installed_version}; expected {expected_version}"
        )


def verify_label(checkout: Path, label: str) -> None:
    parts = label.split(".")
    if len(parts) < 3:
        raise ConfigurationError(f"invalid upstream test label: {label}")
    module_parts, class_name, method_name = parts[:-2], parts[-2], parts[-1]
    source_file = checkout / "tests" / Path(*module_parts).with_suffix(".py")
    if not source_file.is_file():
        raise ConfigurationError(f"{label}: source module not found at {source_file}")

    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    test_class = classes.get(class_name)
    if test_class is None:
        raise ConfigurationError(f"{label}: test class not found in {source_file}")

    def defines_method(node: ast.ClassDef, visited: frozenset[str]) -> bool:
        if node.name in visited:
            return False
        if any(
            isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and member.name == method_name
            for member in node.body
        ):
            return True
        next_visited = visited | {node.name}
        return any(
            defines_method(base_class, next_visited)
            for base in node.bases
            if isinstance(base, ast.Name) and (base_class := classes.get(base.id)) is not None
        )

    if not defines_method(test_class, frozenset()):
        raise ConfigurationError(f"{label}: test method not found in {source_file}")


def select_expectations(
    manifest: Manifest,
    *,
    profile: str,
    categories: frozenset[str],
) -> tuple[Expectation, ...]:
    selected = tuple(
        expectation
        for expectation in manifest.expectations
        if expectation.profile == profile and (not categories or expectation.category in categories)
    )
    if not selected:
        raise ConfigurationError(f"no expectations selected for profile {profile!r}")
    return selected


def run_lane(
    checkout: Path,
    manifest: Manifest,
    expectations: Sequence[Expectation],
    *,
    probe_skips: bool,
    verbosity: int,
) -> int:
    runnable = [
        expectation for expectation in expectations if expectation.outcome == "pass" or probe_skips
    ]
    if not runnable:
        raise ConfigurationError("the selected lane has no runnable expectations")

    with tempfile.TemporaryDirectory(prefix="django-pyturso-upstream-db-") as database_directory:
        environment = os.environ.copy()
        python_paths = [str(REPOSITORY_ROOT / "tests/upstream"), str(REPOSITORY_ROOT)]
        if existing_pythonpath := environment.get("PYTHONPATH"):
            python_paths.append(existing_pythonpath)
        environment["PYTHONPATH"] = os.pathsep.join(python_paths)
        environment["DJANGO_PYTURSO_UPSTREAM_DB_DIR"] = database_directory
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        command = [
            sys.executable,
            str(checkout / "tests/runtests.py"),
            f"--settings={manifest.runner.settings}",
            f"--parallel={manifest.runner.parallel}",
            f"--verbosity={verbosity}",
            "--noinput",
            *(expectation.label for expectation in runnable),
        ]
        print(f"Command: {shlex.join(command)}", flush=True)
        return subprocess.run(command, env=environment, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--profile", help="expectation profile; defaults to manifest runner value")
    parser.add_argument(
        "--checkout", type=Path, help="existing clean checkout at the pinned commit"
    )
    parser.add_argument(
        "--category",
        action="append",
        choices=sorted(ALLOWED_CATEGORIES),
        default=[],
        help="limit the lane to a category; may be repeated",
    )
    parser.add_argument("--verbosity", type=int, choices=range(4), default=1)
    parser.add_argument("--list", action="store_true", help="verify and list without running tests")
    parser.add_argument(
        "--probe-skips",
        action="store_true",
        help="run explicit skipped labels to check whether their blockers remain",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(arguments.manifest.resolve())
        verify_installed_django(manifest.source.installed_version)
        profile = arguments.profile or manifest.runner.default_profile
        expectations = select_expectations(
            manifest,
            profile=profile,
            categories=frozenset(arguments.category),
        )

        with checkout_context(arguments.checkout, manifest.source) as checkout:
            for expectation in expectations:
                verify_label(checkout, expectation.label)

            print(
                f"Django source: {manifest.source.tag} at {manifest.source.commit}",
                flush=True,
            )
            for expectation in expectations:
                if expectation.outcome == "pass":
                    print(f"PASS [{expectation.category}] {expectation.label}")
                else:
                    print(
                        f"SKIP [{expectation.category}] {expectation.label} "
                        f"({expectation.reason_code}: {expectation.reason})"
                    )

            if arguments.list:
                return 0
            return run_lane(
                checkout,
                manifest,
                expectations,
                probe_skips=arguments.probe_skips,
                verbosity=arguments.verbosity,
            )
    except (ConfigurationError, OSError, subprocess.CalledProcessError) as error:
        print(f"upstream lane configuration error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
