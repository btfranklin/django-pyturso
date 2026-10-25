"""SQL generation and value conversion for embedded Turso."""

import datetime
import decimal
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import chain
from typing import TYPE_CHECKING, Never

from django.conf import settings
from django.core.exceptions import FieldError
from django.core.management.color import Style
from django.db import DatabaseError, NotSupportedError, models
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.models.aggregates import AnyValue, Avg, StdDev, Sum, Variance
from django.db.models.constants import OnConflict
from django.db.models.expressions import Col, Expression, Window
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

from .introspection import _identifier_key

if TYPE_CHECKING:
    from .base import DatabaseWrapper

type Converter = Callable[[object, Expression, BaseDatabaseWrapper], object]

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

    connection: DatabaseWrapper

    cast_char_field_without_max_length = "text"
    cast_data_types = {"DateField": "TEXT", "DateTimeField": "TEXT"}
    explain_prefix = "EXPLAIN QUERY PLAN"
    jsonfield_datatype_values = frozenset(["null", "false", "true"])

    def bulk_batch_size(
        self, fields: Iterable[models.Field[Never, object]], objs: Sequence[object]
    ) -> int:
        flattened = list(
            chain.from_iterable(
                field.fields if isinstance(field, models.CompositePrimaryKey) else [field]
                for field in fields
            )
        )
        max_query_params = self.connection.features.max_query_params
        return max_query_params // len(flattened) if flattened else len(objs)

    def check_expression_support(self, expression: object) -> None:
        if isinstance(expression, _UNSUPPORTED_EXPRESSION_TYPES):
            raise NotSupportedError(
                f"{expression.__class__.__name__} isn't supported by django-pyturso v1."
            )
        if isinstance(expression, (Sum, Avg)):
            temporal_fields = (models.DateField, models.DateTimeField, models.TimeField)
            for source in expression.get_source_expressions():
                try:
                    output_field = source.output_field
                except AttributeError, FieldError:
                    continue
                if isinstance(output_field, temporal_fields):
                    raise NotSupportedError(
                        "You cannot use Sum or Avg aggregations on date/time fields "
                        "since date/time is saved as text."
                    )
        if (
            isinstance(expression, models.Aggregate)
            and getattr(expression, "distinct", False)
            and len(expression.source_expressions) > 1
        ):
            raise NotSupportedError(
                "Turso doesn't support DISTINCT on aggregates with multiple arguments."
            )

    def _validate_timezone(self, tzname: str | None) -> None:
        if tzname not in (None, "UTC") or (
            tzname is not None and self.connection.timezone_name != tzname
        ):
            raise NotSupportedError(
                "django-pyturso supports database-side temporal operations only "
                "without timezone conversion or in UTC."
            )

    @staticmethod
    def _extract_sql(lookup_type: str, sql: str) -> str:
        formats = {
            "year": "%%Y",
            "iso_year": "%%G",
            "month": "%%m",
            "day": "%%d",
            "week": "%%V",
            "week_day": "%%w",
            "iso_week_day": "%%u",
            "hour": "%%H",
            "minute": "%%M",
            "second": "%%S",
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
        self, lookup_type: str, sql: str, params: Sequence[object]
    ) -> tuple[str, tuple[object, ...]]:
        return self._extract_sql(lookup_type.lower(), sql), tuple(params)

    # These Django stubs declare str; the runtime requires SQL and parameters.
    def time_extract_sql(  # type: ignore[override]
        self, lookup_type: str, sql: str, params: Sequence[object]
    ) -> tuple[str, tuple[object, ...]]:
        return self._extract_sql(lookup_type.lower(), sql), tuple(params)

    def datetime_extract_sql(
        self, lookup_type: str, sql: str, params: Sequence[object], tzname: str | None
    ) -> tuple[str, tuple[object, ...]]:
        self._validate_timezone(tzname)
        return self._extract_sql(lookup_type.lower(), sql), tuple(params)

    def date_trunc_sql(
        self,
        lookup_type: str,
        sql: str,
        params: Sequence[object],
        tzname: str | None = None,
    ) -> tuple[str, tuple[object, ...]]:
        self._validate_timezone(tzname)
        lookup_type = lookup_type.lower()
        result_params = tuple(params)
        if lookup_type == "year":
            result = f"date({sql}, 'start of year')"
        elif lookup_type == "quarter":
            result = (
                f"CASE WHEN {sql} IS NULL THEN NULL ELSE "
                f"printf('%%04d-%%02d-01', CAST(strftime('%%Y', {sql}) AS INTEGER), "
                f"((CAST(strftime('%%m', {sql}) AS INTEGER) - 1) / 3) * 3 + 1) END"
            )
            result_params *= 3
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
        # Python time values use at most six fractional digits.
        return f"SUBSTR({formatted}, 12, 15)" if time_only else formatted

    # The stub omits the parameter tuple from the runtime return type.
    def datetime_trunc_sql(  # type: ignore[override]
        self, lookup_type: str, sql: str, params: Sequence[object], tzname: str | None
    ) -> tuple[str, tuple[object, ...]]:
        self._validate_timezone(tzname)
        lookup_type = lookup_type.lower()
        if lookup_type == "week":
            date_sql, result_params = self.date_trunc_sql("week", sql, params, tzname)
            return f"{date_sql} || ' 00:00:00'", result_params
        supported = {"year", "quarter", "month", "day", "hour", "minute", "second"}
        if lookup_type not in supported:
            raise NotSupportedError(f"Unsupported datetime truncation: {lookup_type}.")
        parsed = self._time_extension_input(sql)
        result = self._format_time_extension(f"time_trunc({parsed}, '{lookup_type}')")
        return f"CASE WHEN {sql} IS NULL THEN NULL ELSE {result} END", tuple(params) * 2

    # The stub omits the parameter tuple from the runtime return type.
    def time_trunc_sql(  # type: ignore[override]
        self,
        lookup_type: str,
        sql: str,
        params: Sequence[object],
        tzname: str | None = None,
    ) -> tuple[str, tuple[object, ...]]:
        self._validate_timezone(tzname)
        lookup_type = lookup_type.lower()
        if lookup_type not in {"hour", "minute", "second"}:
            raise NotSupportedError(f"Unsupported time truncation: {lookup_type}.")
        # Django may select time truncation from the result field even when
        # the input expression is a datetime. Reduce it to its time first.
        parsed = self._time_extension_input(f"time({sql})", time_only=True)
        truncated = f"time_trunc({parsed}, '{lookup_type}')"
        result = self._format_time_extension(truncated, time_only=True)
        return f"CASE WHEN {sql} IS NULL THEN NULL ELSE {result} END", tuple(params) * 2

    def datetime_cast_date_sql(
        self, sql: str, params: Sequence[object], tzname: str | None
    ) -> tuple[str, tuple[object, ...]]:
        self._validate_timezone(tzname)
        return f"date({sql})", tuple(params)

    def datetime_cast_time_sql(
        self, sql: str, params: Sequence[object], tzname: str | None
    ) -> tuple[str, tuple[object, ...]]:
        self._validate_timezone(tzname)
        parsed = self._time_extension_input(sql)
        formatted = self._format_time_extension(parsed, time_only=True)
        return f"CASE WHEN {sql} IS NULL THEN NULL ELSE {formatted} END", tuple(params) * 2

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

    def _quote_params_for_last_executed_query(self, params: Sequence[object]) -> tuple[object, ...]:
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
        connection = self.connection.connection
        if connection is None:
            raise RuntimeError("Expected an open connection for query formatting.")
        cursor = connection.cursor()
        try:
            row = cursor.execute(sql, params).fetchone()
            return tuple(row)
        finally:
            cursor.close()

    def last_executed_query(
        self,
        cursor: object,
        sql: str,
        params: Sequence[object] | Mapping[str, object] | None,
    ) -> str:
        if not params:
            return sql
        if not isinstance(params, Mapping):
            quoted: tuple[object, ...] | dict[str, object] = (
                self._quote_params_for_last_executed_query(params)
            )
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
            database_tables = self.connection.introspection.table_names(cursor)
            table_names = {_identifier_key(table): table for table in database_tables}
            referencing: dict[str, set[str]] = {}
            for candidate in database_tables:
                cursor.execute("PRAGMA foreign_key_list(%s)" % self.quote_name(candidate))
                for row in cursor.fetchall():
                    raw_target = str(row[2])
                    referenced_table = table_names.get(_identifier_key(raw_target), raw_target)
                    referencing.setdefault(referenced_table, set()).add(candidate)

        result: list[str] = []
        pending = [table_names.get(_identifier_key(table_name), table_name)]
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
        style: Style,
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
        self, style: Style, sequences: Sequence[Mapping[str, str]]
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

    def adapt_datefield_value(self, value: datetime.date | None) -> str | None:
        return value.isoformat() if value is not None else None

    def adapt_datetimefield_value(self, value: datetime.datetime | None) -> str | None:
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

    def adapt_timefield_value(self, value: datetime.datetime | datetime.time | None) -> str | None:
        if value is None:
            return None
        if timezone.is_aware(value):
            raise ValueError("Turso backend does not support timezone-aware times.")
        return value.isoformat()

    def adapt_decimalfield_value(
        self,
        value: decimal.Decimal | None,
        max_digits: int | None = None,
        decimal_places: int | None = None,
    ) -> str | None:
        if value is None:
            return None
        return str(value)

    def get_db_converters(self, expression: Expression) -> list[Converter]:
        converters: list[Converter] = super().get_db_converters(expression)
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

    def convert_datetimefield_value(
        self, value: object, expression: object, connection: object
    ) -> datetime.datetime | None:
        if isinstance(value, str):
            value = parse_datetime(value)
        if value is not None and not isinstance(value, datetime.datetime):
            raise TypeError("Expected a datetime, a string, or None from Turso.")
        if value is not None and settings.USE_TZ and not timezone.is_aware(value):
            value = timezone.make_aware(value, self.connection.timezone)
        return value

    def convert_datefield_value(
        self, value: object, expression: object, connection: object
    ) -> datetime.date | None:
        if isinstance(value, str):
            return parse_date(value)
        if value is None or isinstance(value, datetime.date):
            return value
        raise TypeError("Expected a date, a string, or None from Turso.")

    def convert_timefield_value(
        self, value: object, expression: object, connection: object
    ) -> datetime.time | None:
        if isinstance(value, str):
            return parse_time(value)
        if value is None or isinstance(value, datetime.time):
            return value
        raise TypeError("Expected a time, a string, or None from Turso.")

    def get_decimalfield_converter(self, expression: object) -> Converter:
        create_decimal = decimal.Context(prec=15).create_decimal_from_float
        if isinstance(expression, Col):
            output_field = expression.output_field
            if not isinstance(output_field, models.DecimalField):
                raise TypeError("Expected a DecimalField for decimal conversion.")
            decimal_places = output_field.decimal_places
            if decimal_places is None:
                raise TypeError("Expected decimal_places for decimal conversion.")
            context = output_field.context
            quantize_value = decimal.Decimal(1).scaleb(-decimal_places)

            def converter(
                value: object, _expression: object, connection: object
            ) -> decimal.Decimal | None:
                if value is None:
                    return None
                if not isinstance(value, str | int | float | decimal.Decimal):
                    raise TypeError("Expected a decimal value from Turso.")
                return (
                    create_decimal(value).quantize(quantize_value, context=context)
                    if isinstance(value, float)
                    else decimal.Decimal(value)
                )

        else:

            def converter(
                value: object, _expression: object, connection: object
            ) -> decimal.Decimal | None:
                if value is not None and not isinstance(value, str | int | float | decimal.Decimal):
                    raise TypeError("Expected a decimal value from Turso.")
                return (
                    create_decimal(value)
                    if isinstance(value, float)
                    else decimal.Decimal(value)
                    if value is not None
                    else None
                )

        return converter

    def convert_uuidfield_value(
        self, value: object, expression: object, connection: object
    ) -> uuid.UUID | None:
        if isinstance(value, str):
            return uuid.UUID(value)
        if value is None or isinstance(value, uuid.UUID):
            return value
        raise TypeError("Expected a UUID, a string, or None from Turso.")

    def convert_booleanfield_value(
        self, value: object, expression: object, connection: object
    ) -> object:
        return bool(value) if value in (0, 1) else value

    def combine_expression(self, connector: str, sub_expressions: list[str]) -> str:
        if connector == "^":
            return "POWER(%s)" % ",".join(sub_expressions)
        if connector == "#":
            raise NotSupportedError("Bitwise XOR isn't supported by django-pyturso v1.")
        return super().combine_expression(connector, sub_expressions)

    def combine_duration_expression(self, connector: str, sub_expressions: list[str]) -> str:
        if connector not in {"+", "-", "*", "/"}:
            raise DatabaseError(f"Invalid connector for timedelta: {connector}.")
        raise NotSupportedError("Duration arithmetic isn't supported by django-pyturso v1.")

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
        lhs: tuple[str, Sequence[object]],
        rhs: tuple[str, Sequence[object]],
    ) -> tuple[str, tuple[object, ...]]:
        raise NotSupportedError("Temporal subtraction isn't supported by django-pyturso v1.")

    def insert_statement(self, on_conflict: OnConflict | None = None) -> str:
        return (
            "INSERT OR IGNORE INTO"
            if on_conflict == OnConflict.IGNORE
            else super().insert_statement(on_conflict)
        )

    def on_conflict_suffix_sql(
        self,
        fields: Sequence[models.Field[Never, object]],
        on_conflict: OnConflict | None,
        update_fields: Sequence[str],
        unique_fields: Sequence[str],
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
