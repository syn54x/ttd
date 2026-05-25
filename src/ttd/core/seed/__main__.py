"""CLI entry: ``uv run python -m ttd.core.seed``."""

from __future__ import annotations

import argparse
import asyncio

from ttd.core.db import close_db
from ttd.core.seed.runner import seed_database


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the local TTD database with demo ledger data."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing demo clients, projects, and entries.",
    )
    return parser.parse_args()


async def _run(force: bool) -> int:
    summary = await seed_database(force=force)
    if summary.skipped:
        print(
            "Demo data already present. Run with --force to replace "
            "(Northwind Studio / Summit Labs only)."
        )
        return 0
    print(
        f"Seeded {summary.clients} clients, "
        f"{summary.projects} projects, {summary.entries} time entries."
    )
    return 0


def main() -> None:
    args = _parse_args()

    async def _main() -> int:
        try:
            return await _run(args.force)
        finally:
            await close_db()

    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
