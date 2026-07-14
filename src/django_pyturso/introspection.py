"""Schema introspection for embedded Turso."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import sqlparse
from django.db import DatabaseError
from django.db.backends.base.introspection import BaseDatabaseIntrospection, TableInfo
from django.db.backends.utils import CursorWrapper
from django.db.models import Index
from django.db.models.fields import Field
from django.utils.regex_helper import _lazy_re_compile

if TYPE_CHECKING:
    from django.db.backends.base.introspection import _ConstraintDict, _SequenceDict

# Type-affinity mapping, schema parsing, and constraint assembly follow Django
# 6.0.7's SQLite dialect.


class FieldInfo(NamedTuple):
    """DB-API field metadata plus SQLite-dialect primary-key/JSON markers."""

    name: str
    type_code: str
    display_size: int | None
    internal_size: int | None
    precision: int | None
    scale: int | None
    null_ok: bool
    default: Any
    collation: str | None
    pk: bool
    has_json_constraint: bool


field_size_re = _lazy_re_compile(r"^\s*(?:var)?char\s*\(\s*(\d+)\s*\)\s*$", flags=2)


def get_field_size(name: str) -> int | None:
    """Extract the declared size from a char/varchar type."""
    match = field_size_re.search(name)
    return int(match[1]) if match else None


class FlexibleFieldLookupDict:
    """Map Turso's SQLite-compatible declared types and affinities to fields."""

    base_data_types_reverse = {
        "bool": "BooleanField",
        "boolean": "BooleanField",
        "smallint": "SmallIntegerField",
        "smallint unsigned": "PositiveSmallIntegerField",
        "smallinteger": "SmallIntegerField",
        "int": "IntegerField",
        "integer": "IntegerField",
        "bigint": "BigIntegerField",
        "integer unsigned": "PositiveIntegerField",
        "bigint unsigned": "PositiveBigIntegerField",
        "decimal": "DecimalField",
        "numeric": "DecimalField",
        "real": "FloatField",
        "float": "FloatField",
        "double": "FloatField",
        "text": "TextField",
        "char": "CharField",
        "varchar": "CharField",
        "blob": "BinaryField",
        "date": "DateField",
        "datetime": "DateTimeField",
        "time": "TimeField",
    }

    def __getitem__(self, key: str) -> str:
        declared_type = key.lower().split("(", 1)[0].strip()
        if declared_type in self.base_data_types_reverse:
            return self.base_data_types_reverse[declared_type]
        if "int" in declared_type:
            return "IntegerField"
        if any(fragment in declared_type for fragment in ("char", "clob", "text")):
            return "TextField"
        if not declared_type or "blob" in declared_type:
            return "BinaryField"
        if any(fragment in declared_type for fragment in ("real", "floa", "doub")):
            return "FloatField"
        return "DecimalField"


class DatabaseIntrospection(BaseDatabaseIntrospection):
    """Introspect Turso through its verified SQLite-compatible pragmas."""

    data_types_reverse = FlexibleFieldLookupDict()

    def get_field_type(self, data_type: str, description: Any) -> str:
        field_type = super().get_field_type(data_type, description)
        if description.pk and field_type in {
            "BigIntegerField",
            "IntegerField",
            "SmallIntegerField",
        }:
            return "AutoField"
        if description.has_json_constraint:
            return "JSONField"
        return field_type

    def get_table_list(self, cursor: Any) -> list[TableInfo]:
        cursor.execute(
            """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
        return [TableInfo(name, object_type[0]) for name, object_type in cursor.fetchall()]

    def get_table_description(self, cursor: Any, table_name: str) -> list[FieldInfo]:
        cursor.execute("PRAGMA table_xinfo(%s)" % self.connection.ops.quote_name(table_name))
        table_info = cursor.fetchall()
        if not table_info:
            raise DatabaseError(f"Table {table_name} does not exist (empty pragma).")

        table_sql = self._get_schema_sql(cursor, "table", table_name)
        collations = self._get_column_collations(table_sql)
        column_sizes = self._get_column_sizes(table_sql)
        json_columns = self._get_json_columns(table_sql, {row[1] for row in table_info})
        description = [
            FieldInfo(
                name=name,
                type_code=data_type,
                display_size=column_sizes.get(name, get_field_size(data_type)),
                internal_size=None,
                precision=None,
                scale=None,
                null_ok=not bool(not_null),
                default=default,
                collation=collations.get(name),
                pk=bool(pk_position),
                has_json_constraint=name in json_columns,
            )
            for _, name, data_type, not_null, default, pk_position, hidden in table_info
            if hidden in {0, 2, 3}
        ]
        primary_key_indexes = [index for index, info in enumerate(description) if info.pk]
        if len(primary_key_indexes) > 1:
            for index in primary_key_indexes:
                description[index] = description[index]._replace(pk=False)
        return description

    def get_sequences(
        self,
        cursor: CursorWrapper,
        table_name: str,
        table_fields: Iterable[Field[Any, Any]] = (),
    ) -> list[_SequenceDict]:
        primary_key_columns = self.get_primary_key_columns(cursor, table_name) or []
        if len(primary_key_columns) != 1:
            return []
        return [{"table": table_name, "column": primary_key_columns[0]}]

    def get_relations(self, cursor: Any, table_name: str) -> dict[str, tuple[str, str]]:
        rows = self._foreign_key_rows(cursor, table_name)
        relations: dict[str, tuple[str, str]] = {}
        for rows_for_constraint in rows.values():
            target_table = rows_for_constraint[0][2]
            target_columns = self._resolve_foreign_key_target_columns(
                cursor, target_table, rows_for_constraint
            )
            for row, target_column in zip(rows_for_constraint, target_columns, strict=True):
                relations[row[3]] = (target_column, target_table)
        return relations

    def get_primary_key_columns(self, cursor: Any, table_name: str) -> list[str] | None:
        cursor.execute("PRAGMA table_info(%s)" % self.connection.ops.quote_name(table_name))
        primary_key_rows = [row for row in cursor.fetchall() if row[5]]
        if not primary_key_rows:
            return None
        primary_key_rows.sort(key=lambda row: row[5])
        return [row[1] for row in primary_key_rows]

    def get_constraints(self, cursor: CursorWrapper, table_name: str) -> dict[str, _ConstraintDict]:
        table_sql = self._get_schema_sql(cursor, "table", table_name)
        columns = {info.name for info in self.get_table_description(cursor, table_name)}
        constraints: dict[str, _ConstraintDict] = (
            self._parse_table_constraints(table_sql, columns) if table_sql else {}
        )

        cursor.execute("PRAGMA index_list(%s)" % self.connection.ops.quote_name(table_name))
        for row in cursor.fetchall():
            index_name = row[1]
            unique = bool(row[2])
            index_sql = self._get_schema_sql(cursor, "index", index_name)
            if index_sql is None:
                continue
            cursor.execute("PRAGMA index_xinfo(%s)" % self.connection.ops.quote_name(index_name))
            key_columns: list[str] = []
            orders: list[str] = []
            for index_info in cursor.fetchall():
                if not bool(index_info[5]):
                    continue
                key_columns.append(str(index_info[2] or ""))
                orders.append("DESC" if bool(index_info[3]) else "ASC")
            constraints[index_name] = cast(
                "_ConstraintDict",
                {
                    "columns": key_columns,
                    "orders": orders,
                    "primary_key": False,
                    "unique": unique,
                    "foreign_key": None,
                    "check": False,
                    "index": True,
                    "type": Index.suffix,
                    "definition": index_sql,
                },
            )

        primary_key_columns = self.get_primary_key_columns(cursor, table_name)
        if primary_key_columns:
            constraints["__primary__"] = cast(
                "_ConstraintDict",
                {
                    "columns": primary_key_columns,
                    "primary_key": True,
                    "unique": False,
                    "foreign_key": None,
                    "check": False,
                    "index": False,
                },
            )

        for foreign_key_id, rows in self._foreign_key_rows(cursor, table_name).items():
            target_table = rows[0][2]
            target_columns = self._resolve_foreign_key_target_columns(cursor, target_table, rows)
            constraints[f"fk_{foreign_key_id}"] = cast(
                "_ConstraintDict",
                {
                    "columns": [row[3] for row in rows],
                    "primary_key": False,
                    "unique": False,
                    "foreign_key": (target_table, target_columns[0]),
                    "check": False,
                    "index": False,
                },
            )
        return constraints

    def _foreign_key_rows(self, cursor: Any, table_name: str) -> dict[int, list[tuple[Any, ...]]]:
        cursor.execute("PRAGMA foreign_key_list(%s)" % self.connection.ops.quote_name(table_name))
        grouped: defaultdict[int, list[tuple[Any, ...]]] = defaultdict(list)
        for row in cursor.fetchall():
            grouped[int(row[0])].append(tuple(row))
        for rows in grouped.values():
            rows.sort(key=lambda row: row[1])
        return dict(grouped)

    def _resolve_foreign_key_target_columns(
        self, cursor: Any, target_table: str, rows: list[tuple[Any, ...]]
    ) -> list[str]:
        declared_columns = [row[4] for row in rows]
        if all(column not in (None, "") for column in declared_columns):
            return [str(column) for column in declared_columns]
        primary_key_columns = self.get_primary_key_columns(cursor, target_table) or []
        if len(primary_key_columns) != len(rows):
            source_columns = tuple(str(row[3]) for row in rows)
            raise DatabaseError(
                "Cannot resolve foreign key target columns for "
                f"{target_table!r}: source columns {source_columns!r} do not match "
                f"the target primary key {tuple(primary_key_columns)!r}."
            )
        resolved: list[str] = []
        for row, declared_column in zip(rows, declared_columns, strict=True):
            sequence = int(row[1])
            if sequence >= len(primary_key_columns):
                raise DatabaseError(
                    f"Invalid foreign-key sequence {sequence} for table {target_table!r}."
                )
            resolved.append(
                str(declared_column)
                if declared_column not in (None, "")
                else primary_key_columns[sequence]
            )
        return resolved

    @staticmethod
    def _get_schema_sql(cursor: Any, object_type: str, name: str) -> str | None:
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type = %s AND name = %s",
            (object_type, name),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    @staticmethod
    def _parse_column_or_constraint_definition(
        tokens: Iterator[Any], columns: set[str]
    ) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None, Any]:
        token = None
        is_constraint_definition = None
        field_name = None
        constraint_name = None
        unique = False
        unique_columns: list[str] = []
        check = False
        check_columns: list[str] = []
        braces_deep = 0
        for token in tokens:
            if token.match(sqlparse.tokens.Punctuation, "("):
                braces_deep += 1
            elif token.match(sqlparse.tokens.Punctuation, ")"):
                braces_deep -= 1
                if braces_deep < 0:
                    break
            elif braces_deep == 0 and token.match(sqlparse.tokens.Punctuation, ","):
                break
            if is_constraint_definition is None:
                is_constraint_definition = token.match(sqlparse.tokens.Keyword, "CONSTRAINT")
                if is_constraint_definition:
                    continue
            if is_constraint_definition:
                if constraint_name is None:
                    if token.ttype in (sqlparse.tokens.Name, sqlparse.tokens.Keyword):
                        constraint_name = token.value
                    elif token.ttype == sqlparse.tokens.Literal.String.Symbol:
                        constraint_name = token.value[1:-1]
                if token.match(sqlparse.tokens.Keyword, "UNIQUE"):
                    unique = True
                    unique_braces_deep = braces_deep
                elif unique:
                    if unique_braces_deep == braces_deep:
                        if unique_columns:
                            unique = False
                        continue
                    if token.ttype in (sqlparse.tokens.Name, sqlparse.tokens.Keyword):
                        unique_columns.append(token.value)
                    elif token.ttype == sqlparse.tokens.Literal.String.Symbol:
                        unique_columns.append(token.value[1:-1])
            else:
                if field_name is None:
                    if token.ttype in (sqlparse.tokens.Name, sqlparse.tokens.Keyword):
                        field_name = token.value
                    elif token.ttype == sqlparse.tokens.Literal.String.Symbol:
                        field_name = token.value[1:-1]
                if token.match(sqlparse.tokens.Keyword, "UNIQUE") and field_name is not None:
                    unique_columns = [field_name]
            if token.match(sqlparse.tokens.Keyword, "CHECK"):
                check = True
                check_braces_deep = braces_deep
            elif check:
                if check_braces_deep == braces_deep:
                    if check_columns:
                        check = False
                    continue
                candidate = (
                    token.value[1:-1]
                    if token.ttype == sqlparse.tokens.Literal.String.Symbol
                    else token.value
                )
                if candidate in columns:
                    check_columns.append(candidate)
        if token is None:
            raise DatabaseError("Unable to parse an empty table definition.")
        unique_constraint = (
            {
                "unique": True,
                "columns": unique_columns,
                "primary_key": False,
                "foreign_key": None,
                "check": False,
                "index": False,
            }
            if unique_columns
            else None
        )
        check_constraint = (
            {
                "check": True,
                "columns": list(dict.fromkeys(check_columns)),
                "primary_key": False,
                "unique": False,
                "foreign_key": None,
                "index": False,
            }
            if check_columns
            else None
        )
        return constraint_name, unique_constraint, check_constraint, token

    @classmethod
    def _parse_table_constraints(cls, sql: str, columns: set[str]) -> dict[str, _ConstraintDict]:
        statements = sqlparse.parse(sql)
        if not statements:
            return {}
        constraints: dict[str, _ConstraintDict] = {}
        unnamed_index = 0
        tokens = (
            token
            for token in statements[0].flatten()  # type: ignore[no-untyped-call]
            if not token.is_whitespace
        )
        for token in tokens:
            if token.match(sqlparse.tokens.Punctuation, "("):
                break
        else:
            return constraints
        while True:
            constraint_name, unique, check, end_token = cls._parse_column_or_constraint_definition(
                tokens, columns
            )
            for constraint in (unique, check):
                if constraint is None:
                    continue
                if constraint_name:
                    constraints[constraint_name] = cast("_ConstraintDict", constraint)
                else:
                    unnamed_index += 1
                    constraints[f"__unnamed_constraint_{unnamed_index}__"] = cast(
                        "_ConstraintDict", constraint
                    )
            if end_token.match(sqlparse.tokens.Punctuation, ")"):
                break
        return constraints

    @classmethod
    def _get_column_collations(cls, table_sql: str | None) -> dict[str, str | None]:
        if not table_sql:
            return {}
        collations: dict[str, str | None] = {}
        for definition in cls._split_table_definitions(table_sql):
            column_name = cls._leading_identifier(definition)
            if column_name is None or column_name.upper() in {
                "CHECK",
                "CONSTRAINT",
                "FOREIGN",
                "PRIMARY",
                "UNIQUE",
            }:
                continue
            match = _lazy_re_compile(
                r"\bCOLLATE\s+(?:\"((?:\"\"|[^\"])*)\"|`([^`]*)`|\[([^]]*)\]|([^\s,)]+))",
                flags=2,
            ).search(definition)
            collations[column_name] = (
                next(
                    (value.replace('""', '"') for value in match.groups() if value is not None),
                    None,
                )
                if match
                else None
            )
        return collations

    @classmethod
    def _get_column_sizes(cls, table_sql: str | None) -> dict[str, int]:
        if not table_sql:
            return {}
        sizes: dict[str, int] = {}
        size_pattern = _lazy_re_compile(r"\b(?:var)?char\s*\(\s*(\d+)\s*\)", flags=2)
        for definition in cls._split_table_definitions(table_sql):
            column_name = cls._leading_identifier(definition)
            match = size_pattern.search(definition)
            if column_name is not None and match:
                sizes[column_name] = int(match[1])
        return sizes

    @classmethod
    def _get_json_columns(cls, table_sql: str | None, columns: set[str]) -> set[str]:
        if not table_sql:
            return set()
        columns_by_name = {column.casefold(): column for column in columns}
        result: set[str] = set()
        statements = sqlparse.parse(table_sql)
        if not statements:
            return result
        tokens = [
            token
            for token in statements[0].flatten()  # type: ignore[no-untyped-call]
            if not token.is_whitespace
        ]
        for index, token in enumerate(tokens[:-3]):
            if token.value.casefold() != "json_valid":
                continue
            opening, identifier, closing = tokens[index + 1 : index + 4]
            if not (
                opening.match(sqlparse.tokens.Punctuation, "(")
                and closing.match(sqlparse.tokens.Punctuation, ")")
                and identifier.ttype
                in (
                    sqlparse.tokens.Name,
                    sqlparse.tokens.Keyword,
                    sqlparse.tokens.Literal.String.Symbol,
                )
            ):
                continue
            name = str(identifier.value)
            if name.startswith('"') and name.endswith('"'):
                name = name[1:-1].replace('""', '"')
            elif name.startswith("`") and name.endswith("`"):
                name = name[1:-1]
            elif name.startswith("[") and name.endswith("]"):
                name = name[1:-1]
            if column := columns_by_name.get(name.casefold()):
                result.add(column)
        return result

    @staticmethod
    def _leading_identifier(definition: str) -> str | None:
        parsed = sqlparse.parse(definition)
        if not parsed:
            return None
        token = next(
            (
                token
                for token in parsed[0].flatten()  # type: ignore[no-untyped-call]
                if not token.is_whitespace
            ),
            None,
        )
        if token is None:
            return None
        value = str(token.value)
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1].replace('""', '"')
        if value.startswith("`") and value.endswith("`"):
            return value[1:-1]
        if value.startswith("[") and value.endswith("]"):
            return value[1:-1]
        return value

    @staticmethod
    def _split_table_definitions(sql: str) -> list[str]:
        start = sql.find("(")
        if start < 0:
            return []
        definitions: list[str] = []
        current: list[str] = []
        depth = 0
        quote: str | None = None
        index = start + 1
        while index < len(sql):
            character = sql[index]
            if quote is not None:
                current.append(character)
                if quote == "]" and character == "]":
                    quote = None
                elif quote != "]" and character == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote:
                        current.append(sql[index + 1])
                        index += 1
                    else:
                        quote = None
            elif character in {'"', "'", "`"}:
                quote = character
                current.append(character)
            elif character == "[":
                quote = "]"
                current.append(character)
            elif character == "(":
                depth += 1
                current.append(character)
            elif character == ")":
                if depth == 0:
                    if definition := "".join(current).strip():
                        definitions.append(definition)
                    break
                depth -= 1
                current.append(character)
            elif character == "," and depth == 0:
                if definition := "".join(current).strip():
                    definitions.append(definition)
                current = []
            else:
                current.append(character)
            index += 1
        return definitions
