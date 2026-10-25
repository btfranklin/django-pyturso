"""Validate structured values read from test artifacts and child processes."""

from __future__ import annotations

import datetime
import decimal
import json
from collections.abc import Mapping, Sequence

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]


def json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.total_seconds()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"Expected a string key, received {type(key).__name__}.")
            result[key] = json_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | memoryview):
        return [json_value(item) for item in value]
    raise TypeError(f"Cannot encode {type(value).__name__} as a test JSON value.")


def json_object(value: object) -> dict[str, JSONValue]:
    result = json_value(value)
    if not isinstance(result, dict):
        raise TypeError("Expected a JSON object.")
    return result


def load_json_object(source: str) -> dict[str, JSONValue]:
    value: object = json.loads(source)
    return json_object(value)
