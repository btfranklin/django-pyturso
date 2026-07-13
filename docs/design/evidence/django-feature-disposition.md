# Django 6.0.7 Feature Disposition

This is the exhaustive disposition of the public attributes, cached properties,
and helpers declared by Django 6.0.7 `BaseDatabaseFeatures`. The drift test
fails if Django changes that interface without a deliberate backend decision.

Evidence basis: CPython 3.14.6, Django 6.0.7, `pyturso` 0.6.1, connected
Turso 3.50.4, the Phase 0 driver probes, and focused backend tests. Values stay
conservative when the complete Django meaning has not been proven.

| Django member | Backend value or implementation | Disposition |
| --- | --- | --- |
| `allow_sliced_subqueries_with_in` | `True` | verified explicit value |
| `allows_auto_pk_0` | `True` | verified explicit value |
| `allows_group_by_lob` | `True` | verified explicit value |
| `allows_group_by_select_index` | `True` | verified explicit value |
| `allows_group_by_selected_pks` | `False` | verified explicit value |
| `allows_group_by_selected_pks_on_model` | `explicit method` | verified explicit implementation |
| `allows_multiple_constraints_on_same_fields` | `True` | verified explicit value |
| `atomic_transactions` | `False` | fixed backend value |
| `bare_select_suffix` | `''` | verified explicit value |
| `can_clone_databases` | `False` | verified explicit value |
| `can_create_inline_fk` | `False` | fixed backend value |
| `can_defer_constraint_checks` | `True` | fixed backend value |
| `can_distinct_on_fields` | `False` | verified explicit value |
| `can_introspect_check_constraints` | `True` | verified explicit value |
| `can_introspect_default` | `True` | verified explicit value |
| `can_introspect_foreign_keys` | `True` | verified explicit value |
| `can_introspect_json_field` | `True` | verified explicit value |
| `can_introspect_materialized_views` | `False` | verified explicit value |
| `can_release_savepoints` | `True` | fixed backend value |
| `can_rename_index` | `False` | verified explicit value |
| `can_return_columns_from_insert` | `True` | fixed backend value |
| `can_return_rows_from_bulk_insert` | `True` | fixed backend value |
| `can_return_rows_from_update` | `True` | fixed backend value |
| `can_rollback_ddl` | `True` | fixed backend value |
| `can_use_chunked_reads` | `True` | verified explicit value |
| `closed_cursor_error_class` | `ProgrammingError` | verified explicit value |
| `collate_as_index_expression` | `False` | verified explicit value |
| `connection_persists_old_columns` | `False` | verified explicit value |
| `create_test_procedure_with_int_param_sql` | `None` | verified explicit value |
| `create_test_procedure_without_params_sql` | `None` | verified explicit value |
| `delete_can_self_reference_subquery` | `True` | verified explicit value |
| `django_test_expected_failures` | `set()` | verified explicit value |
| `django_test_skips` | `{}` | verified explicit value |
| `empty_fetchmany_value` | `[]` | verified explicit value |
| `for_update_after_from` | `False` | verified explicit value |
| `gis_enabled` | `False` | verified explicit value |
| `greatest_least_ignores_nulls` | `False` | verified explicit value |
| `has_bulk_insert` | `True` | verified explicit value |
| `has_case_insensitive_like` | `True` | fixed backend value |
| `has_json_object_function` | `True` | verified explicit value |
| `has_json_operators` | `False` | verified explicit value |
| `has_native_duration_field` | `False` | verified explicit value |
| `has_native_json_field` | `False` | verified explicit value |
| `has_native_uuid_field` | `False` | verified explicit value |
| `has_real_datatype` | `False` | verified explicit value |
| `has_select_for_no_key_update` | `False` | verified explicit value |
| `has_select_for_update` | `False` | verified explicit value |
| `has_select_for_update_nowait` | `False` | verified explicit value |
| `has_select_for_update_of` | `False` | verified explicit value |
| `has_select_for_update_skip_locked` | `False` | verified explicit value |
| `has_zoneinfo_database` | `False` | fixed backend value |
| `ignores_table_name_case` | `True` | fixed backend value |
| `ignores_unnecessary_order_by_in_subqueries` | `True` | verified explicit value |
| `implied_column_null` | `False` | verified explicit value |
| `indexes_foreign_keys` | `True` | verified explicit value |
| `insert_test_table_with_defaults` | `'INSERT INTO {} ("null") VALUES (1)'` | fixed backend value |
| `interprets_empty_strings_as_nulls` | `False` | verified explicit value |
| `introspected_field_types` | `explicit collection in features.py` | fixed backend value |
| `json_key_contains_list_matching_requires_list` | `False` | verified explicit value |
| `max_query_params` | `999` | fixed backend value |
| `minimum_database_version` | `(3, 50, 0)` | fixed backend value |
| `nulls_order_largest` | `False` | verified explicit value |
| `only_supports_unbounded_with_preceding_and_following` | `False` | verified explicit value |
| `order_by_nulls_first` | `True` | fixed backend value |
| `prohibits_null_characters_in_text_exception` | `None` | verified explicit value |
| `related_fields_match_type` | `False` | verified explicit value |
| `requires_casted_case_in_updates` | `False` | verified explicit value |
| `requires_compound_order_by_subquery` | `False` | verified explicit value |
| `requires_explicit_null_ordering_when_grouping` | `False` | verified explicit value |
| `requires_literal_defaults` | `True` | fixed backend value |
| `rounds_to_even` | `False` | verified explicit value |
| `schema_editor_uses_clientside_param_binding` | `False` | verified explicit value |
| `select_for_update_of_column` | `False` | verified explicit value |
| `supported_explain_formats` | `set()` | verified explicit value |
| `supports_aggregate_distinct_multiple_argument` | `False` | fixed backend value |
| `supports_aggregate_filter_clause` | `False` | verified explicit value |
| `supports_aggregate_order_by_clause` | `False` | verified explicit value |
| `supports_any_value` | `False` | verified explicit value |
| `supports_boolean_expr_in_select_clause` | `True` | verified explicit value |
| `supports_callproc_kwargs` | `False` | verified explicit value |
| `supports_cast_with_precision` | `False` | fixed backend value |
| `supports_collation_on_charfield` | `True` | verified explicit value |
| `supports_collation_on_textfield` | `True` | verified explicit value |
| `supports_column_check_constraints` | `True` | verified explicit value |
| `supports_combined_alters` | `False` | verified explicit value |
| `supports_comments` | `False` | verified explicit value |
| `supports_comments_inline` | `False` | verified explicit value |
| `supports_comparing_boolean_expr` | `True` | verified explicit value |
| `supports_covering_indexes` | `False` | verified explicit value |
| `supports_date_lookup_using_string` | `True` | verified explicit value |
| `supports_default_in_lead_lag` | `True` | verified explicit value |
| `supports_default_keyword_in_bulk_insert` | `False` | fixed backend value |
| `supports_default_keyword_in_insert` | `False` | fixed backend value |
| `supports_deferrable_unique_constraints` | `False` | verified explicit value |
| `supports_explaining_query_execution` | `True` | fixed backend value |
| `supports_expression_defaults` | `True` | verified explicit value |
| `supports_expression_indexes` | `True` | verified explicit value |
| `supports_foreign_keys` | `True` | verified explicit value |
| `supports_forward_references` | `True` | verified explicit value |
| `supports_frame_exclusion` | `False` | verified explicit value |
| `supports_frame_range_fixed_distance` | `False` | verified explicit value |
| `supports_functions_in_partial_indexes` | `True` | verified explicit value |
| `supports_ignore_conflicts` | `True` | verified explicit value |
| `supports_index_column_ordering` | `True` | verified explicit value |
| `supports_index_on_text_field` | `True` | verified explicit value |
| `supports_json_field` | `True` | verified explicit value |
| `supports_json_field_contains` | `False` | fixed backend value |
| `supports_json_negative_indexing` | `True` | verified explicit value |
| `supports_logical_xor` | `False` | verified explicit value |
| `supports_non_deterministic_collations` | `False` | fixed backend value |
| `supports_nullable_unique_constraints` | `True` | verified explicit value |
| `supports_nulls_distinct_unique_constraints` | `False` | verified explicit value |
| `supports_order_by_nulls_modifier` | `True` | verified explicit value |
| `supports_over_clause` | `False` | verified explicit value |
| `supports_paramstyle_pyformat` | `True` | verified explicit value |
| `supports_parentheses_in_compound` | `False` | fixed backend value |
| `supports_partial_indexes` | `True` | verified explicit value |
| `supports_partially_nullable_unique_constraints` | `True` | verified explicit value |
| `supports_primitives_in_json_field` | `True` | verified explicit value |
| `supports_regex_backreferencing` | `True` | verified explicit value |
| `supports_select_difference` | `True` | verified explicit value |
| `supports_select_for_update_with_limit` | `True` | verified explicit value |
| `supports_select_intersection` | `True` | verified explicit value |
| `supports_select_union` | `True` | verified explicit value |
| `supports_sequence_reset` | `True` | verified explicit value |
| `supports_slicing_ordering_in_compound` | `False` | verified explicit value |
| `supports_stored_generated_columns` | `False` | verified explicit value |
| `supports_subqueries_in_group_by` | `True` | verified explicit value |
| `supports_table_check_constraints` | `True` | verified explicit value |
| `supports_tablespaces` | `False` | verified explicit value |
| `supports_temporal_subtraction` | `False` | verified explicit value |
| `supports_timezones` | `False` | fixed backend value |
| `supports_transactions` | `True` | fixed backend value |
| `supports_tuple_comparison_against_subquery` | `False` | fixed backend value |
| `supports_tuple_lookups` | `True` | verified explicit value |
| `supports_unlimited_charfield` | `True` | fixed backend value |
| `supports_unspecified_pk` | `True` | fixed backend value |
| `supports_update_conflicts` | `True` | fixed backend value |
| `supports_update_conflicts_with_target` | `True` | fixed backend value |
| `supports_virtual_generated_columns` | `False` | verified explicit value |
| `test_collations` | `explicit collection in features.py` | verified explicit value |
| `test_db_allows_multiple_connections` | `False` | fixed backend value |
| `test_now_utc_template` | `None` | verified explicit value |
| `time_cast_precision` | `3` | fixed backend value |
| `truncates_names` | `False` | verified explicit value |
| `update_can_self_select` | `True` | verified explicit value |
| `uses_savepoints` | `True` | verified explicit value |

## High-risk decisions

- Transaction support is a fixed `True`; Django's inherited mutating table
  probe is not used.
- Window frames, aggregate filtering and ordering, generated columns, native
  time zones, `SELECT FOR UPDATE`, database cloning, JSON containment,
  custom nondeterministic collations, multi-argument distinct aggregates, and
  tuple comparison against subqueries remain false.
- `max_query_params` is 999, `time_cast_precision` is 3, and the connected
  engine floor is 3.50.0.
- These static declarations never vary by environment variable, database
  setting, connection probe, or installed engine function.

## Drift enforcement

`tests/unit/test_features.py` reads the public namespace declared directly by
Django 6.0.7 `BaseDatabaseFeatures` and requires every member to be declared
directly on `DatabaseFeatures`, so a new inherited default or mutating probe
cannot become supported accidentally. The evidence check lives in the test
suite; production imports contain only the fixed backend declarations.
