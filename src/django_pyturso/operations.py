"""SQL generation and value conversion for embedded Turso."""

import datetime
import decimal
import uuid
from collections.abc import Iterable, Mapping, Sequence
from itertools import chain
from typing import Any, cast

from django.conf import settings
from django.db import DatabaseError, NotSupportedError, models
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.models.aggregates import AnyValue, StdDev, Variance
from django.db.models.constants import OnConflict
from django.db.models.expressions import Col, Window
from django.db.models.functions import (
    MD5,
    SHA1,
    SHA224,
    SHA256,
    SHA384,
    SHA512,
    Cot,
    LPad,
    Random,
    Repeat,
    Reverse,
    RPad,
)
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time

# Selected conversion and conflict methods follow Django 6.0.7's SQLite dialect.

_UNSUPPORTED_EXPRESSION_TYPES = (
    AnyValue,
    Cot,
    LPad,
    MD5,
    RPad,
    Random,
    Repeat,
    Reverse,
    SHA1,
    SHA224,
    SHA256,
    SHA384,
    SHA512,
    StdDev,
    Variance,
    Window,
)


class DatabaseOperations(BaseDatabaseOperations):
    """Implement the SQLite SQL dialect exposed by the Turso engine."""

    cast_char_field_without_max_length = "text"
    cast_data_types = {"DateField": "TEXT", "DateTimeField": "TEXT"}
    explain_prefix = "EXPLAIN QUERY PLAN"
    jsonfield_datatype_values = frozenset(["null", "false", "true"])

    def bulk_batch_size(self, fields: Iterable[models.Field[Any, Any]], objs: Sequence[Any]) -> int:
        flattened = list(
            chain.from_iterable(
                field.fields if isinstance(field, models.CompositePrimaryKey) else [field]
                for field in fields
            )
        )
        max_query_params = cast(int, self.connection.features.max_query_params)
        return max_query_params // len(flattened) if flattened else len(objs)

    def check_expression_support(self, expression: Any) -> None:
        if isinstance(expression, _UNSUPPORTED_EXPRESSION_TYPES):
            raise NotSupportedError(
                f"{expression.__class__.__name__} isn't supported by django-pyturso v1."
            )
        if (
            isinstance(expression, models.Aggregate)
            and getattr(expression, "distinct", False)
            and len(expression.source_expressions) > 1
        ):
            raise NotSupportedError(
                "Turso doesn't support DISTINCT on aggregates with multiple arguments."
            )

    @staticmethod
    def _validate_timezone(tzname: str | None) -> None:
        if tzname not in (None, "UTC"):
            raise NotSupportedError(
                "django-pyturso supports database-side temporal operations only "
                "without timezone conversion or in UTC."
            )

    @staticmethod
    def _extract_sql(lookup_type: str, sql: str) -> str:
        formats = {
            "year": "%Y",
            "iso_year": "%G",
            "month": "%m",
            "day": "%d",
            "week": "%V",
            "week_day": "%w",
            "iso_week_day": "%u",
            "hour": "%H",
            "minute": "%M",
            "second": "%S",
        }
        if lookup_type == "quarter":
            return f"((CAST(strftime('%%m', {sql}) AS INTEGER) + 2) / 3)"
        if lookup_type not in formats:
            raise NotSupportedError(f"Unsupported temporal extraction: {lookup_type}.")
        extracted = f"CAST(strftime('{formats[lookup_type]}', {sql}) AS INTEGER)"
        if lookup_type == "week_day":
            return f"({extracted} + 1)"
        return extracted

    def date_extract_sql(
        self, lookup_type: str, sql: str, params: Sequence[Any]
    ) -> tuple[str, tuple[Any, ...]]:
        return self._extract_sql(lookup_type.lower(), sql), tuple(params)

    def time_extract_sql(  # type: ignore[override]
        self, lookup_type: str, sql: str, params: Sequence[Any]
    ) -> tuple[str, tuple[Any, ...]]:
        return self._extract_sql(lookup_type.lower(), sql), tuple(params)

    def datetime_extract_sql(
        self, lookup_type: str, sql: str, params: Sequence[Any], tzname: str | None
    ) -> tuple[str, tuple[Any, ...]]:
        self._validate_timezone(tzname)
        return self._extract_sql(lookup_type.lower(), sql), tuple(params)

    def date_trunc_sql(
        self,
        lookup_type: str,
        sql: str,
        params: Sequence[Any],
        tzname: str | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        self._validate_timezone(tzname)
        lookup_type = lookup_type.lower()
        result_params = tuple(params)
        if lookup_type == "year":
            result = f"date({sql}, 'start of year')"
        elif lookup_type == "quarter":
            result = (
                f"printf('%%04d-%%02d-01', CAST(strftime('%%Y', {sql}) AS INTEGER), "
                f"((CAST(strftime('%%m', {sql}) AS INTEGER) - 1) / 3) * 3 + 1)"
            )
            result_params *= 2
        elif lookup_type == "month":
            result = f"date({sql}, 'start of month')"
        elif lookup_type == "week":
            result = f"date({sql}, '-' || (CAST(strftime('%%u', {sql}) AS INTEGER) - 1) || ' days')"
            result_params *= 2
        elif lookup_type == "day":
            result = f"date({sql})"
        else:
            raise NotSupportedError(f"Unsupported date truncation: {lookup_type}.")
        return result, result_params

    @staticmethod
    def _time_extension_input(sql: str, *, time_only: bool = False) -> str:
        if time_only:
            return f"time_parse('1970-01-01T' || {sql} || 'Z')"
        return f"time_parse(REPLACE({sql}, ' ', 'T') || 'Z')"

    @staticmethod
    def _format_time_extension(sql: str, *, time_only: bool = False) -> str:
        formatted = f"RTRIM(REPLACE(time_fmt_iso({sql}), 'T', ' '), 'Z')"
        return f"SUBSTR({formatted}, 12)" if time_only else formatted

    def datetime_trunc_sql(  # type: ignore[override]
        self, lookup_type: str, sql: str, params: Sequence[Any], tzname: str | None
    ) -> tuple[str, tuple[Any, ...]]:
        self._validate_timezone(tzname)
        lookup_type = lookup_type.lower()
        if lookup_type == "week":
            date_sql, result_params = self.date_trunc_sql("week", sql, params, tzname)
            return f"{date_sql} || ' 00:00:00'", result_params
        supported = {"year", "quarter", "month", "day", "hour", "minute", "second"}
        if lookup_type not in supported:
            raise NotSupportedError(f"Unsupported datetime truncation: {lookup_type}.")
        parsed = self._time_extension_input(sql)
        return self._format_time_extension(f"time_trunc({parsed}, '{lookup_type}')"), tuple(params)

    def time_trunc_sql(  # type: ignore[override]
        self,
        lookup_type: str,
        sql: str,
        params: Sequence[Any],
        tzname: str | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        self._validate_timezone(tzname)
        lookup_type = lookup_type.lower()
        if lookup_type not in {"hour", "minute", "second"}:
            raise NotSupportedError(f"Unsupported time truncation: {lookup_type}.")
        parsed = self._time_extension_input(sql, time_only=True)
        truncated = f"time_trunc({parsed}, '{lookup_type}')"
        return self._format_time_extension(truncated, time_only=True), tuple(params)

    def datetime_cast_date_sql(
        self, sql: str, params: Sequence[Any], tzname: str | None
    ) -> tuple[str, tuple[Any, ...]]:
        self._validate_timezone(tzname)
        return f"date({sql})", tuple(params)

    def datetime_cast_time_sql(
        self, sql: str, params: Sequence[Any], tzname: str | None
    ) -> tuple[str, tuple[Any, ...]]:
        self._validate_timezone(tzname)
        parsed = self._time_extension_input(sql)
        formatted = self._format_time_extension(parsed, time_only=True)
        return formatted, tuple(params)

    def format_for_duration_arithmetic(self, sql: str) -> str:
        return sql

    def quote_name(self, name: str) -> str:
        if name.startswith('"') and name.endswith('"'):
            return name
        return '"%s"' % name.replace('"', '""')

    def no_limit_value(self) -> str:
        return "-1"

    def pk_default_value(self) -> str:
        return "NULL"

    def _quote_params_for_last_executed_query(self, params: Sequence[Any]) -> tuple[Any, ...]:
        batch_size = 999
        if len(params) > batch_size:
            return tuple(
                quoted
                for index in range(0, len(params), batch_size)
                for quoted in self._quote_params_for_last_executed_query(
                    params[index : index + batch_size]
                )
            )
        if not params:
            return ()
        sql = "SELECT " + ", ".join(["QUOTE(?)"] * len(params))
        cursor = self.connection.connection.cursor()
        try:
            row = cursor.execute(sql, params).fetchone()
            return tuple(row)
        finally:
            cursor.close()

    def last_executed_query(self, cursor: Any, sql: str, params: Any) -> str:
        if not params:
            return sql
        if isinstance(params, (list, tuple)):
            quoted: Any = self._quote_params_for_last_executed_query(params)
        else:
            values = self._quote_params_for_last_executed_query(tuple(params.values()))
            quoted = dict(zip(params, values, strict=True))
        return str(sql % quoted)

    def _references_graph_for_table(self, table_name: str) -> list[str]:
        """Return *table_name* and every table that transitively references it.

        Turso 0.6 rejects the recursive CTE used by Django's SQLite backend for
        this calculation. Build the graph from the public foreign-key pragma
        instead; this also avoids parsing table SQL with a regular expression.
        """
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
            database_tables = [str(row[0]) for row in cursor.fetchall()]
            referencing: dict[str, set[str]] = {}
            for candidate in database_tables:
                cursor.execute("PRAGMA foreign_key_list(%s)" % self.quote_name(candidate))
                for row in cursor.fetchall():
                    referenced_table = str(row[2])
                    referencing.setdefault(referenced_table, set()).add(candidate)

        result: list[str] = []
        pending = [table_name]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            result.append(current)
            pending.extend(sorted(referencing.get(current, ()), reverse=True))
        return result

    def sql_flush(
        self,
        style: Any,
        tables: Sequence[str],
        *,
        reset_sequences: bool = False,
        allow_cascade: bool = False,
    ) -> list[str]:
        target_tables = set(tables)
        if allow_cascade:
            target_tables = {
                referenced
                for table in target_tables
                for referenced in self._references_graph_for_table(table)
            }
        statements = [
            f"{style.SQL_KEYWORD('DELETE')} {style.SQL_KEYWORD('FROM')} "
            f"{style.SQL_FIELD(self.quote_name(table))};"
            for table in target_tables
        ]
        if reset_sequences:
            statements.extend(
                self.sequence_reset_by_name_sql(
                    style, [{"table": table} for table in target_tables]
                )
            )
        return statements

    def sequence_reset_by_name_sql(
        self, style: Any, sequences: Sequence[Mapping[str, Any]]
    ) -> list[str]:
        if not sequences:
            return []
        names = ", ".join("'%s'" % info["table"].replace("'", "''") for info in sequences)
        return [
            f"{style.SQL_KEYWORD('UPDATE')} {style.SQL_TABLE(self.quote_name('sqlite_sequence'))} "
            f"{style.SQL_KEYWORD('SET')} {style.SQL_FIELD(self.quote_name('seq'))} = 0 "
            f"{style.SQL_KEYWORD('WHERE')} {style.SQL_FIELD(self.quote_name('name'))} "
            f"{style.SQL_KEYWORD('IN')} ({names});"
        ]

    def adapt_datefield_value(self, value: Any) -> Any:
        return value.isoformat() if value is not None else None

    def adapt_datetimefield_value(self, value: Any) -> Any:
        if value is None:
            return None
        if timezone.is_aware(value):
            if settings.USE_TZ:
                value = value.astimezone(self.connection.timezone).replace(tzinfo=None)
            else:
                raise ValueError(
                    "Turso backend does not support timezone-aware datetimes when USE_TZ is False."
                )
        return value.isoformat(" ")

    def adapt_timefield_value(self, value: Any) -> Any:
        if value is None:
            return None
        if timezone.is_aware(value):
            raise ValueError("Turso backend does not support timezone-aware times.")
        return value.isoformat()

    def adapt_decimalfield_value(
        self, value: Any, max_digits: int | None = None, decimal_places: int | None = None
    ) -> Any:
        if value is None:
            return None
        return str(value)

    def get_db_converters(self, expression: Any) -> list[Any]:
        converters = super().get_db_converters(expression)
        internal_type = expression.output_field.get_internal_type()
        if internal_type == "DateTimeField":
            converters.append(self.convert_datetimefield_value)
        elif internal_type == "DateField":
            converters.append(self.convert_datefield_value)
        elif internal_type == "TimeField":
            converters.append(self.convert_timefield_value)
        elif internal_type == "DecimalField":
            converters.append(self.get_decimalfield_converter(expression))
        elif internal_type == "UUIDField":
            converters.append(self.convert_uuidfield_value)
        elif internal_type == "BooleanField":
            converters.append(self.convert_booleanfield_value)
        return converters

    def convert_datetimefield_value(self, value: Any, expression: Any, connection: Any) -> Any:
        if value is not None and not isinstance(value, datetime.datetime):
            value = parse_datetime(value)
        if value is not None and settings.USE_TZ and not timezone.is_aware(value):
            value = timezone.make_aware(value, self.connection.timezone)
        return value

    def convert_datefield_value(self, value: Any, expression: Any, connection: Any) -> Any:
        return (
            parse_date(value)
            if value is not None and not isinstance(value, datetime.date)
            else value
        )

    def convert_timefield_value(self, value: Any, expression: Any, connection: Any) -> Any:
        return (
            parse_time(value)
            if value is not None and not isinstance(value, datetime.time)
            else value
        )

    def get_decimalfield_converter(self, expression: Any) -> Any:
        create_decimal = decimal.Context(prec=15).create_decimal_from_float
        if isinstance(expression, Col):
            output_field = expression.output_field
            decimal_places = getattr(output_field, "decimal_places")
            context = getattr(output_field, "context")
            quantize_value = decimal.Decimal(1).scaleb(-decimal_places)

            def converter(value: Any, _expression: Any, connection: Any) -> Any:
                if value is None:
                    return None
                return (
                    create_decimal(value).quantize(quantize_value, context=context)
                    if isinstance(value, float)
                    else decimal.Decimal(value)
                )

        else:

            def converter(value: Any, _expression: Any, connection: Any) -> Any:
                return (
                    create_decimal(value)
                    if isinstance(value, float)
                    else decimal.Decimal(value)
                    if value is not None
                    else None
                )

        return converter

    def convert_uuidfield_value(self, value: Any, expression: Any, connection: Any) -> Any:
        return uuid.UUID(value) if value is not None and not isinstance(value, uuid.UUID) else value

    def convert_booleanfield_value(self, value: Any, expression: Any, connection: Any) -> Any:
        return bool(value) if value in (0, 1) else value

    def combine_expression(self, connector: str, sub_expressions: list[str]) -> str:
        if connector == "^":
            return "POWER(%s)" % ",".join(sub_expressions)
        if connector == "#":
            return "BITXOR(%s)" % ",".join(sub_expressions)
        return super().combine_expression(connector, sub_expressions)

    def combine_duration_expression(self, connector: str, sub_expressions: list[str]) -> str:
        if connector not in {"+", "-", "*", "/"}:
            raise DatabaseError(f"Invalid connector for timedelta: {connector}.")
        raise NotSupportedError(
            "Duration arithmetic isn't supported by django-pyturso v1."
        )

    def integer_field_range(self, internal_type: str) -> tuple[int, int]:
        if internal_type in {
            "PositiveBigIntegerField",
            "PositiveIntegerField",
            "PositiveSmallIntegerField",
        }:
            return 0, 9223372036854775807
        return -9223372036854775808, 9223372036854775807

    def subtract_temporals(
        self,
        internal_type: str,
        lhs: tuple[str, Sequence[Any]],
        rhs: tuple[str, Sequence[Any]],
    ) -> tuple[str, tuple[Any, ...]]:
        raise NotSupportedError(
            "Temporal subtraction isn't supported by django-pyturso v1."
        )

    def insert_statement(self, on_conflict: OnConflict | None = None) -> str:
        return (
            "INSERT OR IGNORE INTO"
            if on_conflict == OnConflict.IGNORE
            else super().insert_statement(on_conflict)
        )

    def on_conflict_suffix_sql(
        self,
        fields: Sequence[Any],
        on_conflict: OnConflict | None,
        update_fields: Sequence[Any],
        unique_fields: Sequence[Any],
    ) -> str:
        if on_conflict == OnConflict.UPDATE:
            return "ON CONFLICT(%s) DO UPDATE SET %s" % (
                ", ".join(map(self.quote_name, unique_fields)),
                ", ".join(
                    f"{self.quote_name(field)} = EXCLUDED.{self.quote_name(field)}"
                    for field in update_fields
                ),
            )
        return super().on_conflict_suffix_sql(fields, on_conflict, update_fields, unique_fields)

    def format_json_path_numeric_index(self, num: int) -> str:
        return f"[{num}]" if num >= 0 else f"[#-{abs(num)}]"
