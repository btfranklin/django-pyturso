"""Manual foreign-key checking and enforcement-state tests."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import IntegrityError, connection


def _foreign_key_state() -> int:
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.core
def test_constraint_toggles_verify_state_and_preserve_existing_disabled_state(
    django_db_blocker: Any,
) -> None:
    with django_db_blocker.unblock():
        assert _foreign_key_state() == 1
        try:
            assert connection.disable_constraint_checking()
            assert _foreign_key_state() == 0
            with connection.constraint_checks_disabled():
                assert _foreign_key_state() == 0
            assert _foreign_key_state() == 0
            assert not connection.disable_constraint_checking()
            assert _foreign_key_state() == 0
        finally:
            connection.enable_constraint_checking()
        assert _foreign_key_state() == 1

        with connection.constraint_checks_disabled():
            assert _foreign_key_state() == 0
        assert _foreign_key_state() == 1


@pytest.mark.core
def test_manual_checker_reports_rowid_identity_and_respects_table_scope(
    django_db_blocker: Any,
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute("CREATE TABLE fk_rowid_parent (id integer PRIMARY KEY)")
        cursor.execute(
            """
            CREATE TABLE fk_rowid_child (
                parent_id integer REFERENCES fk_rowid_parent(id),
                note text
            )
            """
        )
        try:
            with connection.constraint_checks_disabled():
                cursor.execute(
                    "INSERT INTO fk_rowid_child (parent_id, note) VALUES (%s, %s)",
                    (999, "broken"),
                )

            connection.check_constraints(table_names=["fk_rowid_parent"])
            with pytest.raises(IntegrityError) as raised:
                connection.check_constraints(table_names=["fk_rowid_child"])
            message = str(raised.value)
            assert "fk_rowid_child" in message
            assert "rowid=1" in message
            assert "parent_id" in message
            assert "999" in message
            assert "fk_rowid_parent" in message
            assert "id" in message
        finally:
            cursor.execute("DROP TABLE IF EXISTS fk_rowid_child")
            cursor.execute("DROP TABLE IF EXISTS fk_rowid_parent")


@pytest.mark.core
def test_composite_checker_uses_match_simple_null_semantics(
    django_db_blocker: Any,
) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE fk_composite_parent (
                key_a integer,
                key_b text,
                PRIMARY KEY (key_a, key_b)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE fk_composite_child (
                id integer PRIMARY KEY,
                parent_a integer,
                parent_b text,
                FOREIGN KEY (parent_a, parent_b)
                    REFERENCES fk_composite_parent (key_a, key_b)
            )
            """
        )
        try:
            cursor.execute("INSERT INTO fk_composite_parent VALUES (%s, %s)", (1, "one"))
            cursor.executemany(
                "INSERT INTO fk_composite_child VALUES (%s, %s, %s)",
                [
                    (1, 1, "one"),
                    (2, None, None),
                    (3, 1, None),
                    (4, None, "one"),
                ],
            )
            connection.check_constraints(table_names=["fk_composite_child"])

            with connection.constraint_checks_disabled():
                cursor.execute(
                    "INSERT INTO fk_composite_child VALUES (%s, %s, %s)",
                    (5, 8, "missing"),
                )
            with pytest.raises(IntegrityError) as raised:
                connection.check_constraints(table_names=["fk_composite_child"])
            message = str(raised.value)
            assert "id=5" in message
            assert "('parent_a', 'parent_b')" in message
            assert "(8, 'missing')" in message
            assert "('key_a', 'key_b')" in message
        finally:
            cursor.execute("DROP TABLE IF EXISTS fk_composite_child")
            cursor.execute("DROP TABLE IF EXISTS fk_composite_parent")


@pytest.mark.core
def test_omitted_targets_and_quoted_unicode_identifiers(django_db_blocker: Any) -> None:
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE "cible étrange" (
                "clé un" integer,
                "clé deux" text,
                PRIMARY KEY ("clé un", "clé deux")
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE "enfant étrange" (
                "identité" text PRIMARY KEY,
                "référence un" integer,
                "référence deux" text,
                FOREIGN KEY ("référence un", "référence deux")
                    REFERENCES "cible étrange"
            )
            """
        )
        try:
            cursor.execute('INSERT INTO "cible étrange" VALUES (%s, %s)', (7, "sept"))
            cursor.execute(
                'INSERT INTO "enfant étrange" VALUES (%s, %s, %s)',
                ("validé", 7, "sept"),
            )
            connection.check_constraints(table_names=["enfant étrange"])

            with connection.constraint_checks_disabled():
                cursor.execute(
                    'INSERT INTO "enfant étrange" VALUES (%s, %s, %s)',
                    ("cassé", 9, "absent"),
                )
            with pytest.raises(IntegrityError) as raised:
                connection.check_constraints(table_names=["enfant étrange"])
            message = str(raised.value)
            assert "enfant étrange" in message
            assert "identité='cassé'" in message
            assert "référence un" in message
            assert "référence deux" in message
            assert "cible étrange" in message
            assert "clé un" in message
            assert "clé deux" in message
        finally:
            cursor.execute('DROP TABLE IF EXISTS "enfant étrange"')
            cursor.execute('DROP TABLE IF EXISTS "cible étrange"')
