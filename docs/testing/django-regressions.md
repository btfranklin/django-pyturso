# Selected Django Regression Sources

The tests in `tests/django_regressions/` are adapted from Django 6.0.7 at commit
[`e2a424605ac2e7e6e799496542fb2997207e2f23`](https://github.com/django/django/commit/e2a424605ac2e7e6e799496542fb2997207e2f23).
The [third-party notice](../../THIRD_PARTY_NOTICES.md) contains Django's license.

## Selection and Test Setup

The existing backend suite covers basic CRUD, scalar conversion, nested JSON
equality, joins, correlated subqueries, and nested transaction rollback. These
selected upstream cases add bulk conflict handling, batched bulk update
rollback, JSON null distinctions, JSON key expressions, expression reuse, and
transaction error recovery.

The local tests use pytest assertions and two small models in a separate app
registry. A fixture creates real Turso tables before each case and removes them
after it. It checks the configured backend engine. It does not replace the
driver or Django's SQL compiler. There are no feature skips in this suite.

The suite contains 20 functions and 26 collected cases. It runs with WAL memory
and file settings, and with MVCC memory and file settings. See
[Testing](../testing.md) for commands and CI coverage.

## Source Map

All source links below use the exact commit specified above. Local file paths
are relative to `tests/django_regressions/`.

| Local test | Upstream source method | Local changes |
| --- | --- | --- |
| `test_bulk.py::test_bulk_create_mixed_primary_keys` | [tests/bulk_create/tests.py: BulkCreateTests.test_large_batch_mixed](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/bulk_create/tests.py#L226-L242) | Use 20 rows and batches of three. Retain the explicit and generated primary key counts. |
| `test_bulk.py::test_bulk_create_sql_expressions` | [tests/bulk_create/tests.py: BulkCreateTests.test_bulk_insert_expressions](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/bulk_create/tests.py#L304-L312) | Use the local record model. Retain the `Lower(Value(...))` insert and query. |
| `test_bulk.py::test_bulk_create_ignore_conflicts` | [tests/bulk_create/tests.py: BulkCreateTests.test_ignore_conflicts_ignore](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/bulk_create/tests.py#L396-L423) | Use one unique name field. Combine duplicate and new rows in one insert. Check that a failed ordinary insert preserves the existing rows. |
| `test_bulk.py::test_bulk_create_update_conflicts_with_db_columns` | [tests/bulk_create/tests.py: BulkCreateTests.test_update_conflicts_unique_fields_update_fields_db_column](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/bulk_create/tests.py#L823-L853) | Use the local rank model. Require returned primary keys because the backend declares this support. Retain custom column names on both fields. |
| `test_bulk.py::test_bulk_update_field_references` | [tests/queries/test_bulk_update.py: BulkUpdateTests.test_field_references](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/queries/test_bulk_update.py#L242-L247) | Use four rows in batches of two. Retain the `F()` increment and check the update count. |
| `test_bulk.py::test_bulk_update_duplicate_row_counts` | [tests/queries/test_bulk_update.py: BulkUpdateTests.test_updated_rows_when_passing_duplicates](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/queries/test_bulk_update.py#L175-L181) | Use the local record model. Retain both the single-batch and two-batch counts. |
| `test_bulk.py::test_bulk_update_batches_are_atomic` | [tests/queries/test_bulk_update.py: BulkUpdateTests.test_database_routing_batch_atomicity](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/queries/test_bulk_update.py#L359-L366) | Use the default Turso connection without a database router. Retain the second-batch unique failure and check both original names after rollback. |
| `test_bulk.py::test_bulk_update_json_sql_null` | [tests/queries/test_bulk_update.py: BulkUpdateTests.test_json_field_sql_null](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/queries/test_bulk_update.py#L304-L320) | Collect direct `None`, `Value(None)`, and a null `Coalesce` as separate cases. Retain the SQL-null lookup. |
| `test_json.py::test_json_null_differs_from_sql_null` | [tests/model_fields/test_jsonfield.py: TestSaveLoad.test_json_null_different_from_sql_null](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/model_fields/test_jsonfield.py#L227-L247) | Use the local payload field. Retain JSON-null insertion and update, SQL-null insertion, all three lookups, and Python equality. |
| `test_json.py::test_has_key_matches_json_null` | [tests/model_fields/test_jsonfield.py: TestQuerying.test_has_key_null_value](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/model_fields/test_jsonfield.py#L566-L570) | Use explicit present-null, missing-key, and SQL-null rows. |
| `test_json.py::test_json_key_in` | [tests/model_fields/test_jsonfield.py: TestQuerying.test_key_in](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/model_fields/test_jsonfield.py#L996-L1027) | Select five variants: number, string, nested `F()` reference, true, and false. Use one matching row and a missing-key row. |
| `test_json.py::test_group_by_nested_json_key` | [tests/model_fields/test_jsonfield.py: TestQuerying.test_ordering_grouping_by_key_transform](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/model_fields/test_jsonfield.py#L408-L427) | Retain the nested text-key grouping and count. Use three explicit rows. Omit the separate ordering-only assertions. |
| `test_json.py::test_nested_json_transform_on_subquery` | [tests/model_fields/test_jsonfield.py: TestQuerying.test_nested_key_transform_on_subquery](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/model_fields/test_jsonfield.py#L524-L536) | Retain the correlated JSON subquery and chained object/array transforms. Use matching and nonmatching nested rows. |
| `test_expressions.py::test_range_lookup_with_field_expressions` | [tests/expressions/tests.py: IterableLookupInnerExpressionsTests.test_range_lookup_allows_F_expressions_and_expressions_for_integers](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/expressions/tests.py#L1243-L1263) | Use local integer fields and the same five numeric pairs. Retain the three expression-based range variants. |
| `test_expressions.py::test_field_expression_reuse_across_models` | [tests/expressions/tests.py: ExpressionsTests.test_F_reuse](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/expressions/tests.py#L1425-L1440) | Use both local models. Retain expression reuse and repeated evaluation of the first query. |
| `test_expressions.py::test_decimal_expression_filter` | [tests/expressions/tests.py: ExpressionsNumericTests.test_filter_decimal_expression](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/expressions/tests.py#L1655-L1660) | Use the local integer and decimal fields. Retain the decimal output field and combined filters. |
| `test_expressions.py::test_negated_empty_exists_filter_and_annotation` | [tests/expressions/tests.py: ExistsTests.test_negated_empty_exists and test_select_negated_empty_exists](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/expressions/tests.py#L2574-L2585) | Combine the two upstream methods. Check both filtering and the converted Python boolean from the annotation. |
| `test_transactions.py::test_force_atomic_rollback` | [tests/transactions/tests.py: AtomicTests.test_force_rollback](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/transactions/tests.py#L206-L212) | Use the local record model. Retain the rollback flag and empty-table check. |
| `test_transactions.py::test_recover_merged_atomic_with_manual_savepoint` | [tests/transactions/tests.py: AtomicTests.test_prevent_rollback](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/transactions/tests.py#L214-L227) | Use the local table name in the invalid-column query. Retain merged atomic failure, manual savepoint recovery, and the surviving outer row. |
| `test_transactions.py::test_integrity_error_blocks_queries_until_atomic_rollback` | [tests/transactions/tests.py: AtomicErrorsTests.test_atomic_prevents_queries_in_broken_transaction](https://github.com/django/django/blob/e2a424605ac2e7e6e799496542fb2997207e2f23/tests/transactions/tests.py#L348-L364) | Use the local name field. Retain duplicate primary key failure, blocked queries, the exception cause, and the unchanged original row. |

These are selected regressions for supported backend behavior. They do not
represent the complete Django test suite. The batched rollback case does not
test database routing, and the range case does not test relational joins.
