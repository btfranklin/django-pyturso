"""Check the typed row boundary against custom driver row factories."""

import pytest
import turso
from pytest_django.plugin import DjangoDbBlocker

from django_pyturso.base import DatabaseWrapper
from tests.support import wrapper_settings

pytestmark = pytest.mark.core


def _text_row(cursor: turso.Cursor, row: turso.Row) -> str:
    return "custom row"


@pytest.mark.parametrize("method", ["fetchone", "fetchmany", "fetchall", "next"])
def test_fetch_rejects_non_tuple_driver_rows(
    method: str, django_db_blocker: DjangoDbBlocker
) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "row-types")
    with django_db_blocker.unblock():
        wrapper.ensure_connection()
        try:
            cursor = wrapper.create_cursor()
            cursor.row_factory = _text_row
            cursor.execute("SELECT 1")
            with pytest.raises(TypeError, match="tuple rows"):
                if method == "fetchone":
                    cursor.fetchone()
                elif method == "fetchmany":
                    cursor.fetchmany()
                elif method == "fetchall":
                    cursor.fetchall()
                else:
                    next(cursor)
            cursor.close()
        finally:
            wrapper._force_close()


def test_returning_rejects_non_tuple_driver_rows(django_db_blocker: DjangoDbBlocker) -> None:
    wrapper = DatabaseWrapper(wrapper_settings(), "returning-row-types")
    with django_db_blocker.unblock():
        wrapper.ensure_connection()
        try:
            cursor = wrapper.create_cursor()
            cursor.execute("CREATE TABLE t(id INTEGER PRIMARY KEY)")
            cursor.row_factory = _text_row
            with pytest.raises(TypeError, match="tuple rows"):
                cursor.execute("INSERT INTO t VALUES (1) RETURNING id")
            cursor.close()
        finally:
            wrapper._force_close()
