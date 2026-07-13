"""Run deterministic environment and ordering hardening lanes."""

from __future__ import annotations

import argparse
import locale
import os
import subprocess
import sys
from collections.abc import Sequence

DEFAULT_SEED = "20260713"
FAST_EXPRESSION = "not integration and not upstream and not stress and not performance"
FULL_EXPRESSION = "not upstream and not stress and not performance"
TEMPORAL_TARGETS = (
    "tests/core/test_operations.py",
    "tests/core/test_orm.py",
    "tests/core/test_migration_corpus.py",
)


def _run(arguments: Sequence[str], *, environment: dict[str, str] | None = None) -> None:
    command = [sys.executable, *arguments]
    print("hardening command:", " ".join(command), flush=True)
    subprocess.run(command, check=True, env=environment)


def _environment(**overrides: str) -> dict[str, str]:
    return {**os.environ, **overrides}


def _pytest(*arguments: str, environment: dict[str, str] | None = None) -> None:
    _run(("-m", "pytest", *arguments), environment=environment)


def _seed() -> str:
    seed = os.environ.get("HARDENING_SEED", DEFAULT_SEED)
    if not seed.isdecimal():
        raise ValueError("HARDENING_SEED must contain decimal digits only")
    print(f"hardening seed: {seed}", flush=True)
    return seed


def run_utc() -> None:
    _seed()
    _pytest("-m", FULL_EXPRESSION, environment=_environment(TZ="UTC"))


def run_timezones() -> None:
    _seed()
    for zone in ("America/Phoenix", "America/New_York"):
        print(f"hardening timezone: {zone}", flush=True)
        _pytest(
            *TEMPORAL_TARGETS,
            "-k",
            "date or time or temporal or duration",
            environment=_environment(TZ=zone),
        )


def run_locale() -> None:
    _seed()
    locale_name = os.environ.get("HARDENING_LOCALE", "de_DE.UTF-8")
    previous = locale.setlocale(locale.LC_ALL)
    try:
        locale.setlocale(locale.LC_ALL, locale_name)
    except locale.Error as error:
        raise RuntimeError(f"required hardening locale is unavailable: {locale_name}") from error
    finally:
        locale.setlocale(locale.LC_ALL, previous)
    print(f"hardening locale: {locale_name}", flush=True)
    _pytest(
        "tests/core/test_operations.py",
        "tests/core/test_schema.py",
        "tests/core/test_schema_branches.py",
        "-k",
        "date or time or decimal or quote or last_executed_query",
        environment=_environment(LC_ALL=locale_name, LANG=locale_name),
    )


def run_django_order() -> None:
    seed = _seed()
    base = (
        "tests/project/manage.py",
        "test",
        "tests.project.tests",
        "--settings=tests.settings.turso_memory",
        "--noinput",
        "--verbosity=2",
    )
    _run((*base, "--reverse"))
    _run((*base, f"--shuffle={seed}"))


def run_random_order() -> None:
    seed = _seed()
    _pytest(
        "--maxfail=1",
        "--random-order",
        "--random-order-bucket=global",
        f"--random-order-seed={seed}",
        "-m",
        FAST_EXPRESSION,
    )


def run_repeated_fast() -> None:
    seed = int(_seed())
    repetitions = int(os.environ.get("HARDENING_REPETITIONS", "3"))
    if repetitions < 1:
        raise ValueError("HARDENING_REPETITIONS must be positive")
    for index in range(repetitions):
        iteration_seed = str(seed + index)
        print(
            f"hardening repetition: {index + 1}/{repetitions}; PYTHONHASHSEED={iteration_seed}",
            flush=True,
        )
        _pytest(
            "--maxfail=1",
            "-m",
            FAST_EXPRESSION,
            environment=_environment(PYTHONHASHSEED=iteration_seed),
        )


RUNNERS = {
    "utc": run_utc,
    "timezones": run_timezones,
    "locale": run_locale,
    "django-order": run_django_order,
    "random-order": run_random_order,
    "repeated-fast": run_repeated_fast,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=RUNNERS)
    arguments = parser.parse_args()
    RUNNERS[arguments.lane]()


if __name__ == "__main__":
    main()
