"""Execute the backend-neutral differential catalog in an isolated process."""
# mypy: disable-error-code=misc

# django-stubs cannot bind nested, runtime-defined model managers to their
# model classes. Keep all other strict checks enabled for this subprocess tool.

from __future__ import annotations

import argparse
import datetime
import decimal
import json
from pathlib import Path
from typing import Any, cast

from django.conf import settings


def _configure(engine: str, database_name: str) -> None:
    settings.configure(
        DATABASES={"default": {"ENGINE": engine, "NAME": database_name}},
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        INSTALLED_APPS=[],
        SECRET_KEY="differential-runner",
        TIME_ZONE="UTC",
        USE_TZ=True,
    )


def _canonical(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return format(value, "f")
    if isinstance(value, datetime.datetime):
        return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _run_catalog() -> dict[str, Any]:
    import django

    django.setup()

    from django.db import connection, models, transaction
    from django.db.models import Exists, F, OuterRef, Subquery
    from django.db.models.functions import Random

    class Author(models.Model):
        objects = models.Manager["Author"]()
        name = models.CharField(max_length=40, unique=True)

        class Meta:
            app_label = "differential"
            db_table = "differential_author"

    class Record(models.Model):
        objects = models.Manager["Record"]()
        author = models.ForeignKey(Author, on_delete=models.CASCADE)
        title = models.CharField(max_length=80)
        rank = models.IntegerField(null=True)
        amount = models.DecimalField(decimal_places=2, max_digits=8)
        active = models.BooleanField(default=True)
        note = models.TextField(null=True)
        payload = models.JSONField()
        happened_at = models.DateTimeField()

        class Meta:
            app_label = "differential"
            db_table = "differential_record"
            constraints = [
                models.UniqueConstraint(fields=["title"], name="differential_record_title_uq")
            ]
            indexes = [models.Index(fields=["rank"], name="differential_record_rank_idx")]

    class SchemaProbe(models.Model):
        objects = models.Manager["SchemaProbe"]()
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "differential"
            db_table = "differential_schema_probe"

    with connection.schema_editor() as editor:
        editor.create_model(Author)
        editor.create_model(Record)
        editor.create_model(SchemaProbe)

    alice = Author.objects.create(name="Alice")
    bob = Author.objects.create(name="Bob")
    moment = datetime.datetime(2026, 7, 13, 18, 42, 31, 123456, tzinfo=datetime.UTC)
    Record.objects.bulk_create(
        [
            Record(
                author=alice,
                title="alpha",
                rank=2,
                amount=decimal.Decimal("12.50"),
                active=True,
                note=None,
                payload={"items": ["a", "z"], "nested": {"enabled": True}},
                happened_at=moment,
            ),
            Record(
                author=bob,
                title="beta",
                rank=None,
                amount=decimal.Decimal("0.00"),
                active=False,
                note="present",
                payload={"items": [], "nested": {"enabled": False}},
                happened_at=moment + datetime.timedelta(seconds=1),
            ),
            Record(
                author=alice,
                title="gamma",
                rank=1,
                amount=decimal.Decimal("-3.25"),
                active=True,
                note="third",
                payload={"items": ["g"], "nested": {"enabled": True}},
                happened_at=moment + datetime.timedelta(seconds=2),
            ),
        ]
    )
    SchemaProbe.objects.create(name="preserved")

    observations: dict[str, Any] = {}

    created = Record.objects.create(
        author=bob,
        title="temporary",
        rank=9,
        amount=decimal.Decimal("1.00"),
        active=True,
        note=None,
        payload={"items": ["temporary"]},
        happened_at=moment,
    )
    Record.objects.filter(pk=created.pk).update(title="temporary-updated", rank=10)
    refreshed = Record.objects.get(pk=created.pk)
    deleted_count, _ = refreshed.delete()
    observations["crud"] = {
        "deleted": deleted_count,
        "remaining": Record.objects.count(),
        "updated": [refreshed.title, refreshed.rank],
    }

    scalar = Record.objects.values(
        "active", "amount", "happened_at", "note", "payload", "rank", "title"
    ).get(title="alpha")
    observations["scalars_and_nulls"] = _canonical(scalar)

    observations["ordering"] = list(
        Record.objects.order_by(F("rank").asc(nulls_last=True), "title").values_list(
            "title", flat=True
        )
    )
    observations["joins"] = list(
        Record.objects.filter(author__name="Alice")
        .order_by("title")
        .values_list("title", "author__name")
    )

    latest_title = (
        Record.objects.filter(author=OuterRef("pk")).order_by("-rank").values("title")[:1]
    )
    authors = Author.objects.annotate(
        has_active=Exists(Record.objects.filter(author=OuterRef("pk"), active=True)),
        latest_title=Subquery(latest_title),
    ).order_by("name")
    observations["subqueries"] = list(
        authors.values_list("name", "has_active", "latest_title")
    )

    observations["json"] = {
        "first_item": list(
            Record.objects.filter(payload__items__0="a").values_list("title", flat=True)
        ),
        "nested_true": list(
            Record.objects.filter(payload__nested__enabled=True)
            .order_by("title")
            .values_list("title", flat=True)
        ),
    }

    before = Record.objects.count()
    try:
        with transaction.atomic():
            Record.objects.create(
                author=alice,
                title="rolled-back",
                rank=5,
                amount=decimal.Decimal("5.00"),
                payload={},
                happened_at=moment,
            )
            raise RuntimeError("rollback sentinel")
    except RuntimeError:
        pass
    with transaction.atomic():
        Record.objects.create(
            author=alice,
            title="outer-committed",
            rank=6,
            amount=decimal.Decimal("6.00"),
            payload={},
            happened_at=moment,
        )
        try:
            with transaction.atomic():
                Record.objects.create(
                    author=alice,
                    title="inner-rolled-back",
                    rank=7,
                    amount=decimal.Decimal("7.00"),
                    payload={},
                    happened_at=moment,
                )
                raise RuntimeError("savepoint sentinel")
        except RuntimeError:
            pass
    observations["transactions"] = {
        "after_outer_commit": Record.objects.count(),
        "before": before,
        "inner_exists": Record.objects.filter(title="inner-rolled-back").exists(),
        "outer_exists": Record.objects.filter(title="outer-committed").exists(),
        "rolled_back_exists": Record.objects.filter(title="rolled-back").exists(),
    }

    added = models.CharField(default="added", max_length=12)
    added.contribute_to_class(SchemaProbe, "added_by_schema")
    with connection.schema_editor() as editor:
        editor.add_field(SchemaProbe, added)
    added_values = list(
        SchemaProbe.objects.order_by("name").values_list("added_by_schema", flat=True)
    )
    with connection.schema_editor() as editor:
        editor.remove_field(SchemaProbe, added)
    with connection.cursor() as cursor:
        columns_after_remove = [
            column.name
            for column in connection.introspection.get_table_description(
                cursor, "differential_schema_probe"
            )
        ]
    observations["schema"] = {
        "added_default_count": added_values.count("added"),
        "added_default_total": len(added_values),
        "column_removed": "added_by_schema" not in columns_after_remove,
    }

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, "differential_record")
        relations = connection.introspection.get_relations(cursor, "differential_record")
    observations["introspection"] = {
        "foreign_key": any(value.get("foreign_key") for value in constraints.values()),
        "primary_key": any(value.get("primary_key") for value in constraints.values()),
        "rank_index": "differential_record_rank_idx" in constraints,
        "relation_columns": sorted(str(column) for column in relations),
        "tables": sorted(
            name
            for name in connection.introspection.table_names()
            if name.startswith("differential_")
        ),
        "title_unique": any(
            value.get("unique") and value.get("columns") == ["title"]
            for value in constraints.values()
        ),
    }

    observations["backend_identity"] = {
        "display_name": connection.display_name,
        "engine": connection.settings_dict["ENGINE"],
    }
    try:
        random_count = len(list(Record.objects.order_by(Random()).values_list("pk", flat=True)))
    except Exception as error:  # The exception class is the observable contract.
        observations["random_function"] = {
            "exception": type(error).__name__,
            "status": "rejected",
        }
    else:
        observations["random_function"] = {"count": random_count, "status": "supported"}

    return cast(dict[str, Any], _canonical(observations))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("sqlite", "turso"), required=True)
    parser.add_argument("--mode", choices=("memory", "file"), required=True)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()

    engine = "django.db.backends.sqlite3" if args.backend == "sqlite" else "django_pyturso"
    if args.mode == "memory":
        database_name = ":memory:"
    elif args.database is None:
        parser.error("--database is required for file mode")
    else:
        database_name = str(args.database)
    _configure(engine, database_name)
    print(json.dumps(_run_catalog(), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
