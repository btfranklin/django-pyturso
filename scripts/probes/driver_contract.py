#!/usr/bin/env python3
"""Collect versioned evidence about pyturso's public DB-API contract.

The default probe is read-only and uses only a private ``:memory:`` connection.
Pass ``--include-disposable-exercises`` to exercise transactions and a database
created inside a temporary directory. No caller-supplied database is accepted.
"""

from __future__ import annotations

import argparse
import inspect
import json
import locale
import os
import platform
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from email.parser import Parser
from functools import partial
from importlib import metadata
from pathlib import Path
from typing import Any

import turso

SCHEMA_VERSION = 1
PROBE_ID = "django-pyturso.driver-contract"
PROBE_REVISION = "phase-0a-v1"
PARAMETER_COUNTS = (999, 1_000, 32_766, 32_767)


def _qualified_name(value: object) -> str:
    cls = value if isinstance(value, type) else type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def _public_attributes(value: object) -> list[str]:
    return sorted(name for name in dir(value) if not name.startswith("_"))


def _error_details(error: Exception) -> dict[str, str]:
    return {"type": _qualified_name(error), "message": str(error)}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex(), "length": len(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence):
        return [_json_safe(item) for item in value]
    return {"type": _qualified_name(value), "repr": repr(value)}


def _attempt(operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"status": "ok", "result": _json_safe(operation())}
    except Exception as error:  # Probe evidence must retain the driver's public error.
        return {"status": "error", "error": _error_details(error)}


def _execute_fetchall(cursor: Any, statement: str) -> Any:
    return cursor.execute(statement).fetchall()


def _execute_parameter_count(connection: Any, statement: str, count: int) -> Any:
    return connection.execute(statement, tuple(range(count))).fetchone()[0]


def _distribution_details(name: str) -> dict[str, Any]:
    distribution = metadata.distribution(name)
    wheel_text = distribution.read_text("WHEEL")
    wheel: dict[str, Any] | None = None
    if wheel_text is not None:
        message = Parser().parsestr(wheel_text)
        wheel = {
            "wheel_version": message.get("Wheel-Version"),
            "generator": message.get("Generator"),
            "root_is_purelib": message.get("Root-Is-Purelib"),
            "tags": message.get_all("Tag", []),
        }
    return {
        "name": distribution.metadata["Name"],
        "version": distribution.version,
        "wheel": wheel,
    }


def _environment() -> dict[str, Any]:
    language, encoding = locale.getlocale()
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "packages": {
            "django": _distribution_details("Django"),
            "pyturso": _distribution_details("pyturso"),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "process": {
            "timezone": datetime.now().astimezone().tzname(),
            "locale": {"language": language, "encoding": encoding},
        },
    }


def _exception_hierarchy() -> dict[str, Any]:
    names = (
        "Warning",
        "Error",
        "InterfaceError",
        "DatabaseError",
        "DataError",
        "OperationalError",
        "IntegrityError",
        "InternalError",
        "ProgrammingError",
        "NotSupportedError",
    )
    hierarchy: dict[str, Any] = {}
    for name in names:
        exception = getattr(turso, name)
        hierarchy[name] = {
            "qualified_name": _qualified_name(exception),
            "bases": [_qualified_name(base) for base in exception.__bases__],
            "is_error": issubclass(exception, turso.Error),
            "is_database_error": issubclass(exception, turso.DatabaseError),
        }
    return hierarchy


def _pragma_inventory(cursor: Any) -> dict[str, Any]:
    statements = {
        "compile_options": "PRAGMA compile_options",
        "defer_foreign_keys": "PRAGMA defer_foreign_keys",
        "foreign_key_list": "PRAGMA foreign_key_list(probe_parent)",
        "foreign_keys": "PRAGMA foreign_keys",
        "index_info": "PRAGMA index_info(probe_index)",
        "index_list": "PRAGMA index_list(probe_child)",
        "journal_mode": "PRAGMA journal_mode",
        "legacy_alter_table": "PRAGMA legacy_alter_table",
        "max_variable_number": "PRAGMA max_variable_number",
        "table_info": "PRAGMA table_info(probe_child)",
        "table_xinfo": "PRAGMA table_xinfo(probe_child)",
    }
    return {
        name: _attempt(partial(_execute_fetchall, cursor, statement))
        for name, statement in statements.items()
    }


def _function_inventory(cursor: Any) -> dict[str, Any]:
    result = _attempt(lambda: cursor.execute("PRAGMA function_list").fetchall())
    if result["status"] != "ok":
        return result

    rows = result["result"]
    functions = [
        {
            "name": row[0],
            "builtin": bool(row[1]),
            "kind": row[2],
            "encoding": row[3],
            "arity": row[4],
            "flags": row[5],
        }
        for row in rows
    ]
    functions.sort(key=lambda item: (item["name"], item["arity"], item["kind"]))
    return {
        "status": "ok",
        "row_count": len(functions),
        "distinct_names": sorted({item["name"] for item in functions}),
        "functions": functions,
    }


def _selected_function_trials(cursor: Any) -> dict[str, Any]:
    statements = {
        "generate_series": "SELECT value FROM generate_series(1, 3)",
        "percentile": "SELECT percentile(1, 50)",
        "regexp": "SELECT 'abc' REGEXP '^a'",
        "regexp_like": "SELECT regexp_like('abc', '^a')",
        "time_now": "SELECT time_now()",
        "uuid7": "SELECT uuid7()",
        "vector_distance_cos": ("SELECT vector_distance_cos(vector32('[1,0]'), vector32('[1,0]'))"),
    }
    return {
        name: _attempt(partial(_execute_fetchall, cursor, statement))
        for name, statement in statements.items()
    }


def _read_only_driver_probe() -> dict[str, Any]:
    connection = turso.connect(":memory:", isolation_level=None)
    try:
        cursor = connection.cursor()
        engine_version = cursor.execute("SELECT sqlite_version()").fetchone()[0]
        return {
            "dbapi": {
                "apilevel": turso.apilevel,
                "threadsafety": turso.threadsafety,
                "paramstyle": turso.paramstyle,
                "binary_constructor_available": hasattr(turso, "Binary"),
                "connect_signature": str(inspect.signature(turso.connect)),
                "module_sqlite_version": turso.sqlite_version,
                "module_sqlite_version_info": list(turso.sqlite_version_info),
                "exception_hierarchy": _exception_hierarchy(),
            },
            "connected_engine_version": engine_version,
            "public_api": {
                "connection_type": _qualified_name(connection),
                "connection_attributes": _public_attributes(connection),
                "cursor_type": _qualified_name(cursor),
                "cursor_attributes": _public_attributes(cursor),
                "connection_capabilities": {
                    name: hasattr(connection, name)
                    for name in (
                        "backup",
                        "create_aggregate",
                        "create_collation",
                        "create_function",
                        "getlimit",
                        "set_authorizer",
                        "setlimit",
                    )
                },
            },
            "functions": _function_inventory(cursor),
            "selected_function_trials": _selected_function_trials(cursor),
            "pragmas": _pragma_inventory(cursor),
        }
    finally:
        connection.close()


def _memory_behavior_probe() -> dict[str, Any]:
    connection = turso.connect(":memory:", isolation_level=None)
    cursor = connection.cursor()
    states: dict[str, bool] = {"initial": connection.in_transaction}
    try:
        qmark = cursor.execute("SELECT ? + ?", (2, 3)).fetchone()[0]
        named = cursor.execute("SELECT :left + :right", {"left": 2, "right": 3}).fetchone()[0]
        cursor.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT UNIQUE)")
        returned = cursor.execute(
            "INSERT INTO probe(value) VALUES (?) RETURNING id, value", ("kept",)
        ).fetchone()

        cursor.execute("BEGIN")
        states["after_begin"] = connection.in_transaction
        cursor.execute("SAVEPOINT probe_savepoint")
        cursor.execute("INSERT INTO probe(value) VALUES (?)", ("discarded",))
        cursor.execute("ROLLBACK TO probe_savepoint")
        cursor.execute("RELEASE probe_savepoint")
        connection.commit()
        states["after_commit"] = connection.in_transaction

        integrity_error = _attempt(
            lambda: cursor.execute("INSERT INTO probe(value) VALUES (?)", ("kept",)).fetchall()
        )
        row_count = cursor.execute("SELECT COUNT(*) FROM probe").fetchone()[0]
    finally:
        cursor.close()
        connection.close()

    closed = {
        "execute": _attempt(lambda: connection.execute("SELECT 1").fetchone()),
        "cursor_execute": _attempt(lambda: connection.cursor().execute("SELECT 1").fetchone()),
        "commit": _attempt(connection.commit),
        "rollback": _attempt(connection.rollback),
    }
    return {
        "bindings": {"qmark_result": qmark, "named_result": named},
        "returning_row": list(returned),
        "transaction_states": states,
        "savepoint_rollback_row_count": row_count,
        "integrity_error": integrity_error,
        "closed_connection": closed,
    }


def _parameter_probe(connection: Any) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for count in PARAMETER_COUNTS:
        placeholders = ",".join(["(?)"] * count)
        statement = f"SELECT COUNT(*) FROM (VALUES {placeholders})"
        results[str(count)] = _attempt(
            partial(_execute_parameter_count, connection, statement, count)
        )
    return {
        "v1_cross_platform_floor": 999,
        "local_counts": results,
        "note": "Passing local counts above 999 do not raise the portable v1 floor.",
    }


def _file_snapshot(directory: Path) -> list[dict[str, Any]]:
    return [
        {"name": path.name, "size": path.stat().st_size} for path in sorted(directory.iterdir())
    ]


def _disposable_file_probe() -> dict[str, Any]:
    directory = Path(tempfile.mkdtemp(prefix="django-pyturso-driver-probe-"))
    database = directory / "probe.sqlite3"
    evidence: dict[str, Any] = {}
    first: Any | None = None
    second: Any | None = None
    try:
        first = turso.connect(str(database), isolation_level=None)
        second = turso.connect(str(database), isolation_level=None)
        evidence["files_after_connect"] = _file_snapshot(directory)
        evidence["journal_mode"] = first.execute("PRAGMA journal_mode").fetchone()[0]

        first.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY, value TEXT)")
        first.execute("INSERT INTO probe(value) VALUES (?)", ("committed",))
        evidence["second_connection_committed_rows"] = second.execute(
            "SELECT value FROM probe ORDER BY id"
        ).fetchall()

        first.execute("BEGIN IMMEDIATE")
        first.execute("INSERT INTO probe(value) VALUES (?)", ("uncommitted",))
        evidence["second_connection_during_uncommitted_write"] = second.execute(
            "SELECT value FROM probe ORDER BY id"
        ).fetchall()
        evidence["competing_write"] = _attempt(
            lambda: second.execute("INSERT INTO probe(value) VALUES (?)", ("blocked",)).fetchall()
        )
        first.rollback()

        evidence["checkpoint_passive"] = _attempt(
            lambda: first.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchall()
        )
        evidence["checkpoint_truncate"] = _attempt(
            lambda: first.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        )
        evidence["parameters"] = _parameter_probe(first)
        evidence["files_before_close"] = _file_snapshot(directory)
    finally:
        if second is not None:
            second.close()
        if first is not None:
            first.close()

    evidence["files_after_close"] = _file_snapshot(directory)
    shutil.rmtree(directory)
    evidence["disposable_directory_removed"] = not directory.exists()
    return evidence


def collect_probe(*, include_disposable_exercises: bool = False) -> dict[str, Any]:
    """Return a JSON-serializable driver evidence document."""
    result: dict[str, Any] = {
        "schema_id": "django-pyturso.driver-contract.v1",
        "schema_version": SCHEMA_VERSION,
        "probe_id": PROBE_ID,
        "probe_revision": PROBE_REVISION,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": {
            "read_only_private_memory_connection": True,
            "disposable_exercises_included": include_disposable_exercises,
            "caller_database_accepted": False,
        },
        "environment": _environment(),
        "driver": _read_only_driver_probe(),
    }
    if include_disposable_exercises:
        result["disposable_exercises"] = {
            "memory": _memory_behavior_probe(),
            "file": _disposable_file_probe(),
        }
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-disposable-exercises",
        action="store_true",
        help="exercise transactions and a database in an auto-removed temporary directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON to this path instead of stdout",
    )
    parser.add_argument("--compact", action="store_true", help="omit JSON indentation")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evidence = collect_probe(include_disposable_exercises=args.include_disposable_exercises)
    indent = None if args.compact else 2
    serialized = json.dumps(evidence, indent=indent, sort_keys=True) + os.linesep
    if args.output is None:
        sys.stdout.write(serialized)
    else:
        args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
