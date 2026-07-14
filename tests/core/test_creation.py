"""Test database lifecycle contract tests."""

from pathlib import Path
from typing import cast

import pytest
from django.db import NotSupportedError

from django_pyturso.base import DatabaseWrapper
from django_pyturso.creation import DatabaseCreation
from tests.support import wrapper_settings

pytestmark = pytest.mark.core


def _creation(*, name: object = ":memory:", test_name: object = None) -> DatabaseCreation:
    wrapper = DatabaseWrapper(wrapper_settings(NAME=name), "probe")
    wrapper.settings_dict["TEST"]["NAME"] = test_name
    return cast(DatabaseCreation, wrapper.creation)


def test_file_test_name_is_a_sibling(tmp_path: Path) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(NAME=tmp_path / "app.db"), "probe")
    creation = cast(DatabaseCreation, wrapper.creation)
    assert creation._get_test_db_name() == str(tmp_path / "test_app.db")


def test_memory_test_database_stays_exact_memory() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "probe")
    creation = cast(DatabaseCreation, wrapper.creation)
    assert creation._get_test_db_name() == ":memory:"
    assert creation.test_db_signature() == (":memory:", "probe")


def test_pathlike_memory_test_database_stays_exact_memory() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(NAME=Path(":memory:")), "probe")
    creation = cast(DatabaseCreation, wrapper.creation)

    assert creation._get_test_db_name() == ":memory:"
    assert creation.test_db_signature() == (Path(":memory:"), "probe")


def test_file_destroy_removes_only_verified_artifacts(tmp_path: Path) -> None:
    database = tmp_path / "test_app.db"
    wal = Path(f"{database}-wal")
    unrelated = Path(f"{database}-other")
    for path in (database, wal, unrelated):
        path.write_text(path.name)
    wrapper = DatabaseWrapper(wrapper_settings(NAME=database), "probe")
    creation = cast(DatabaseCreation, wrapper.creation)
    creation._destroy_test_db(str(database), verbosity=0)
    assert not database.exists()
    assert not wal.exists()
    assert unrelated.exists()


def test_parallel_cloning_and_memory_mirrors_are_rejected() -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "probe")
    creation = cast(DatabaseCreation, wrapper.creation)
    with pytest.raises(NotSupportedError, match="parallel"):
        creation._clone_test_db("1", verbosity=0)
    with pytest.raises(NotSupportedError, match="file-backed"):
        creation.set_as_test_mirror({"NAME": ":memory:"})


def test_creation_name_overrides_and_path_shaped_memory(tmp_path: Path) -> None:
    configured = tmp_path / "configured.db"
    creation = _creation(name=tmp_path / "source.db", test_name=configured)
    assert creation._get_test_db_name() == str(configured)
    assert DatabaseCreation.is_in_memory_db(":memory:")
    assert DatabaseCreation.is_in_memory_db(Path(":memory:"))
    assert not DatabaseCreation.is_in_memory_db(object())


def test_creation_fast_paths_and_file_signature(tmp_path: Path) -> None:
    memory = _creation()
    assert memory._create_test_db(verbosity=0, autoclobber=False) == ":memory:"

    source = tmp_path / "app.db"
    file_creation = _creation(name=source)
    expected = str(tmp_path / "test_app.db")
    assert file_creation._create_test_db(verbosity=0, autoclobber=True) == expected
    assert file_creation._create_test_db(verbosity=0, autoclobber=False, keepdb=True) == expected
    assert file_creation.test_db_signature() == (source, expected)


def test_creation_existing_database_prompt_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_database = tmp_path / "test_app.db"
    test_database.write_text("old")
    creation = _creation(name=tmp_path / "app.db")
    messages: list[str] = []
    monkeypatch.setattr(creation, "log", messages.append)

    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(SystemExit) as cancelled:
        creation._create_test_db(verbosity=0, autoclobber=False)
    assert cancelled.value.code == 1
    assert messages == ["Tests cancelled."]

    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert creation._create_test_db(verbosity=0, autoclobber=False) == str(test_database)
    assert not test_database.exists()


def test_creation_remove_failure_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creation = _creation(name=tmp_path / "app.db")
    messages: list[str] = []
    monkeypatch.setattr(creation, "log", messages.append)

    def fail(path: Path) -> None:
        raise OSError("read only")

    monkeypatch.setattr(creation, "_remove_database_artifacts", fail)
    with pytest.raises(SystemExit) as failed:
        creation._create_test_db(verbosity=0, autoclobber=True)
    assert failed.value.code == 2
    assert messages == ["Unable to remove the old test database: read only"]


def test_creation_clone_destroy_and_mirror_branches(tmp_path: Path) -> None:
    memory = _creation()
    with pytest.raises(NotSupportedError, match="parallel"):
        memory.get_test_db_clone_settings("1")
    memory._destroy_test_db(":memory:", verbosity=0)
    memory._destroy_test_db("", verbosity=0)

    source = tmp_path / "primary.db"
    mirror = _creation(name=tmp_path / "mirror.db")
    mirror.set_as_test_mirror({"NAME": source})
    assert mirror.connection.settings_dict["NAME"] == source


def test_remove_database_artifacts_skips_absent_sidecars(tmp_path: Path) -> None:
    database = tmp_path / "database.db"
    database.write_text("content")
    DatabaseCreation._remove_database_artifacts(database)
    assert not database.exists()
    assert not Path(f"{database}-wal").exists()
