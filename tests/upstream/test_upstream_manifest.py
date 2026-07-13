from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.upstream

MANIFEST_PATH = Path(__file__).parents[1] / "manifests/upstream-expectations.toml"
PINNED_COMMIT = "e2a424605ac2e7e6e799496542fb2997207e2f23"
EXPECTED_CATEGORIES = {"backend", "schema", "introspection", "transactions", "query"}
ADD_FIELD_DIFFERENCE = "UPSTREAM-INTENTIONAL-SCHEMA-REMAKE-NULLABLE-ADD"


def load_document() -> dict[str, Any]:
    with MANIFEST_PATH.open("rb") as stream:
        return tomllib.load(stream)


def test_manifest_pins_django_source_identity() -> None:
    source = load_document()["source"]

    assert source == {
        "repository": "https://github.com/django/django.git",
        "tag": "6.0.7",
        "commit": PINNED_COMMIT,
        "installed_version": "6.0.7",
    }


def test_smoke_lane_has_unique_exact_labels_across_all_categories() -> None:
    document = load_document()
    expectations = document["expectation"]
    smoke = [entry for entry in expectations if entry["profile"] == "smoke"]
    labels = [entry["label"] for entry in smoke]

    assert len(labels) == len(set(labels))
    assert {entry["category"] for entry in smoke} == EXPECTED_CATEGORIES
    assert all(label.count(".") >= 2 for label in labels)
    assert sum(entry["outcome"] == "pass" for entry in smoke) == 30
    assert all(entry["relevance"] for entry in smoke)
    assert document["runner"] == {
        "settings": "django_pyturso_upstream_settings",
        "parallel": 1,
        "default_profile": "smoke",
        "expected_passes": 30,
        "expected_skips": 1,
        "expected_failures": 0,
    }


def test_skip_is_an_explicit_intentional_difference() -> None:
    expectations = load_document()["expectation"]
    skipped = [entry for entry in expectations if entry["outcome"] == "skip"]

    assert skipped == [
        {
            "label": "schema.tests.SchemaTests.test_add_field",
            "category": "schema",
            "profile": "smoke",
            "outcome": "skip",
            "relevance": "Exercises adding a field through Django's schema editor.",
            "reason_code": ADD_FIELD_DIFFERENCE,
            "reason": (
                "Turso 0.6.1 stores ALTER TABLE ADD COLUMN ... NULL as NOT NULL, so the "
                "backend intentionally remakes the table; this conflicts only with the test's "
                "SQLite-specific no-CREATE-TABLE assertion."
            ),
        }
    ]
