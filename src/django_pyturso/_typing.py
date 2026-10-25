"""Types for data at the driver and SQL parser boundaries."""

from collections.abc import Iterable, Iterator, Mapping
from typing import Protocol

from sqlparse.tokens import _TokenType

type Row = tuple[object, ...]
type Parameters = Iterable[object] | Mapping[str, object]


class SQLToken(Protocol):
    """The sqlparse token attributes that the backend reads."""

    value: str
    ttype: _TokenType | None
    is_whitespace: bool

    def match(self, ttype: _TokenType, values: str | tuple[str, ...]) -> bool: ...


class SQLStatement(Protocol):
    def flatten(self) -> Iterator[SQLToken]: ...
