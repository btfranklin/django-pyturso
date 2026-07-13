"""Tests for the static Django 6 database-capability declarations."""

from __future__ import annotations

from django.db.backends.base.features import BaseDatabaseFeatures

from django_pyturso.features import DatabaseFeatures


def _public_base_capability_names() -> set[str]:
    return {name for name in vars(BaseDatabaseFeatures) if not name.startswith("_")}


def test_every_django_6_base_capability_has_an_explicit_disposition() -> None:
    expected = _public_base_capability_names()

    assert expected <= set(vars(DatabaseFeatures))


def test_mutating_base_transaction_probe_is_replaced_by_fixed_evidence() -> None:
    assert vars(DatabaseFeatures)["supports_transactions"] is True
    assert vars(DatabaseFeatures)["supports_explaining_query_execution"] is True


def test_high_risk_conservative_values_match_the_v1_contract() -> None:
    expected = {
        "can_clone_databases": False,
        "has_native_duration_field": False,
        "has_native_uuid_field": False,
        "has_select_for_update": False,
        "has_zoneinfo_database": False,
        "supports_aggregate_distinct_multiple_argument": False,
        "supports_aggregate_filter_clause": False,
        "supports_aggregate_order_by_clause": False,
        "supports_any_value": False,
        "supports_cast_with_precision": False,
        "supports_json_field_contains": False,
        "supports_non_deterministic_collations": False,
        "supports_over_clause": False,
        "supports_parentheses_in_compound": False,
        "supports_stored_generated_columns": False,
        "supports_temporal_subtraction": False,
        "supports_timezones": False,
        "supports_tuple_comparison_against_subquery": False,
        "supports_virtual_generated_columns": False,
        "test_db_allows_multiple_connections": False,
    }

    for name, value in expected.items():
        assert getattr(DatabaseFeatures, name) is value


def test_fixed_backend_limits_and_version_floor() -> None:
    assert DatabaseFeatures.minimum_database_version == (3, 50, 0)
    assert DatabaseFeatures.max_query_params == 999
    assert DatabaseFeatures.time_cast_precision == 3
