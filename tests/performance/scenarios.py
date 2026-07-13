"""Deterministic datasets and normalized performance workloads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from django.core.management.color import no_style
from django.db import models, transaction
from django.db.migrations.operations import AddField, CreateModel
from django.db.migrations.state import ProjectState

from django_pyturso.base import DatabaseWrapper
from django_pyturso.creation import DatabaseCreation

ENTRY_COUNT = 5_000
ACTIVE_PAGE_SIZE = 500
INSERT_COUNT = 1_000
RECORD_COUNT = 2_000
AUTHOR_COUNT = 50
INTROSPECTION_TABLE_COUNT = 40


class PerformanceEntry(models.Model):
    title = models.CharField(max_length=64)
    active = models.BooleanField()

    class Meta:
        app_label = "pyturso_performance"
        db_table = "performance_entry"
        managed = False


class PerformanceCrud(models.Model):
    payload = models.CharField(max_length=64)

    class Meta:
        app_label = "pyturso_performance"
        db_table = "performance_crud"
        managed = False


class PerformanceAuthor(models.Model):
    name = models.CharField(max_length=64)

    class Meta:
        app_label = "pyturso_performance"
        db_table = "performance_author"
        managed = False


class PerformanceRecord(models.Model):
    author = models.ForeignKey(PerformanceAuthor, models.DO_NOTHING)
    score = models.IntegerField(db_index=True)
    note = models.CharField(max_length=64)
    payload = models.JSONField()

    class Meta:
        app_label = "pyturso_performance"
        db_table = "performance_record"
        managed = False


ENTRY_ROWS = tuple(
    (index, f"entry-{index:05d}", index % 2 == 0)
    for index in range(1, ENTRY_COUNT + 1)
)
INSERT_ROWS = tuple(
    (index, f"payload-{index:04d}") for index in range(1, INSERT_COUNT + 1)
)
AUTHOR_ROWS = tuple((index, f"author-{index:03d}") for index in range(1, AUTHOR_COUNT + 1))
RECORD_ROWS = tuple(
    (
        index,
        (index % AUTHOR_COUNT) + 1,
        index % 100,
        f"note-{index % 17:02d}",
        json.dumps(
            {"enabled": index % 3 == 0, "group": index % 10},
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    for index in range(1, RECORD_COUNT + 1)
)


def seed_database(wrapper: DatabaseWrapper) -> None:
    with wrapper.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE performance_entry ("
            "id INTEGER PRIMARY KEY, title TEXT NOT NULL, active BOOL NOT NULL)"
        )
        cursor.executemany(
            "INSERT INTO performance_entry(id, title, active) VALUES (%s, %s, %s)",
            ENTRY_ROWS,
        )
        cursor.execute(
            "CREATE TABLE performance_insert (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        cursor.execute(
            "CREATE TABLE performance_crud (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        cursor.execute(
            "CREATE TABLE performance_author (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        cursor.executemany(
            "INSERT INTO performance_author(id, name) VALUES (%s, %s)", AUTHOR_ROWS
        )
        cursor.execute(
            "CREATE TABLE performance_record ("
            "id INTEGER PRIMARY KEY, author_id INTEGER NOT NULL "
            "REFERENCES performance_author(id), score INTEGER NOT NULL, "
            "note TEXT NOT NULL, payload TEXT NOT NULL "
            "CHECK (JSON_VALID(payload) OR payload IS NULL))"
        )
        cursor.execute("CREATE INDEX performance_record_score ON performance_record(score)")
        cursor.executemany(
            "INSERT INTO performance_record(id, author_id, score, note, payload) "
            "VALUES (%s, %s, %s, %s, %s)",
            RECORD_ROWS,
        )
        cursor.execute(
            "CREATE TABLE performance_transaction (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        for index in range(1, INTROSPECTION_TABLE_COUNT + 1):
            cursor.execute(
                f'CREATE TABLE "performance_introspection_{index:02d}" '
                "(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
            )


def _payload_hash(rows: Sequence[Sequence[Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def active_entry_page(alias: str) -> dict[str, Any]:
    rows = list(
        PerformanceEntry._default_manager.using(alias)
        .filter(active=True)
        .order_by("id")
        .values_list("id", "title")[:ACTIVE_PAGE_SIZE]
    )
    return {
        "count": len(rows),
        "first": list(rows[0]),
        "last": list(rows[-1]),
        "id_sum": sum(row[0] for row in rows),
        "payload_sha256": _payload_hash(rows),
    }


def clear_insert_table(wrapper: DatabaseWrapper) -> None:
    with wrapper.cursor() as cursor:
        cursor.execute("DELETE FROM performance_insert")


def insert_batch(wrapper: DatabaseWrapper) -> int:
    with wrapper.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO performance_insert(id, payload) VALUES (%s, %s)", INSERT_ROWS
        )
        return int(cursor.rowcount)


def inserted_batch_summary(wrapper: DatabaseWrapper) -> dict[str, Any]:
    with wrapper.cursor() as cursor:
        cursor.execute("SELECT id, payload FROM performance_insert ORDER BY id")
        rows = cursor.fetchall()
    return {
        "count": len(rows),
        "first": list(rows[0]),
        "last": list(rows[-1]),
        "id_sum": sum(row[0] for row in rows),
        "payload_sha256": _payload_hash(rows),
    }


def single_row_crud(alias: str) -> dict[str, Any]:
    manager = PerformanceCrud._default_manager.using(alias)
    manager.all().delete()
    created = manager.create(id=1, payload="created")
    read_payload = manager.values_list("payload", flat=True).get(pk=created.pk)
    updated = manager.filter(pk=created.pk).update(payload="updated")
    updated_payload = manager.values_list("payload", flat=True).get(pk=created.pk)
    deleted, _ = manager.filter(pk=created.pk).delete()
    return {
        "created_id": created.pk,
        "read_payload": read_payload,
        "updated": updated,
        "updated_payload": updated_payload,
        "deleted": deleted,
        "remaining": manager.count(),
    }


def update_batch(wrapper: DatabaseWrapper) -> int:
    updates = tuple(
        (f"updated-{index:04d}", index) for index in range(1, INSERT_COUNT + 1)
    )
    with wrapper.cursor() as cursor:
        cursor.executemany(
            "UPDATE performance_insert SET payload = %s WHERE id = %s", updates
        )
        return int(cursor.rowcount)


def query_family_summary(alias: str) -> dict[str, Any]:
    manager = PerformanceRecord._default_manager.using(alias)
    indexed = list(
        manager.filter(score=42).order_by("id").values_list("id", flat=True)
    )
    unindexed = list(
        manager.filter(note="note-03").order_by("id").values_list("id", flat=True)
    )
    ordered = list(
        manager.order_by("-score", "id").values_list("id", "score")[:50]
    )
    aggregate = manager.aggregate(row_count=models.Count("id"), score_sum=models.Sum("score"))
    related = [
        (record.pk, record.author.name)
        for record in manager.select_related("author").order_by("id")[:100]
    ]
    json_rows = list(
        manager.filter(payload__group=3).order_by("id").values_list("id", flat=True)
    )
    return {
        "indexed_count": len(indexed),
        "indexed_sha256": _payload_hash([indexed]),
        "unindexed_count": len(unindexed),
        "unindexed_sha256": _payload_hash([unindexed]),
        "ordered_first": list(ordered[0]),
        "ordered_last": list(ordered[-1]),
        "ordered_sha256": _payload_hash(ordered),
        "aggregate": aggregate,
        "related_first": list(related[0]),
        "related_last": list(related[-1]),
        "related_sha256": _payload_hash(related),
        "json_count": len(json_rows),
        "json_sha256": _payload_hash([json_rows]),
    }


def transaction_savepoint_summary(wrapper: DatabaseWrapper) -> dict[str, Any]:
    with wrapper.cursor() as cursor:
        cursor.execute("DELETE FROM performance_transaction")
    with transaction.atomic(using=wrapper.alias):
        with wrapper.cursor() as cursor:
            cursor.execute(
                "INSERT INTO performance_transaction(id, payload) VALUES (%s, %s)",
                (1, "outer"),
            )
        try:
            with transaction.atomic(using=wrapper.alias):
                with wrapper.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO performance_transaction(id, payload) VALUES (%s, %s)",
                        (2, "rolled-back"),
                    )
                raise RuntimeError("savepoint rollback")
        except RuntimeError:
            pass
        with wrapper.cursor() as cursor:
            cursor.execute(
                "INSERT INTO performance_transaction(id, payload) VALUES (%s, %s)",
                (3, "committed"),
            )
    with wrapper.cursor() as cursor:
        cursor.execute("SELECT id, payload FROM performance_transaction ORDER BY id")
        rows = cursor.fetchall()
    return {"count": len(rows), "rows": [list(row) for row in rows]}


def many_table_introspection_summary(wrapper: DatabaseWrapper) -> dict[str, Any]:
    prefix = "performance_introspection_"
    with wrapper.cursor() as cursor:
        tables = sorted(
            name for name in wrapper.introspection.table_names(cursor) if name.startswith(prefix)
        )
        columns = [
            [field.name for field in wrapper.introspection.get_table_description(cursor, table)]
            for table in tables
        ]
    return {
        "count": len(tables),
        "first": tables[0],
        "last": tables[-1],
        "columns_sha256": _payload_hash(columns),
        "tables_sha256": _payload_hash([tables]),
    }


def connection_lifecycle_summary(database: Path) -> dict[str, Any]:
    settings = {
        "ENGINE": "django_pyturso",
        "NAME": database,
        "OPTIONS": {},
        "HOST": "",
        "PORT": "",
        "USER": "",
        "PASSWORD": "",
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "TIME_ZONE": None,
        "TEST": {"NAME": None},
    }
    versions: list[list[int]] = []
    values: list[int] = []
    for cycle in range(2):
        wrapper = DatabaseWrapper(settings, f"performance_connection_{cycle}")
        try:
            for value in range(cycle * 2, cycle * 2 + 2):
                with wrapper.cursor() as cursor:
                    cursor.execute("SELECT %s", (value,))
                    values.append(int(cursor.fetchone()[0]))
                versions.append(list(wrapper.get_database_version()))
        finally:
            wrapper.close()
    return {
        "close_count": 2,
        "file_exists": database.exists(),
        "open_count": 2,
        "persistent_queries_per_open": 2,
        "values": values,
        "versions": versions,
    }


def database_lifecycle_summary(source_database: Path) -> dict[str, Any]:
    test_database = source_database.with_name("test_performance_lifecycle.db")
    settings: dict[str, Any] = {
        "ENGINE": "django_pyturso",
        "NAME": source_database,
        "OPTIONS": {},
        "HOST": "",
        "PORT": "",
        "USER": "",
        "PASSWORD": "",
        "AUTOCOMMIT": True,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "TIME_ZONE": None,
        "TEST": {"NAME": test_database},
    }
    creator = DatabaseWrapper(settings, "performance_test_creation")
    creation = cast(DatabaseCreation, creator.creation)
    created_name = creation._create_test_db(
        verbosity=0, autoclobber=True, keepdb=False
    )
    runtime_settings = dict(settings)
    runtime_settings["NAME"] = Path(created_name)
    runtime = DatabaseWrapper(runtime_settings, "performance_test_runtime")
    rows_before_flush = 0
    rows_after_flush = 0
    try:
        with runtime.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE performance_test_lifecycle "
                "(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
            )
            cursor.execute(
                "INSERT INTO performance_test_lifecycle(id, payload) VALUES (%s, %s)",
                (1, "migrated"),
            )
            cursor.execute("SELECT COUNT(*) FROM performance_test_lifecycle")
            rows_before_flush = int(cursor.fetchone()[0])
            statements = runtime.ops.sql_flush(
                no_style(), ["performance_test_lifecycle"], reset_sequences=False
            )
            for statement in statements:
                cursor.execute(statement)
            cursor.execute("SELECT COUNT(*) FROM performance_test_lifecycle")
            rows_after_flush = int(cursor.fetchone()[0])
    finally:
        cast(DatabaseCreation, runtime.creation)._destroy_test_db(created_name, verbosity=0)
    return {
        "created_name": Path(created_name).name,
        "database_destroyed": not test_database.exists(),
        "phases": ["create", "migrate", "flush", "destroy"],
        "rows_after_flush": rows_after_flush,
        "rows_before_flush": rows_before_flush,
        "wal_destroyed": not Path(f"{test_database}-wal").exists(),
    }


def create_initial_migration(wrapper: DatabaseWrapper) -> ProjectState:
    state = ProjectState()
    operation = CreateModel(
        name="PerformanceMigration",
        fields=[
            ("id", models.BigAutoField(primary_key=True)),
            ("payload", models.CharField(max_length=64)),
        ],
        options={"db_table": "performance_migration"},
    )
    next_state = state.clone()
    operation.state_forwards("pyturso_performance", next_state)
    with wrapper.schema_editor() as editor:
        operation.database_forwards("pyturso_performance", editor, state, next_state)
    return next_state


def populate_migration_table(wrapper: DatabaseWrapper, state: ProjectState) -> None:
    model = state.apps.get_model("pyturso_performance", "PerformanceMigration")
    model._default_manager.using(wrapper.alias).bulk_create(
        [model(id=index, payload=f"migration-{index:04d}") for index in range(1, 501)]
    )


def remake_populated_migration(wrapper: DatabaseWrapper, state: ProjectState) -> ProjectState:
    operation = AddField(
        model_name="performancemigration",
        name="status",
        field=models.CharField(default="ready", max_length=16),
    )
    next_state = state.clone()
    operation.state_forwards("pyturso_performance", next_state)
    with wrapper.schema_editor() as editor:
        operation.database_forwards("pyturso_performance", editor, state, next_state)
    return next_state


def migration_summary(wrapper: DatabaseWrapper, state: ProjectState) -> dict[str, Any]:
    model = state.apps.get_model("pyturso_performance", "PerformanceMigration")
    rows = list(
        model._default_manager.using(wrapper.alias).order_by("id").values_list("id", "payload")
    )
    with wrapper.cursor() as cursor:
        columns = [
            field.name
            for field in wrapper.introspection.get_table_description(
                cursor, model._meta.db_table
            )
        ]
    result: dict[str, Any] = {
        "columns": columns,
        "count": len(rows),
        "payload_sha256": _payload_hash(rows),
    }
    if "status" in columns:
        result["ready_count"] = model._default_manager.using(wrapper.alias).filter(
            status="ready"
        ).count()
    return result


def drop_migration_table(wrapper: DatabaseWrapper, state: ProjectState) -> None:
    model = state.apps.get_model("pyturso_performance", "PerformanceMigration")
    with wrapper.schema_editor() as editor:
        editor.delete_model(model)
