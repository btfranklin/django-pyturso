"""Subprocess helper that exits with an uncommitted Turso WAL transaction."""

from __future__ import annotations

import os
import sys

import turso


def main() -> None:
    connection = turso.connect(sys.argv[1], isolation_level=None)
    connection.execute("CREATE TABLE recovery_probe (value TEXT)")
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO recovery_probe VALUES (?)", ("uncommitted",))
    os._exit(23)


if __name__ == "__main__":
    main()
