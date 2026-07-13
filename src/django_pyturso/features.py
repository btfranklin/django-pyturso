"""Static Django database-capability declarations for embedded Turso."""

from __future__ import annotations

from typing import Any

from django.db import ProgrammingError
from django.db.backends.base.features import BaseDatabaseFeatures


class DatabaseFeatures(BaseDatabaseFeatures):
    """Django capabilities audited against 6.0.7 and the supported Turso floor."""

    minimum_database_version = (3, 50, 0)
    gis_enabled = False
    allows_group_by_lob = True
    allows_group_by_selected_pks = False
    allows_group_by_select_index = True
    empty_fetchmany_value: list[Any] = []
    update_can_self_select = True
    delete_can_self_reference_subquery = True
    interprets_empty_strings_as_nulls = False
    supports_nullable_unique_constraints = True
    supports_partially_nullable_unique_constraints = True
    supports_nulls_distinct_unique_constraints = False
    supports_deferrable_unique_constraints = False
    can_use_chunked_reads = True
    can_return_columns_from_insert = True
    can_return_rows_from_bulk_insert = True
    can_return_rows_from_update = True
    has_bulk_insert = True
    uses_savepoints = True
    can_release_savepoints = True
    related_fields_match_type = False
    allow_sliced_subqueries_with_in = True
    has_select_for_update = False
    has_select_for_update_nowait = False
    has_select_for_update_skip_locked = False
    has_select_for_update_of = False
    has_select_for_no_key_update = False
    select_for_update_of_column = False
    test_db_allows_multiple_connections = False
    supports_unspecified_pk = True
    supports_forward_references = True
    truncates_names = False
    has_real_datatype = False
    supports_subqueries_in_group_by = True
    ignores_unnecessary_order_by_in_subqueries = True
    has_native_uuid_field = False
    has_native_duration_field = False
    supports_temporal_subtraction = False
    supports_regex_backreferencing = True
    supports_date_lookup_using_string = True
    supports_timezones = False
    has_zoneinfo_database = False
    requires_explicit_null_ordering_when_grouping = False
    nulls_order_largest = False
    supports_order_by_nulls_modifier = True
    order_by_nulls_first = True
    max_query_params = 999
    allows_auto_pk_0 = True
    can_defer_constraint_checks = True
    supports_tablespaces = False
    supports_sequence_reset = True
    can_introspect_default = True
    can_introspect_foreign_keys = True
    introspected_field_types = {
        "AutoField": "AutoField",
        "BigAutoField": "AutoField",
        "BigIntegerField": "BigIntegerField",
        "BinaryField": "BinaryField",
        "BooleanField": "BooleanField",
        "CharField": "CharField",
        "DurationField": "BigIntegerField",
        "GenericIPAddressField": "CharField",
        "IntegerField": "IntegerField",
        "PositiveBigIntegerField": "PositiveBigIntegerField",
        "PositiveIntegerField": "PositiveIntegerField",
        "PositiveSmallIntegerField": "PositiveSmallIntegerField",
        "SmallAutoField": "AutoField",
        "SmallIntegerField": "SmallIntegerField",
        "TimeField": "TimeField",
    }
    supports_index_column_ordering = True
    can_introspect_materialized_views = False
    can_distinct_on_fields = False
    atomic_transactions = False
    can_rollback_ddl = True
    schema_editor_uses_clientside_param_binding = False
    supports_combined_alters = False
    supports_foreign_keys = True
    can_create_inline_fk = False
    can_rename_index = False
    indexes_foreign_keys = True
    supports_column_check_constraints = True
    supports_table_check_constraints = True
    can_introspect_check_constraints = True
    supports_paramstyle_pyformat = True
    requires_literal_defaults = True
    supports_expression_defaults = True
    supports_default_keyword_in_insert = False
    supports_default_keyword_in_bulk_insert = False
    connection_persists_old_columns = False
    closed_cursor_error_class = ProgrammingError
    has_case_insensitive_like = True
    bare_select_suffix = ""
    implied_column_null = False
    supports_select_for_update_with_limit = True
    greatest_least_ignores_nulls = False
    can_clone_databases = False
    ignores_table_name_case = True
    for_update_after_from = False
    supports_select_union = True
    supports_select_intersection = True
    supports_select_difference = True
    supports_slicing_ordering_in_compound = False
    supports_parentheses_in_compound = False
    requires_compound_order_by_subquery = False
    supports_aggregate_filter_clause = False
    supports_aggregate_order_by_clause = False
    supports_aggregate_distinct_multiple_argument = False
    supports_any_value = False
    supports_index_on_text_field = True
    supports_over_clause = False
    supports_frame_range_fixed_distance = False
    supports_frame_exclusion = False
    only_supports_unbounded_with_preceding_and_following = False
    supports_cast_with_precision = False
    time_cast_precision = 3
    create_test_procedure_without_params_sql = None
    create_test_procedure_with_int_param_sql = None
    supports_callproc_kwargs = False
    supported_explain_formats: set[str] = set()
    supports_default_in_lead_lag = True
    supports_ignore_conflicts = True
    supports_update_conflicts = True
    supports_update_conflicts_with_target = True
    requires_casted_case_in_updates = False
    supports_partial_indexes = True
    supports_functions_in_partial_indexes = True
    supports_covering_indexes = False
    supports_expression_indexes = True
    collate_as_index_expression = False
    allows_multiple_constraints_on_same_fields = True
    supports_boolean_expr_in_select_clause = True
    supports_comparing_boolean_expr = True
    supports_json_field = True
    can_introspect_json_field = True
    supports_primitives_in_json_field = True
    has_native_json_field = False
    has_json_operators = False
    supports_json_field_contains = False
    json_key_contains_list_matching_requires_list = False
    has_json_object_function = True
    supports_json_negative_indexing = True
    supports_collation_on_charfield = True
    supports_collation_on_textfield = True
    supports_non_deterministic_collations = False
    supports_comments = False
    supports_comments_inline = False
    supports_stored_generated_columns = False
    supports_virtual_generated_columns = False
    supports_logical_xor = False
    prohibits_null_characters_in_text_exception = None
    supports_unlimited_charfield = True
    supports_tuple_lookups = True
    supports_tuple_comparison_against_subquery = False
    test_collations = {
        "ci": None,
        "cs": None,
        "non_default": None,
        "swedish_ci": None,
        "virtual": None,
    }
    test_now_utc_template = None
    insert_test_table_with_defaults = 'INSERT INTO {} ("null") VALUES (1)'
    rounds_to_even = False
    django_test_expected_failures: set[str] = set()
    django_test_skips: dict[str, set[str]] = {}

    # Turso 3.50 supports the direct DROP COLUMN syntax. Schema code may still
    # choose a table remake when Django's operation needs more than that syntax.
    can_alter_table_drop_column = True

    supports_explaining_query_execution = True
    supports_transactions = True

    def allows_group_by_selected_pks_on_model(self, model: Any) -> bool:
        """Apply Django's verified base rule without inheriting it implicitly."""

        return self.allows_group_by_selected_pks and model._meta.managed
