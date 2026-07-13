"""Run one offline stage of the shared-file interoperability corpus."""
# mypy: disable-error-code=misc

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from django.conf import settings


def _configure(engine: str, database: Path) -> None:
    settings.configure(
        DATABASES={"default": {"ENGINE": engine, "NAME": str(database)}},
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        INSTALLED_APPS=[],
        SECRET_KEY="file-interop",
    )


def _rows(model: Any) -> list[list[Any]]:
    names = [field.name for field in model._meta.local_fields if field.name != "id"]
    return [
        [row["id"], *(row[name] for name in names)]
        for row in model.objects.order_by("id").values("id", *names)
    ]


def _run(stage: str) -> dict[str, Any]:
    import django

    django.setup()
    from django.db import connection, models

    has_status = stage in {"sqlite_verify_write", "turso_final_verify"}

    class InteropRecord(models.Model):
        objects = models.Manager["InteropRecord"]()
        title = models.CharField(max_length=80, unique=True)
        rank = models.IntegerField(null=True)
        payload = models.JSONField()
        if has_status:
            status = models.CharField(default="ready", max_length=12)

        class Meta:
            app_label = "file_interop"
            db_table = "file_interop_record"
            indexes = [models.Index(fields=["rank"], name="file_interop_rank_idx")]

    if stage == "sqlite_seed":
        with connection.schema_editor() as editor:
            editor.create_model(InteropRecord)
        InteropRecord.objects.bulk_create(
            [
                InteropRecord(title="alpha", rank=1, payload={"source": "sqlite"}),
                InteropRecord(title="beta", rank=None, payload={"source": "sqlite"}),
            ]
        )
    elif stage == "turso_migrate_write":
        before = _rows(InteropRecord)
        status = models.CharField(default="ready", max_length=12)
        status.contribute_to_class(InteropRecord, "status")
        with connection.schema_editor() as editor:
            editor.add_field(InteropRecord, status)
        InteropRecord.objects.filter(title="alpha").update(status="migrated")
        InteropRecord.objects.create(
            title="gamma", rank=3, payload={"source": "turso"}, status="created"
        )
        return {"before": before, "after": _rows(InteropRecord)}
    elif stage == "sqlite_verify_write":
        before = _rows(InteropRecord)
        InteropRecord.objects.filter(title="beta").update(
            rank=2, payload={"source": "sqlite-again"}, status="updated"
        )
        return {"before": before, "after": _rows(InteropRecord)}
    elif stage != "turso_final_verify":
        raise ValueError(f"Unknown stage: {stage}")

    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(
            cursor, "file_interop_record"
        )
        constraints = connection.introspection.get_constraints(cursor, "file_interop_record")
    return {
        "columns": [field.name for field in description],
        "has_rank_index": "file_interop_rank_idx" in constraints,
        "rows": _rows(InteropRecord),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("sqlite", "turso"), required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    engine = "django.db.backends.sqlite3" if args.backend == "sqlite" else "django_pyturso"
    _configure(engine, args.database)
    print(json.dumps(_run(args.stage), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
