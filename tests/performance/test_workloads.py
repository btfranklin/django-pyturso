"""Correctness-first benchmarks for representative backend workloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from django.db.migrations.state import ProjectState
from django.test.utils import CaptureQueriesContext

from .conftest import PerformanceDatabase
from .scenarios import (
    active_entry_page,
    clear_insert_table,
    connection_lifecycle_summary,
    create_initial_migration,
    database_lifecycle_summary,
    drop_migration_table,
    insert_batch,
    inserted_batch_summary,
    many_table_introspection_summary,
    migration_summary,
    populate_migration_table,
    query_family_summary,
    remake_populated_migration,
    single_row_crud,
    transaction_savepoint_summary,
    update_batch,
)

pytestmark = pytest.mark.performance
SNAPSHOTS = Path(__file__).parents[1] / "snapshots" / "performance"


def load_json(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((SNAPSHOTS / name).read_text(encoding="utf-8")),
    )


def assert_case(
    case_id: str,
    result: dict[str, Any],
    *,
    observed_queries: int | None = None,
    observed_operations: int | None = None,
) -> None:
    snapshots = load_json("correctness.json")["cases"]
    query_caps = load_json("query-caps.json")
    assert result == snapshots[case_id]
    cap = query_caps[case_id]
    if observed_queries is not None:
        assert observed_queries <= cap["max_queries"]
    if observed_operations is not None:
        assert observed_operations <= cap["max_operations"]


def assert_read_correctness(database: PerformanceDatabase) -> tuple[dict[str, Any], int]:
    with CaptureQueriesContext(database.wrapper) as queries:
        result = active_entry_page(database.alias)
    assert_case("orm_active_page_500", result, observed_queries=len(queries))
    return result, len(queries)


def assert_insert_correctness(database: PerformanceDatabase) -> tuple[dict[str, Any], int]:
    clear_insert_table(database.wrapper)
    with CaptureQueriesContext(database.wrapper) as queries:
        inserted = insert_batch(database.wrapper)
    assert inserted == 1_000
    result = inserted_batch_summary(database.wrapper)
    assert_case("cursor_insert_1000", result, observed_queries=len(queries))
    return result, len(queries)


def test_performance_correctness_and_query_caps(
    performance_database: PerformanceDatabase,
) -> None:
    assert_read_correctness(performance_database)
    assert_insert_correctness(performance_database)


def test_extended_correctness_corpus_and_query_caps(
    performance_database: PerformanceDatabase,
) -> None:
    database = performance_database

    with CaptureQueriesContext(database.wrapper) as queries:
        crud = single_row_crud(database.alias)
    assert_case("orm_single_row_crud", crud, observed_queries=len(queries))

    clear_insert_table(database.wrapper)
    insert_batch(database.wrapper)
    with CaptureQueriesContext(database.wrapper) as queries:
        updated = update_batch(database.wrapper)
    assert updated == 1_000
    batch_update = inserted_batch_summary(database.wrapper)
    assert_case("cursor_update_1000", batch_update, observed_queries=len(queries))

    with CaptureQueriesContext(database.wrapper) as queries:
        query_families = query_family_summary(database.alias)
    assert_case("orm_query_families", query_families, observed_queries=len(queries))

    with CaptureQueriesContext(database.wrapper) as queries:
        transaction_result = transaction_savepoint_summary(database.wrapper)
    assert_case(
        "transaction_atomic_savepoint",
        transaction_result,
        observed_queries=len(queries),
    )

    with CaptureQueriesContext(database.wrapper) as queries:
        introspection = many_table_introspection_summary(database.wrapper)
    assert_case("introspection_40_tables", introspection, observed_queries=len(queries))

    connection_lifecycle = connection_lifecycle_summary(
        database.path.with_name("connection-lifecycle.db")
    )
    assert_case(
        "connection_lifecycle",
        connection_lifecycle,
        observed_operations=8,
    )

    test_lifecycle = database_lifecycle_summary(
        database.path.with_name("lifecycle-source.db")
    )
    assert_case("test_database_lifecycle", test_lifecycle, observed_operations=7)


def test_initial_and_populated_remake_migrations(
    performance_database: PerformanceDatabase,
) -> None:
    database = performance_database
    state: ProjectState | None = None
    try:
        with CaptureQueriesContext(database.wrapper) as queries:
            state = create_initial_migration(database.wrapper)
        initial = migration_summary(database.wrapper, state)
        assert_case("migration_initial", initial, observed_queries=len(queries))

        populate_migration_table(database.wrapper, state)
        with CaptureQueriesContext(database.wrapper) as queries:
            state = remake_populated_migration(database.wrapper, state)
        populated = migration_summary(database.wrapper, state)
        assert_case("migration_populated_remake", populated, observed_queries=len(queries))
    finally:
        if state is not None:
            drop_migration_table(database.wrapper, state)


def test_benchmark_orm_active_page_500(
    benchmark: Any, performance_database: PerformanceDatabase
) -> None:
    expected, observed_queries = assert_read_correctness(performance_database)
    benchmark.group = "django-pyturso-read"
    benchmark.extra_info["case_id"] = "orm_active_page_500"
    benchmark.extra_info["max_queries"] = 1
    benchmark.extra_info["observed_queries"] = observed_queries
    benchmark.extra_info["correctness_status"] = "pass"
    benchmark.extra_info["observed_count"] = expected["count"]
    benchmark.extra_info["correctness_sha256"] = expected["payload_sha256"]

    result = benchmark.pedantic(
        active_entry_page,
        args=(performance_database.alias,),
        rounds=12,
        warmup_rounds=3,
        iterations=1,
    )

    assert result == expected


def test_benchmark_cursor_insert_1000(
    benchmark: Any, performance_database: PerformanceDatabase
) -> None:
    expected, observed_queries = assert_insert_correctness(performance_database)
    benchmark.group = "django-pyturso-write"
    benchmark.extra_info["case_id"] = "cursor_insert_1000"
    benchmark.extra_info["max_queries"] = 1
    benchmark.extra_info["observed_queries"] = observed_queries
    benchmark.extra_info["correctness_status"] = "pass"
    benchmark.extra_info["observed_count"] = expected["count"]
    benchmark.extra_info["correctness_sha256"] = expected["payload_sha256"]

    def setup() -> None:
        clear_insert_table(performance_database.wrapper)

    inserted = benchmark.pedantic(
        insert_batch,
        args=(performance_database.wrapper,),
        setup=setup,
        rounds=8,
        warmup_rounds=2,
        iterations=1,
    )

    assert inserted == expected["count"]
