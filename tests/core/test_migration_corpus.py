"""Generated migration corpus for schema and data preservation."""

from __future__ import annotations

import datetime
import decimal
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.operations import (
    AddConstraint,
    AddField,
    AddIndex,
    AlterField,
    CreateModel,
    RemoveConstraint,
    RenameField,
)
from django.db.migrations.state import ProjectState

APP_LABEL = "migration_corpus"
TABLE_PREFIX = "migration_corpus_"
SNAPSHOT_PATH = (
    Path(__file__).parents[1] / "snapshots" / "schema" / "migration-corpus.json"
)


def _apply_operation(state: ProjectState, operation: Any) -> ProjectState:
    next_state = state.clone()
    operation.state_forwards(APP_LABEL, next_state)
    with connection.schema_editor() as editor:
        operation.database_forwards(APP_LABEL, editor, state, next_state)
    return next_state


def _reverse_operation(
    state: ProjectState, operation: Any, previous_state: ProjectState
) -> ProjectState:
    with connection.schema_editor() as editor:
        operation.database_backwards(APP_LABEL, editor, state, previous_state)
    return previous_state


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _normalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_normalize_value(item) for item in value]
    return value


def _normalized_schema() -> dict[str, Any]:
    result: dict[str, Any] = {}
    with connection.cursor() as cursor:
        table_names = sorted(
            name
            for name in connection.introspection.table_names(cursor)
            if name.startswith(TABLE_PREFIX)
        )
        for table_name in table_names:
            description = connection.introspection.get_table_description(cursor, table_name)
            constraints = connection.introspection.get_constraints(cursor, table_name)
            result[table_name] = {
                "columns": [
                    {
                        "name": field.name,
                        "type": str(field.type_code),
                        "null": field.null_ok,
                        "primary_key": field.pk,
                    }
                    for field in sorted(description, key=lambda item: item.name)
                ],
                "constraints": {
                    name: {
                        key: _normalize_value(details.get(key))
                        for key in (
                            "columns",
                            "primary_key",
                            "unique",
                            "foreign_key",
                            "check",
                            "index",
                            "orders",
                            "type",
                        )
                        if key in details
                    }
                    for name, details in sorted(constraints.items())
                },
            }
    return result


def _normalized_data(state: ProjectState) -> dict[str, Any]:
    author = state.apps.get_model(APP_LABEL, "Author")
    article = state.apps.get_model(APP_LABEL, "Article")
    return {
        "authors": _normalize_value(list(author.objects.order_by("pk").values())),
        "articles": _normalize_value(list(article.objects.order_by("pk").values())),
    }


def _snapshot_stage(state: ProjectState) -> dict[str, Any]:
    content = {
        "schema": _normalized_schema(),
        "data": _normalized_data(state),
    }
    serialized = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return {"sha256": hashlib.sha256(serialized.encode()).hexdigest(), **content}


def _assert_snapshot_stage(
    stage: str, actual: dict[str, Any], snapshot: dict[str, Any]
) -> None:
    expected = snapshot["stages"][stage]
    assert actual["sha256"] == expected["schema_data_sha256"]
    assert sorted(actual["schema"]) == expected["tables"]
    assert {
        key: len(rows) for key, rows in actual["data"].items()
    } == expected["row_counts"]


def _operations() -> tuple[list[Any], list[Any]]:
    initial = [
        CreateModel(
            name="Author",
            fields=[
                ("id", models.BigAutoField(primary_key=True)),
                ("slug", models.CharField(max_length=40, unique=True)),
                ("display_name", models.CharField(max_length=80)),
                ("joined_on", models.DateField()),
                ("preferences", models.JSONField(null=True)),
            ],
            options={
                "db_table": "migration_corpus_author",
                "indexes": [
                    models.Index(fields=["joined_on"], name="corpus_author_joined_ix")
                ],
            },
        ),
        CreateModel(
            name="Article",
            fields=[
                ("id", models.BigAutoField(primary_key=True)),
                (
                    "author",
                    models.ForeignKey(
                        db_column="author_slug",
                        on_delete=models.CASCADE,
                        to=f"{APP_LABEL}.author",
                        to_field="slug",
                    ),
                ),
                ("title", models.CharField(max_length=60)),
                ("status", models.CharField(default="draft", max_length=12)),
                ("payload", models.JSONField(null=True)),
                ("published_at", models.DateTimeField(null=True)),
                ("reading_time", models.DurationField(null=True)),
                ("publication_time", models.TimeField(null=True)),
            ],
            options={
                "db_table": "migration_corpus_article",
                "constraints": [
                    models.UniqueConstraint(
                        fields=["author", "title"], name="corpus_article_author_title_uq"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(status__in=("draft", "published")),
                        name="corpus_article_status_ck",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["published_at"], name="corpus_article_published_ix"
                    )
                ],
            },
        ),
    ]
    changes = [
        AlterField(
            model_name="author",
            name="slug",
            field=models.CharField(max_length=80, unique=True),
        ),
        AlterField(
            model_name="author",
            name="preferences",
            field=models.JSONField(default=dict),
        ),
        AlterField(
            model_name="article",
            name="title",
            field=models.CharField(max_length=120),
        ),
        RemoveConstraint(
            model_name="article", name="corpus_article_status_ck"
        ),
        RenameField(model_name="article", old_name="status", new_name="lifecycle"),
        AddConstraint(
            model_name="article",
            constraint=models.CheckConstraint(
                condition=models.Q(lifecycle__in=("draft", "published")),
                name="corpus_article_lifecycle_ck",
            ),
        ),
        AddField(
            model_name="article",
            name="score",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        AddConstraint(
            model_name="article",
            constraint=models.CheckConstraint(
                condition=models.Q(score__gte=0), name="corpus_article_score_ck"
            ),
        ),
        AddIndex(
            model_name="article",
            index=models.Index(
                fields=["lifecycle", "title"], name="corpus_article_state_title_ix"
            ),
        ),
    ]
    return initial, changes


@pytest.mark.core
def test_generated_migration_corpus_matches_normalized_digest(
    django_db_blocker: Any,
) -> None:
    snapshot: dict[str, Any] = json.loads(SNAPSHOT_PATH.read_text())
    initial, changes = _operations()
    state = ProjectState()
    history: list[tuple[Any, ProjectState]] = []

    with django_db_blocker.unblock():
        try:
            for operation in initial:
                previous_state = state
                state = _apply_operation(state, operation)
                history.append((operation, previous_state))

            author = state.apps.get_model(APP_LABEL, "Author")
            article = state.apps.get_model(APP_LABEL, "Article")
            author.objects.create(
                slug="ada",
                display_name="Ada Lovelace",
                joined_on=datetime.date(2026, 1, 2),
                preferences={"density": "compact", "topics": ["math", "engines"]},
            )
            article.objects.create(
                author_id="ada",
                title="Analytical Engines",
                status="published",
                payload={"edition": 1, "reviewed": True},
                published_at=datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
                reading_time=datetime.timedelta(minutes=7, seconds=30),
                publication_time=datetime.time(3, 4, 5, 6000),
            )
            initial_stage = _snapshot_stage(state)
            _assert_snapshot_stage("initial", initial_stage, snapshot)

            for operation in changes:
                previous_state = state
                state = _apply_operation(state, operation)
                history.append((operation, previous_state))

            forward_stage = _snapshot_stage(state)
            _assert_snapshot_stage("forward", forward_stage, snapshot)
            article = state.apps.get_model(APP_LABEL, "Article")
            with pytest.raises(IntegrityError), transaction.atomic():
                article.objects.create(
                    author_id="ada",
                    title="Invalid score",
                    lifecycle="draft",
                    score=-1,
                )
            with pytest.raises(IntegrityError), transaction.atomic():
                article.objects.create(
                    author_id="missing",
                    title="Missing author",
                    lifecycle="draft",
                )
            with pytest.raises(IntegrityError), transaction.atomic():
                article.objects.create(
                    author_id="ada",
                    title="Analytical Engines",
                    lifecycle="published",
                )
            with pytest.raises(IntegrityError), transaction.atomic():
                article.objects.create(
                    author_id="ada",
                    title="Invalid lifecycle",
                    lifecycle="retired",
                )

            for operation, previous_state in reversed(history[len(initial) :]):
                state = _reverse_operation(state, operation, previous_state)

            backward_stage = _snapshot_stage(state)
            _assert_snapshot_stage("backward", backward_stage, snapshot)
            assert initial_stage == backward_stage

            for operation, previous_state in reversed(history[: len(initial)]):
                state = _reverse_operation(state, operation, previous_state)

            remaining = [
                name
                for name in connection.introspection.table_names()
                if name.startswith(TABLE_PREFIX) or name.startswith("new__migration_corpus_")
            ]
            assert remaining == []
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS migration_corpus_article")
                cursor.execute("DROP TABLE IF EXISTS new__migration_corpus_article")
                cursor.execute("DROP TABLE IF EXISTS migration_corpus_author")
                cursor.execute("DROP TABLE IF EXISTS new__migration_corpus_author")
