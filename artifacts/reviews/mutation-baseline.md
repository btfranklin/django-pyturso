# Mutation Baseline Review

This is the exhaustive review of the final mutation run on 2026-07-13. The run generated 1,485 mutants: 1,340 were killed, 143 survived, and 2 timed out. Every current non-killed mutant was displayed individually with `pdm run mutmut show <name>`. All 145 names and diffs exactly match entries from the earlier exhaustive review, so their prior classifications are retained except for the two repeatedly rerun timeouts, whose deterministic behavior divergence is now considered detected.

## Conclusion

The final baseline has zero unreviewed mutants and zero behavior-changing survivors. All 143 survivors are equivalent, message-only non-contractual, typing-only, or unreachable under the fixed backend contract. The two graph-traversal mutations are behavior-changing but are not survivors: repeated isolated reruns deterministically hit the pytest timeout because they remove loop progress. Timeout is the test-detected divergence for those mutants.

## Final totals

| Result or classification | Count | Disposition |
| --- | ---: | --- |
| Generated | 1,485 | Complete run |
| Killed | 1,340 | Detected by assertions/exceptions |
| Reviewed behavior-changing divergence detected by timeout | 2 | Detected by deterministic pytest timeout |
| Equivalent survivors | 37 | Reviewed non-blocker |
| Exception/message-only non-contractual survivors | 77 | Reviewed non-blocker |
| Typing/annotation-only survivors | 2 | Reviewed non-blocker |
| Unreachable-under-fixed-contract survivors | 27 | Reviewed non-blocker |
| Behavior-changing survivors | 0 | None remain |
| Unreviewed non-killed mutants | 0 | None remain |

## Timeout disposition

Both timeouts are in `DatabaseOperations._references_graph_for_table()` and were rerun repeatedly in isolation:

- Replacing `current = pending.pop()` with `current = None` prevents the pending stack from shrinking, so the traversal cannot terminate.
- Replacing `seen.add(current)` with `seen.add(None)` prevents visited nodes from entering the seen set, so cyclic references are revisited indefinitely.

These are reviewed, behavior-changing divergences detected by the configured pytest timeout. They are neither surviving behavior changes nor unresolved results.

## Classification rules

- **Reviewed behavior-changing divergence detected by timeout:** the mutation removes loop progress and repeated isolated runs are deterministically terminated by pytest-timeout.
- **Equivalent:** the diff has the same observable supported behavior, including SQL keyword or identifier case, falsey sentinels used only as booleans, or arguments ignored by the fixed Django base implementation.
- **Exception/message-only non-contractual:** only diagnostic wording or a non-contractual exception payload changes; exception type and supported state behavior remain unchanged.
- **Typing/annotation-only:** the mutation changes runtime-erased typing metadata such as `typing.cast()` or a default-only annotation value.
- **Unreachable under fixed contract:** the changed branch requires an input, driver state, or Django shape excluded by the backend's fixed Django 6 and embedded-pyturso contract.

## Module and function summary

| Module/function | Category | Count |
| --- | --- | ---: |
| `django_pyturso.base.DatabaseWrapper._check_foreign_key` | Equivalent | 2 |
| `django_pyturso.base.DatabaseWrapper._check_foreign_key` | Exception/message-only non-contractual | 1 |
| `django_pyturso.base.DatabaseWrapper._check_foreign_key` | Unreachable under fixed contract | 6 |
| `django_pyturso.base.DatabaseWrapper._ensure_transaction` | Exception/message-only non-contractual | 2 |
| `django_pyturso.base.DatabaseWrapper._foreign_keys_by_id` | Equivalent | 1 |
| `django_pyturso.base.DatabaseWrapper._foreign_keys_by_id` | Unreachable under fixed contract | 1 |
| `django_pyturso.base.DatabaseWrapper._parse_database_version` | Exception/message-only non-contractual | 5 |
| `django_pyturso.base.DatabaseWrapper._read_foreign_key_state` | Equivalent | 1 |
| `django_pyturso.base.DatabaseWrapper._read_foreign_key_state` | Exception/message-only non-contractual | 2 |
| `django_pyturso.base.DatabaseWrapper._resolve_foreign_key_targets` | Exception/message-only non-contractual | 6 |
| `django_pyturso.base.DatabaseWrapper._resolve_foreign_key_targets` | Unreachable under fixed contract | 4 |
| `django_pyturso.base.DatabaseWrapper._rollback_active_transaction_for_close` | Exception/message-only non-contractual | 2 |
| `django_pyturso.base.DatabaseWrapper._set_autocommit` | Exception/message-only non-contractual | 4 |
| `django_pyturso.base.DatabaseWrapper._source_identity` | Equivalent | 2 |
| `django_pyturso.base.DatabaseWrapper.disable_constraint_checking` | Equivalent | 1 |
| `django_pyturso.base.DatabaseWrapper.disable_constraint_checking` | Exception/message-only non-contractual | 2 |
| `django_pyturso.base.DatabaseWrapper.enable_constraint_checking` | Equivalent | 2 |
| `django_pyturso.base.DatabaseWrapper.enable_constraint_checking` | Exception/message-only non-contractual | 2 |
| `django_pyturso.base.DatabaseWrapper.get_connection_params` | Equivalent | 1 |
| `django_pyturso.base.DatabaseWrapper.get_connection_params` | Exception/message-only non-contractual | 23 |
| `django_pyturso.base.DatabaseWrapper.inc_thread_sharing` | Exception/message-only non-contractual | 5 |
| `django_pyturso.operations.DatabaseOperations._quote_params_for_last_executed_query` | Equivalent | 3 |
| `django_pyturso.operations.DatabaseOperations._references_graph_for_table` | Reviewed behavior-changing divergence detected by timeout | 2 |
| `django_pyturso.operations.DatabaseOperations._references_graph_for_table` | Equivalent | 6 |
| `django_pyturso.operations.DatabaseOperations._validate_timezone` | Exception/message-only non-contractual | 4 |
| `django_pyturso.operations.DatabaseOperations.adapt_datetimefield_value` | Exception/message-only non-contractual | 1 |
| `django_pyturso.operations.DatabaseOperations.adapt_timefield_value` | Exception/message-only non-contractual | 2 |
| `django_pyturso.operations.DatabaseOperations.bulk_batch_size` | Typing/annotation-only | 1 |
| `django_pyturso.operations.DatabaseOperations.check_expression_support` | Equivalent | 2 |
| `django_pyturso.operations.DatabaseOperations.check_expression_support` | Exception/message-only non-contractual | 2 |
| `django_pyturso.operations.DatabaseOperations.check_expression_support` | Unreachable under fixed contract | 1 |
| `django_pyturso.operations.DatabaseOperations.combine_duration_expression` | Exception/message-only non-contractual | 1 |
| `django_pyturso.operations.DatabaseOperations.datetime_trunc_sql` | Equivalent | 3 |
| `django_pyturso.operations.DatabaseOperations.get_db_converters` | Unreachable under fixed contract | 1 |
| `django_pyturso.operations.DatabaseOperations.get_decimalfield_converter` | Equivalent | 1 |
| `django_pyturso.operations.DatabaseOperations.insert_statement` | Equivalent | 1 |
| `django_pyturso.operations.DatabaseOperations.last_executed_query` | Unreachable under fixed contract | 3 |
| `django_pyturso.operations.DatabaseOperations.on_conflict_suffix_sql` | Unreachable under fixed contract | 4 |
| `django_pyturso.operations.DatabaseOperations.subtract_temporals` | Exception/message-only non-contractual | 1 |
| `django_pyturso.schema.DatabaseSchemaEditor.__enter__` | Equivalent | 1 |
| `django_pyturso.schema.DatabaseSchemaEditor.__enter__` | Exception/message-only non-contractual | 4 |
| `django_pyturso.schema.DatabaseSchemaEditor.__exit__` | Equivalent | 1 |
| `django_pyturso.schema.DatabaseSchemaEditor._alter_field` | Equivalent | 1 |
| `django_pyturso.schema.DatabaseSchemaEditor._foreign_key_state` | Equivalent | 1 |
| `django_pyturso.schema.DatabaseSchemaEditor._foreign_key_state` | Exception/message-only non-contractual | 2 |
| `django_pyturso.schema.DatabaseSchemaEditor._remake_table` | Equivalent | 7 |
| `django_pyturso.schema.DatabaseSchemaEditor._remake_table` | Unreachable under fixed contract | 7 |
| `django_pyturso.schema.DatabaseSchemaEditor._set_foreign_key_state` | Exception/message-only non-contractual | 5 |
| `django_pyturso.schema.DatabaseSchemaEditor.quote_value` | Exception/message-only non-contractual | 1 |
| `django_pyturso.schema.DatabaseSchemaEditor.remove_field` | Typing/annotation-only | 1 |

## Representative reviewed diffs

- Typing-only: `bulk_batch_size__mutmut_5` changes `cast(int, value)` to `cast(None, value)`; `cast()` returns the same value at runtime.
- Equivalent: SQLite accepts the lowercase `pragma foreign_keys` spelling exactly as it accepts `PRAGMA foreign_keys`.
- Message-only: connection-validation mutations change exception text or payload while retaining the same exception type and rejection behavior.
- Unreachable: `getattr(new_field, "primary_key", False)` default mutations cannot affect supported Django fields, which always expose `primary_key`.
- Timeout-detected: the two reference-graph mutations remove stack or seen-set progress and are deterministically caught by pytest-timeout.

## Exhaustive current non-killed ledger

### Reviewed behavior-changing divergence detected by timeout (2)

- 023 `django_pyturso.operations.xǁDatabaseOperationsǁ_references_graph_for_table__mutmut_29` — `current = pending.pop()` → `current = None`
- 024 `django_pyturso.operations.xǁDatabaseOperationsǁ_references_graph_for_table__mutmut_32` — `seen.add(current)` → `seen.add(None)`

### Equivalent (37)

- 002 `django_pyturso.operations.xǁDatabaseOperationsǁcheck_expression_support__mutmut_6` — `and getattr(expression, "distinct", False)` → `and getattr(expression, "distinct", None)`
- 003 `django_pyturso.operations.xǁDatabaseOperationsǁcheck_expression_support__mutmut_9` — `and getattr(expression, "distinct", False)` → `and getattr(expression, "distinct", )`
- 011 `django_pyturso.operations.xǁDatabaseOperationsǁdatetime_trunc_sql__mutmut_11` — `date_sql, result_params = self.date_trunc_sql("week", sql, params, tzname)` → `date_sql, result_params = self.date_trunc_sql("week", sql, params, None)`
- 012 `django_pyturso.operations.xǁDatabaseOperationsǁdatetime_trunc_sql__mutmut_15` — `date_sql, result_params = self.date_trunc_sql("week", sql, params, tzname)` → `date_sql, result_params = self.date_trunc_sql("week", sql, params, )`
- 013 `django_pyturso.operations.xǁDatabaseOperationsǁdatetime_trunc_sql__mutmut_17` — `date_sql, result_params = self.date_trunc_sql("week", sql, params, tzname)` → `date_sql, result_params = self.date_trunc_sql("WEEK", sql, params, tzname)`
- 014 `django_pyturso.operations.xǁDatabaseOperationsǁ_quote_params_for_last_executed_query__mutmut_2` — `batch_size = 999` → `batch_size = 1000`
- 015 `django_pyturso.operations.xǁDatabaseOperationsǁ_quote_params_for_last_executed_query__mutmut_18` — `sql = "SELECT " + ", ".join(["QUOTE(?)"] * len(params))` → `sql = "select " + ", ".join(["QUOTE(?)"] * len(params))`
- 016 `django_pyturso.operations.xǁDatabaseOperationsǁ_quote_params_for_last_executed_query__mutmut_23` — `sql = "SELECT " + ", ".join(["QUOTE(?)"] * len(params))` → `sql = "SELECT " + ", ".join(["quote(?)"] * len(params))`
- 020 `django_pyturso.operations.xǁDatabaseOperationsǁ_references_graph_for_table__mutmut_3` — `"SELECT name FROM sqlite_master "` → `"select name from sqlite_master "`
- 021 `django_pyturso.operations.xǁDatabaseOperationsǁ_references_graph_for_table__mutmut_6` — `"WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"` → `"where type = 'table' and name not like 'sqlite_%'"`
- 022 `django_pyturso.operations.xǁDatabaseOperationsǁ_references_graph_for_table__mutmut_15` — `cursor.execute("PRAGMA foreign_key_list(%s)" % self.quote_name(candidate))` → `cursor.execute("pragma foreign_key_list(%s)" % self.quote_name(candidate))`
- 025 `django_pyturso.operations.xǁDatabaseOperationsǁ_references_graph_for_table__mutmut_36` — `pending.extend(sorted(referencing.get(current, ()), reverse=True))` → `pending.extend(sorted(referencing.get(current, ()), reverse=None))`
- 026 `django_pyturso.operations.xǁDatabaseOperationsǁ_references_graph_for_table__mutmut_38` — `pending.extend(sorted(referencing.get(current, ()), reverse=True))` → `pending.extend(sorted(referencing.get(current, ()), ))`
- 027 `django_pyturso.operations.xǁDatabaseOperationsǁ_references_graph_for_table__mutmut_43` — `pending.extend(sorted(referencing.get(current, ()), reverse=True))` → `pending.extend(sorted(referencing.get(current, ()), reverse=False))`
- 032 `django_pyturso.operations.xǁDatabaseOperationsǁget_decimalfield_converter__mutmut_22` — `quantize_value = decimal.Decimal(1).scaleb(-decimal_places)` → `quantize_value = decimal.Decimal(2).scaleb(-decimal_places)`
- 035 `django_pyturso.operations.xǁDatabaseOperationsǁinsert_statement__mutmut_4` — `else super().insert_statement(on_conflict)` → `else super().insert_statement(None)`
- 060 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_72` — `raw_mode = options.get("transaction_mode", "DEFERRED")` → `raw_mode = options.get("transaction_mode", "deferred")`
- 075 `django_pyturso.base.xǁDatabaseWrapperǁ_read_foreign_key_state__mutmut_3` — `cursor.execute("PRAGMA foreign_keys")` → `cursor.execute("pragma foreign_keys")`
- 078 `django_pyturso.base.xǁDatabaseWrapperǁdisable_constraint_checking__mutmut_6` — `cursor.execute("PRAGMA foreign_keys = OFF")` → `cursor.execute("pragma foreign_keys = off")`
- 081 `django_pyturso.base.xǁDatabaseWrapperǁenable_constraint_checking__mutmut_2` — `if self._read_foreign_key_state() == 1:` → `if self._read_foreign_key_state() == 2:`
- 082 `django_pyturso.base.xǁDatabaseWrapperǁenable_constraint_checking__mutmut_5` — `cursor.execute("PRAGMA foreign_keys = ON")` → `cursor.execute("pragma foreign_keys = on")`
- 085 `django_pyturso.base.xǁDatabaseWrapperǁ_foreign_keys_by_id__mutmut_4` — `cursor.execute("PRAGMA foreign_key_list(%s)" % self.ops.quote_name(table_name))` → `cursor.execute("pragma foreign_key_list(%s)" % self.ops.quote_name(table_name))`
- 097 `django_pyturso.base.xǁDatabaseWrapperǁ_source_identity__mutmut_21` — `for candidate in ("rowid", "_rowid_", "oid")` → `for candidate in ("rowid", "_ROWID_", "oid")`
- 098 `django_pyturso.base.xǁDatabaseWrapperǁ_source_identity__mutmut_23` — `for candidate in ("rowid", "_rowid_", "oid")` → `for candidate in ("rowid", "_rowid_", "OID")`
- 099 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_37` — `nonnull_sql = " AND ".join(f"{column} IS NOT NULL" for column in source_sql)` → `nonnull_sql = " and ".join(f"{column} IS NOT NULL" for column in source_sql)`
- 100 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_41` — `join_sql = " AND ".join(` → `join_sql = " and ".join(`
- 115 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_foreign_key_state__mutmut_3` — `cursor.execute("PRAGMA foreign_keys")` → `cursor.execute("pragma foreign_keys")`
- 127 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ__enter____mutmut_9` — `self._set_foreign_key_state(False)` → `self._set_foreign_key_state(None)`
- 128 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ__exit____mutmut_2` — `check_traceback: TracebackType | None = None` → `check_traceback: TracebackType | None = ""`
- 130 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_17` — `if getattr(create_field, "primary_key", False) or any(` → `if getattr(create_field, "primary_key", None) or any(`
- 138 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_119` — `meta = type("Meta", (), meta_contents)` → `meta = type("XXMetaXX", (), meta_contents)`
- 139 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_120` — `meta = type("Meta", (), meta_contents)` → `meta = type("meta", (), meta_contents)`
- 140 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_121` — `meta = type("Meta", (), meta_contents)` → `meta = type("META", (), meta_contents)`
- 141 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_162` — `meta = type("Meta", (), meta_contents)` → `meta = type("XXMetaXX", (), meta_contents)`
- 142 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_163` — `meta = type("Meta", (), meta_contents)` → `meta = type("meta", (), meta_contents)`
- 143 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_164` — `meta = type("Meta", (), meta_contents)` → `meta = type("META", (), meta_contents)`
- 145 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_alter_field__mutmut_1` — `strict: bool = False,` → `strict: bool = True,`

### Exception/message-only non-contractual (77)

- 005 `django_pyturso.operations.xǁDatabaseOperationsǁcheck_expression_support__mutmut_16` — `"Turso doesn't support DISTINCT on aggregates with multiple arguments."` → `"XXTurso doesn't support DISTINCT on aggregates with multiple arguments.XX"`
- 006 `django_pyturso.operations.xǁDatabaseOperationsǁcheck_expression_support__mutmut_18` — `"Turso doesn't support DISTINCT on aggregates with multiple arguments."` → `"TURSO DOESN'T SUPPORT DISTINCT ON AGGREGATES WITH MULTIPLE ARGUMENTS."`
- 007 `django_pyturso.operations.xǁDatabaseOperationsǁ_validate_timezone__mutmut_5` — `"django-pyturso supports database-side temporal operations only "` → `"XXdjango-pyturso supports database-side temporal operations only XX"`
- 008 `django_pyturso.operations.xǁDatabaseOperationsǁ_validate_timezone__mutmut_6` — `"django-pyturso supports database-side temporal operations only "` → `"DJANGO-PYTURSO SUPPORTS DATABASE-SIDE TEMPORAL OPERATIONS ONLY "`
- 009 `django_pyturso.operations.xǁDatabaseOperationsǁ_validate_timezone__mutmut_7` — `"without timezone conversion or in UTC."` → `"XXwithout timezone conversion or in UTC.XX"`
- 010 `django_pyturso.operations.xǁDatabaseOperationsǁ_validate_timezone__mutmut_8` — `"without timezone conversion or in UTC."` → `"without timezone conversion or in utc."`
- 028 `django_pyturso.operations.xǁDatabaseOperationsǁadapt_datetimefield_value__mutmut_6` — `"Turso backend does not support timezone-aware datetimes when USE_TZ is False."` → `"XXTurso backend does not support timezone-aware datetimes when USE_TZ is False.XX"`
- 029 `django_pyturso.operations.xǁDatabaseOperationsǁadapt_timefield_value__mutmut_4` — `raise ValueError("Turso backend does not support timezone-aware times.")` → `raise ValueError("XXTurso backend does not support timezone-aware times.XX")`
- 030 `django_pyturso.operations.xǁDatabaseOperationsǁadapt_timefield_value__mutmut_5` — `raise ValueError("Turso backend does not support timezone-aware times.")` → `raise ValueError("turso backend does not support timezone-aware times.")`
- 033 `django_pyturso.operations.xǁDatabaseOperationsǁcombine_duration_expression__mutmut_8` — `"Duration arithmetic is disabled until the full Turso precision matrix passes."` → `"XXDuration arithmetic is disabled until the full Turso precision matrix passes.XX"`
- 034 `django_pyturso.operations.xǁDatabaseOperationsǁsubtract_temporals__mutmut_2` — `"Temporal subtraction is disabled until the full Turso precision matrix passes."` → `"XXTemporal subtraction is disabled until the full Turso precision matrix passes.XX"`
- 040 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_6` — `"settings.DATABASES is improperly configured. Please supply NAME."` → `None`
- 041 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_7` — `"settings.DATABASES is improperly configured. Please supply NAME."` → `"XXsettings.DATABASES is improperly configured. Please supply NAME.XX"`
- 042 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_8` — `"settings.DATABASES is improperly configured. Please supply NAME."` → `"settings.databases is improperly configured. please supply name."`
- 043 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_9` — `"settings.DATABASES is improperly configured. Please supply NAME."` → `"SETTINGS.DATABASES IS IMPROPERLY CONFIGURED. PLEASE SUPPLY NAME."`
- 044 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_12` — `raise ImproperlyConfigured("Database NAME must be a local filesystem path.") from exc` → `raise ImproperlyConfigured(None) from exc`
- 045 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_13` — `raise ImproperlyConfigured("Database NAME must be a local filesystem path.") from exc` → `raise ImproperlyConfigured("XXDatabase NAME must be a local filesystem path.XX") from exc`
- 046 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_14` — `raise ImproperlyConfigured("Database NAME must be a local filesystem path.") from exc` → `raise ImproperlyConfigured("database name must be a local filesystem path.") from exc`
- 047 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_15` — `raise ImproperlyConfigured("Database NAME must be a local filesystem path.") from exc` → `raise ImproperlyConfigured("DATABASE NAME MUST BE A LOCAL FILESYSTEM PATH.") from exc`
- 048 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_19` — `raise ImproperlyConfigured("Database NAME must be a nonempty local path.")` → `raise ImproperlyConfigured(None)`
- 049 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_20` — `raise ImproperlyConfigured("Database NAME must be a nonempty local path.")` → `raise ImproperlyConfigured("XXDatabase NAME must be a nonempty local path.XX")`
- 050 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_21` — `raise ImproperlyConfigured("Database NAME must be a nonempty local path.")` → `raise ImproperlyConfigured("database name must be a nonempty local path.")`
- 051 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_22` — `raise ImproperlyConfigured("Database NAME must be a nonempty local path.")` → `raise ImproperlyConfigured("DATABASE NAME MUST BE A NONEMPTY LOCAL PATH.")`
- 052 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_34` — `"django-pyturso accepts local paths and exactly ':memory:', not URLs or file URIs."` → `None`
- 053 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_35` — `"django-pyturso accepts local paths and exactly ':memory:', not URLs or file URIs."` → `"XXdjango-pyturso accepts local paths and exactly ':memory:', not URLs or file URIs.XX"`
- 054 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_36` — `"django-pyturso accepts local paths and exactly ':memory:', not URLs or file URIs."` → `"django-pyturso accepts local paths and exactly ':memory:', not urls or file uris."`
- 055 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_37` — `"django-pyturso accepts local paths and exactly ':memory:', not URLs or file URIs."` → `"DJANGO-PYTURSO ACCEPTS LOCAL PATHS AND EXACTLY ':MEMORY:', NOT URLS OR FILE URIS."`
- 056 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_47` — `f"django-pyturso doesn't accept the {key} database setting."` → `None`
- 057 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_59` — `names = ", ".join(sorted(unknown))` → `names = None`
- 058 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_61` — `names = ", ".join(sorted(unknown))` → `names = "XX, XX".join(sorted(unknown))`
- 059 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_63` — `raise ImproperlyConfigured(f"Unsupported django-pyturso OPTIONS: {names}.")` → `raise ImproperlyConfigured(None)`
- 061 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_77` — `allowed = ", ".join(sorted(self.transaction_modes))` → `allowed = None`
- 062 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_79` — `allowed = ", ".join(sorted(self.transaction_modes))` → `allowed = "XX, XX".join(sorted(self.transaction_modes))`
- 063 `django_pyturso.base.xǁDatabaseWrapperǁget_connection_params__mutmut_81` — `raise ImproperlyConfigured(f"transaction_mode must be one of: {allowed}.")` → `raise ImproperlyConfigured(None)`
- 064 `django_pyturso.base.xǁDatabaseWrapperǁ_parse_database_version__mutmut_2` — `raise DatabaseError("Turso returned a non-text engine version.")` → `raise DatabaseError(None)`
- 065 `django_pyturso.base.xǁDatabaseWrapperǁ_parse_database_version__mutmut_3` — `raise DatabaseError("Turso returned a non-text engine version.")` → `raise DatabaseError("XXTurso returned a non-text engine version.XX")`
- 066 `django_pyturso.base.xǁDatabaseWrapperǁ_parse_database_version__mutmut_4` — `raise DatabaseError("Turso returned a non-text engine version.")` → `raise DatabaseError("turso returned a non-text engine version.")`
- 067 `django_pyturso.base.xǁDatabaseWrapperǁ_parse_database_version__mutmut_5` — `raise DatabaseError("Turso returned a non-text engine version.")` → `raise DatabaseError("TURSO RETURNED A NON-TEXT ENGINE VERSION.")`
- 068 `django_pyturso.base.xǁDatabaseWrapperǁ_parse_database_version__mutmut_14` — `raise DatabaseError(f"Invalid Turso engine version: {raw_version!r}.")` → `raise DatabaseError(None)`
- 069 `django_pyturso.base.xǁDatabaseWrapperǁ_ensure_transaction__mutmut_6` — `"Django is inside atomic() but the Turso transaction is no longer active."` → `"XXDjango is inside atomic() but the Turso transaction is no longer active.XX"`
- 070 `django_pyturso.base.xǁDatabaseWrapperǁ_ensure_transaction__mutmut_7` — `"Django is inside atomic() but the Turso transaction is no longer active."` → `"django is inside atomic() but the turso transaction is no longer active."`
- 071 `django_pyturso.base.xǁDatabaseWrapperǁ_set_autocommit__mutmut_1` — `"Commit or roll back before enabling autocommit."` → `None`
- 072 `django_pyturso.base.xǁDatabaseWrapperǁ_set_autocommit__mutmut_2` — `"Commit or roll back before enabling autocommit."` → `"XXCommit or roll back before enabling autocommit.XX"`
- 073 `django_pyturso.base.xǁDatabaseWrapperǁ_set_autocommit__mutmut_3` — `"Commit or roll back before enabling autocommit."` → `"commit or roll back before enabling autocommit."`
- 074 `django_pyturso.base.xǁDatabaseWrapperǁ_set_autocommit__mutmut_4` — `"Commit or roll back before enabling autocommit."` → `"COMMIT OR ROLL BACK BEFORE ENABLING AUTOCOMMIT."`
- 076 `django_pyturso.base.xǁDatabaseWrapperǁ_read_foreign_key_state__mutmut_13` — `raise DatabaseError("Turso did not report a valid foreign-key state.")` → `raise DatabaseError("XXTurso did not report a valid foreign-key state.XX")`
- 077 `django_pyturso.base.xǁDatabaseWrapperǁ_read_foreign_key_state__mutmut_14` — `raise DatabaseError("Turso did not report a valid foreign-key state.")` → `raise DatabaseError("turso did not report a valid foreign-key state.")`
- 079 `django_pyturso.base.xǁDatabaseWrapperǁdisable_constraint_checking__mutmut_11` — `"Turso did not disable foreign-key checks after PRAGMA readback."` → `"XXTurso did not disable foreign-key checks after PRAGMA readback.XX"`
- 080 `django_pyturso.base.xǁDatabaseWrapperǁdisable_constraint_checking__mutmut_12` — `"Turso did not disable foreign-key checks after PRAGMA readback."` → `"turso did not disable foreign-key checks after pragma readback."`
- 083 `django_pyturso.base.xǁDatabaseWrapperǁenable_constraint_checking__mutmut_10` — `"Turso did not enable foreign-key checks after PRAGMA readback."` → `"XXTurso did not enable foreign-key checks after PRAGMA readback.XX"`
- 084 `django_pyturso.base.xǁDatabaseWrapperǁenable_constraint_checking__mutmut_11` — `"Turso did not enable foreign-key checks after PRAGMA readback."` → `"turso did not enable foreign-key checks after pragma readback."`
- 087 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_14` — `source_columns = tuple(str(row[3]) for row in rows)` → `source_columns = None`
- 088 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_16` — `source_columns = tuple(str(row[3]) for row in rows)` → `source_columns = tuple(str(None) for row in rows)`
- 089 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_17` — `source_columns = tuple(str(row[3]) for row in rows)` → `source_columns = tuple(str(row[4]) for row in rows)`
- 090 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_19` — `"Cannot resolve omitted foreign-key target columns for "` → `"XXCannot resolve omitted foreign-key target columns for XX"`
- 091 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_20` — `"Cannot resolve omitted foreign-key target columns for "` → `"cannot resolve omitted foreign-key target columns for "`
- 092 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_21` — `"Cannot resolve omitted foreign-key target columns for "` → `"CANNOT RESOLVE OMITTED FOREIGN-KEY TARGET COLUMNS FOR "`
- 104 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_63` — `identity = ", ".join(` → `identity = "XX, XX".join(`
- 108 `django_pyturso.base.xǁDatabaseWrapperǁ_rollback_active_transaction_for_close__mutmut_4` — `raise DatabaseError("Turso remained in a transaction after rollback.")` → `raise DatabaseError("XXTurso remained in a transaction after rollback.XX")`
- 109 `django_pyturso.base.xǁDatabaseWrapperǁ_rollback_active_transaction_for_close__mutmut_5` — `raise DatabaseError("Turso remained in a transaction after rollback.")` → `raise DatabaseError("turso remained in a transaction after rollback.")`
- 110 `django_pyturso.base.xǁDatabaseWrapperǁinc_thread_sharing__mutmut_2` — `"In-memory django-pyturso databases cannot be shared across threads; "` → `"XXIn-memory django-pyturso databases cannot be shared across threads; XX"`
- 111 `django_pyturso.base.xǁDatabaseWrapperǁinc_thread_sharing__mutmut_3` — `"In-memory django-pyturso databases cannot be shared across threads; "` → `"in-memory django-pyturso databases cannot be shared across threads; "`
- 112 `django_pyturso.base.xǁDatabaseWrapperǁinc_thread_sharing__mutmut_5` — `"use a file-backed test database for LiveServerTestCase."` → `"XXuse a file-backed test database for LiveServerTestCase.XX"`
- 113 `django_pyturso.base.xǁDatabaseWrapperǁinc_thread_sharing__mutmut_6` — `"use a file-backed test database for LiveServerTestCase."` → `"use a file-backed test database for liveservertestcase."`
- 114 `django_pyturso.base.xǁDatabaseWrapperǁinc_thread_sharing__mutmut_7` — `"use a file-backed test database for LiveServerTestCase."` → `"USE A FILE-BACKED TEST DATABASE FOR LIVESERVERTESTCASE."`
- 116 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_foreign_key_state__mutmut_13` — `raise NotSupportedError("Turso did not report a valid foreign-key state.")` → `raise NotSupportedError("XXTurso did not report a valid foreign-key state.XX")`
- 117 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_foreign_key_state__mutmut_14` — `raise NotSupportedError("Turso did not report a valid foreign-key state.")` → `raise NotSupportedError("turso did not report a valid foreign-key state.")`
- 118 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_set_foreign_key_state__mutmut_11` — `state = "enable" if enabled else "disable"` → `state = "XXenableXX" if enabled else "disable"`
- 119 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_set_foreign_key_state__mutmut_13` — `state = "enable" if enabled else "disable"` → `state = "enable" if enabled else "XXdisableXX"`
- 120 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_set_foreign_key_state__mutmut_16` — `"Enter the schema editor outside transaction.atomic()."` → `"XXEnter the schema editor outside transaction.atomic().XX"`
- 121 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_set_foreign_key_state__mutmut_17` — `"Enter the schema editor outside transaction.atomic()."` → `"enter the schema editor outside transaction.atomic()."`
- 122 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_set_foreign_key_state__mutmut_18` — `"Enter the schema editor outside transaction.atomic()."` → `"ENTER THE SCHEMA EDITOR OUTSIDE TRANSACTION.ATOMIC()."`
- 123 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ__enter____mutmut_4` — `"Turso schema editing must begin outside transaction.atomic() "` → `"XXTurso schema editing must begin outside transaction.atomic() XX"`
- 124 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ__enter____mutmut_5` — `"Turso schema editing must begin outside transaction.atomic() "` → `"turso schema editing must begin outside transaction.atomic() "`
- 125 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ__enter____mutmut_7` — `"so foreign-key checks can be disabled and verified first."` → `"XXso foreign-key checks can be disabled and verified first.XX"`
- 126 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ__enter____mutmut_8` — `"so foreign-key checks can be disabled and verified first."` → `"SO FOREIGN-KEY CHECKS CAN BE DISABLED AND VERIFIED FIRST."`
- 129 `django_pyturso.schema.xǁDatabaseSchemaEditorǁquote_value__mutmut_11` — `raise ValueError("Non-finite floats cannot be used as Turso schema defaults.")` → `raise ValueError("XXNon-finite floats cannot be used as Turso schema defaults.XX")`

### Typing/annotation-only (2)

- 001 `django_pyturso.operations.xǁDatabaseOperationsǁbulk_batch_size__mutmut_5` — `max_query_params = cast(int, self.connection.features.max_query_params)` → `max_query_params = cast(None, self.connection.features.max_query_params)`
- 144 `django_pyturso.schema.xǁDatabaseSchemaEditorǁremove_field__mutmut_6` — `cast(DatabaseFeatures, self.connection.features).can_alter_table_drop_column` → `cast(None, self.connection.features).can_alter_table_drop_column`

### Unreachable under fixed contract (27)

- 004 `django_pyturso.operations.xǁDatabaseOperationsǁcheck_expression_support__mutmut_12` — `and getattr(expression, "distinct", False)` → `and getattr(expression, "distinct", True)`
- 017 `django_pyturso.operations.xǁDatabaseOperationsǁlast_executed_query__mutmut_11` — `quoted = dict(zip(params, values, strict=True))` → `quoted = dict(zip(params, values, strict=None))`
- 018 `django_pyturso.operations.xǁDatabaseOperationsǁlast_executed_query__mutmut_14` — `quoted = dict(zip(params, values, strict=True))` → `quoted = dict(zip(params, values, ))`
- 019 `django_pyturso.operations.xǁDatabaseOperationsǁlast_executed_query__mutmut_15` — `quoted = dict(zip(params, values, strict=True))` → `quoted = dict(zip(params, values, strict=False))`
- 031 `django_pyturso.operations.xǁDatabaseOperationsǁget_db_converters__mutmut_2` — `converters = super().get_db_converters(expression)` → `converters = super().get_db_converters(None)`
- 036 `django_pyturso.operations.xǁDatabaseOperationsǁon_conflict_suffix_sql__mutmut_16` — `return super().on_conflict_suffix_sql(fields, on_conflict, update_fields, unique_fields)` → `return super().on_conflict_suffix_sql(None, on_conflict, update_fields, unique_fields)`
- 037 `django_pyturso.operations.xǁDatabaseOperationsǁon_conflict_suffix_sql__mutmut_17` — `return super().on_conflict_suffix_sql(fields, on_conflict, update_fields, unique_fields)` → `return super().on_conflict_suffix_sql(fields, None, update_fields, unique_fields)`
- 038 `django_pyturso.operations.xǁDatabaseOperationsǁon_conflict_suffix_sql__mutmut_18` — `return super().on_conflict_suffix_sql(fields, on_conflict, update_fields, unique_fields)` → `return super().on_conflict_suffix_sql(fields, on_conflict, None, unique_fields)`
- 039 `django_pyturso.operations.xǁDatabaseOperationsǁon_conflict_suffix_sql__mutmut_19` — `return super().on_conflict_suffix_sql(fields, on_conflict, update_fields, unique_fields)` → `return super().on_conflict_suffix_sql(fields, on_conflict, update_fields, None)`
- 086 `django_pyturso.base.xǁDatabaseWrapperǁ_foreign_keys_by_id__mutmut_14` — `rows.sort(key=lambda row: int(row[1]))` → `rows.sort(key=None)`
- 093 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_26` — `for row, declared_column in zip(rows, declared_columns, strict=True):` → `for row, declared_column in zip(rows, declared_columns, strict=None):`
- 094 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_29` — `for row, declared_column in zip(rows, declared_columns, strict=True):` → `for row, declared_column in zip(rows, declared_columns, ):`
- 095 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_30` — `for row, declared_column in zip(rows, declared_columns, strict=True):` → `for row, declared_column in zip(rows, declared_columns, strict=False):`
- 096 `django_pyturso.base.xǁDatabaseWrapperǁ_resolve_foreign_key_targets__mutmut_37` — `str(declared_column)` → `str(None)`
- 101 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_44` — `f"{target} = {source}" for source, target in zip(source_sql, target_sql, strict=True)` → `f"{target} = {source}" for source, target in zip(source_sql, target_sql, strict=None)`
- 102 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_47` — `f"{target} = {source}" for source, target in zip(source_sql, target_sql, strict=True)` → `f"{target} = {source}" for source, target in zip(source_sql, target_sql, )`
- 103 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_48` — `f"{target} = {source}" for source, target in zip(source_sql, target_sql, strict=True)` → `f"{target} = {source}" for source, target in zip(source_sql, target_sql, strict=False)`
- 105 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_66` — `f"{name}={value!r}" for name, value in zip(identity_names, identity_values, strict=True)` → `f"{name}={value!r}" for name, value in zip(identity_names, identity_values, strict=None)`
- 106 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_69` — `f"{name}={value!r}" for name, value in zip(identity_names, identity_values, strict=True)` → `f"{name}={value!r}" for name, value in zip(identity_names, identity_values, )`
- 107 `django_pyturso.base.xǁDatabaseWrapperǁ_check_foreign_key__mutmut_70` — `f"{name}={value!r}" for name, value in zip(identity_names, identity_values, strict=True)` → `f"{name}={value!r}" for name, value in zip(identity_names, identity_values, strict=False)`
- 131 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_27` — `getattr(new_field, "primary_key", False) for _, new_field in alter_fields` → `getattr(new_field, "primary_key", None) for _, new_field in alter_fields`
- 132 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_30` — `getattr(new_field, "primary_key", False) for _, new_field in alter_fields` → `getattr(new_field, "primary_key", ) for _, new_field in alter_fields`
- 133 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_33` — `getattr(new_field, "primary_key", False) for _, new_field in alter_fields` → `getattr(new_field, "primary_key", True) for _, new_field in alter_fields`
- 134 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_54` — `body.pop(old_field.name, None)` → `body.pop(old_field.name, )`
- 135 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_57` — `mapping.pop(old_field.column, None)` → `mapping.pop(old_field.column, )`
- 136 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_60` — `continue` → `break`
- 137 `django_pyturso.schema.xǁDatabaseSchemaEditorǁ_remake_table__mutmut_82` — `mapping.pop(delete_field.column, None)` → `mapping.pop(delete_field.column, )`
