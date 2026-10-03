"""Exit with an open Turso transaction after a committed write."""

from __future__ import annotations

import os
import sys

import turso


def main() -> None:
    connection = turso.connect(sys.argv[1], isolation_level=None)
    connection.execute(f"PRAGMA journal_mode = {sys.argv[2]}").fetchall()
    connection.execute("CREATE TABLE recovery_probe (value TEXT)")
    connection.execute("INSERT INTO recovery_probe VALUES (?)", ("committed",))
    connection.execute(f"BEGIN {sys.argv[3]}")
    connection.execute("INSERT INTO recovery_probe VALUES (?)", ("uncommitted",))
    os._exit(23)


if __name__ == "__main__":
    main()
