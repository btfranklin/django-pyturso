"""Test database lifecycle contract tests."""

from pathlib import Path
from typing import cast

import pytest
from django.db import NotSupportedError

from django_pyturso.base import DatabaseWrapper
from django_pyturso.creation import DatabaseCreation
from tests.core.test_connection import wrapper_settings

pytestmark = pytest.mark.core


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
