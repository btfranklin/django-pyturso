#!/usr/bin/env python3
"""Run Django integration-project management commands."""

import os
import sys
from pathlib import Path

from django.core.management import execute_from_command_line


def main() -> None:
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings.turso_memory")
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
