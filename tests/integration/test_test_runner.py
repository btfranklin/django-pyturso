"""Subprocess coverage for Django's own test-runner lifecycle."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANAGE = ROOT / "tests" / "project" / "manage.py"


def run_manage(
    *arguments: str, settings: str, database_directory: Path
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": settings,
        "DJANGO_PYTURSO_TEST_DB": str(database_directory),
    }
    return subprocess.run(
        [sys.executable, str(MANAGE), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.integration
def test_memory_live_server_fails_before_thread_sharing(tmp_path: Path) -> None:
    result = run_manage(
        "test",
        "tests.project.live_server_case",
        "--verbosity=0",
        settings="tests.settings.turso_memory",
        database_directory=tmp_path,
    )
    assert result.returncode != 0
    assert "cannot be shared across threads" in result.stderr
    assert "file-backed test database" in result.stderr


@pytest.mark.integration
def test_file_live_server_uses_separate_local_connections(tmp_path: Path) -> None:
    result = run_manage(
        "test",
        "tests.project.live_server_case",
        "--verbosity=0",
        settings="tests.settings.turso_file",
        database_directory=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.integration
def test_parallel_runner_rejects_database_cloning(tmp_path: Path) -> None:
    result = run_manage(
        "test",
        "tests.project",
        "--parallel=2",
        "--verbosity=0",
        settings="tests.settings.turso_file",
        database_directory=tmp_path,
    )
    assert result.returncode != 0
    assert "doesn't support parallel test database cloning" in result.stderr


@pytest.mark.integration
def test_file_keepdb_reuses_database_and_file_mirror(tmp_path: Path) -> None:
    for _ in range(2):
        keepdb = run_manage(
            "test",
            "tests.project.tests",
            "--keepdb",
            "--verbosity=0",
            settings="tests.settings.turso_file",
            database_directory=tmp_path,
        )
        assert keepdb.returncode == 0, keepdb.stdout + keepdb.stderr
    assert (tmp_path / "test_django-pyturso-tests.db").exists()

    mirror = run_manage(
        "test",
        "tests.project.mirror_case",
        "--noinput",
        "--verbosity=0",
        settings="tests.settings.turso_file_mirror",
        database_directory=tmp_path,
    )
    assert mirror.returncode == 0, mirror.stdout + mirror.stderr


@pytest.mark.integration
def test_memory_mirror_is_rejected_during_setup(tmp_path: Path) -> None:
    result = run_manage(
        "test",
        "tests.project.mirror_case",
        "--verbosity=0",
        settings="tests.settings.turso_memory_mirror",
        database_directory=tmp_path,
    )
    assert result.returncode != 0
    assert "test mirrors require a file-backed primary" in result.stderr


@pytest.mark.integration
@pytest.mark.parametrize(
    "settings",
    ["tests.settings.turso_memory", "tests.settings.turso_file"],
)
def test_fixtures_serialized_rollback_and_management_commands(
    tmp_path: Path, settings: str
) -> None:
    for arguments in (
        ("check", "--database", "default", "--verbosity=0"),
        ("migrate", "--plan", "--verbosity=0"),
        ("showmigrations", "--plan", "--verbosity=0"),
        ("test", "tests.project.serialized_case", "--verbosity=0"),
    ):
        result = run_manage(
            *arguments,
            settings=settings,
            database_directory=tmp_path,
        )
        assert result.returncode == 0, result.stdout + result.stderr
