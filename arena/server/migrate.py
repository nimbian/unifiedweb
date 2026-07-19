"""Apply ordered SQL migrations from ``db/migrations`` to Postgres.

    python -m server.migrate                    # uses $DATABASE_URL
    python -m server.migrate --dsn postgresql://...

Each ``NNNN_name.sql`` file is applied at most once, in filename order, inside a
transaction; the applied version is recorded in ``schema_migrations`` (which this
runner owns). Requires ``asyncpg``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"


async def apply_migrations(dsn: str) -> list[str]:
    con = await asyncpg.connect(dsn)
    newly_applied: list[str] = []
    try:
        await con.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {r["version"] for r in await con.fetch("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.stem
            if version in applied:
                print(f"  = {version} (already applied)")
                continue
            print(f"  + {version} applying...")
            sql = path.read_text(encoding="utf-8")
            async with con.transaction():
                await con.execute(sql)
                await con.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", version
                )
            newly_applied.append(version)
    finally:
        await con.close()
    return newly_applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply D&D Arena DB migrations")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args(argv)
    if not args.dsn:
        parser.error("no DSN: pass --dsn or set DATABASE_URL")
    applied = asyncio.run(apply_migrations(args.dsn))
    print(f"done — {len(applied)} migration(s) applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
