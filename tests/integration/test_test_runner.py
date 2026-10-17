"""Subprocess tests for Django's own test-runner lifecycle."""

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

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
def test_manage_uses_project_package_when_root_is_on_pythonpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]))
    result = run_manage(
        "check",
        "--database",
        "default",
        "--verbosity=0",
        settings="tests.settings.turso_memory",
        database_directory=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.parametrize("file_database", [False, True], ids=["memory", "file"])
@pytest.mark.parametrize("keepdb", [False, True])
def test_creation_switches_from_an_open_memory_database(
    tmp_path: Path, file_database: bool, keepdb: bool
) -> None:
    script = dedent(
        f"""
        import os
        from pathlib import Path
        import turso
        from django.db import connection
        from tests.project.models import Entry

        test_name = (
            str(Path(os.environ["DJANGO_PYTURSO_TEST_DB"]) / "test-switch.db")
            if {file_database!r} else ":memory:"
        )
        connection.settings_dict["TEST"]["NAME"] = test_name
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE before_test_setup (value INTEGER)")
        original = connection.connection
        name = connection.creation.create_test_db(
            verbosity=0, autoclobber=True, keepdb={keepdb!r}
        )
        assert name == test_name
        assert connection.connection is not original
        assert "before_test_setup" not in connection.introspection.table_names()
        Entry.objects.create(title="test database")
        if {file_database!r}:
            assert Path(test_name).is_file()
            other = turso.connect(test_name, isolation_level=None)
            try:
                assert other.execute(
                    "SELECT title FROM pyturso_test_project_entry"
                ).fetchall() == [("test database",)]
                assert other.execute(
                    "SELECT COUNT(*) FROM django_migrations"
                ).fetchone()[0] > 0
            finally:
                other.close()
        connection.creation.destroy_test_db(":memory:", verbosity=0, keepdb={keepdb!r})
        if {file_database!r} and {keepdb!r}:
            with connection.cursor() as cursor:
                cursor.execute("CREATE TABLE before_test_setup (value INTEGER)")
            connection.creation.create_test_db(verbosity=0, autoclobber=True, keepdb=True)
            assert "before_test_setup" not in connection.introspection.table_names()
            assert list(Entry.objects.values_list("title", flat=True)) == ["test database"]
            connection.creation.destroy_test_db(":memory:", verbosity=0, keepdb=False)
        """
    )
    result = run_manage(
        "shell",
        "--command",
        script,
        settings="tests.settings.turso_memory",
        database_directory=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.parametrize("keepdb", [False, True])
def test_destruction_restores_the_original_file_database(
    tmp_path: Path, keepdb: bool
) -> None:
    script = dedent(
        f"""
        from django.db import connection
        from tests.project.models import Entry

        original_name = str(connection.settings_dict["NAME"])
        connection.settings_dict["TEST"]["NAME"] = ":memory:"
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE source_rows(value INTEGER)")
            cursor.execute("INSERT INTO source_rows VALUES (7)")
        connection.creation.create_test_db(verbosity=0, autoclobber=True)
        assert "source_rows" not in connection.introspection.table_names()
        Entry.objects.create(title="test database")
        connection.creation.destroy_test_db(
            original_name, verbosity=0, keepdb={keepdb!r}
        )
        assert connection.connection is None
        assert connection.settings_dict["NAME"] == original_name
        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM source_rows")
            assert cursor.fetchall() == [(7,)]
        assert Entry._meta.db_table not in connection.introspection.table_names()
        connection.close()
        """
    )
    result = run_manage(
        "shell",
        "--command",
        script,
        settings="tests.settings.turso_file",
        database_directory=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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
