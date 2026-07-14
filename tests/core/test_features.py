"""Tests for the static Django 6 database-capability declarations."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from django_pyturso.base import DatabaseWrapper
from django_pyturso.features import DatabaseFeatures
from tests.support import wrapper_settings

pytestmark = pytest.mark.core


def test_core_capability_declarations() -> None:
    assert vars(DatabaseFeatures)["supports_transactions"] is True
    assert vars(DatabaseFeatures)["supports_explaining_query_execution"] is True


def test_database_capability_methods_apply_fixed_declarations() -> None:
    features = DatabaseFeatures(DatabaseWrapper(wrapper_settings(), "capabilities"))

    managed = SimpleNamespace(_meta=SimpleNamespace(managed=True))
    unmanaged = SimpleNamespace(_meta=SimpleNamespace(managed=False))
    assert not features.allows_group_by_selected_pks_on_model(managed)
    features.allows_group_by_selected_pks = True
    assert features.allows_group_by_selected_pks_on_model(managed)
    assert not features.allows_group_by_selected_pks_on_model(unmanaged)


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
