"""
scripts/clear_pipeline_data.py

Shows row counts for all pipeline tables, asks for confirmation,
then truncates them in FK-safe order.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from backend.database import engine

# Tables in FK-safe order (dependents first)
TABLES = [
    "beat_reporter_signals",
    "player_dependencies",
    "player_schedules",
    "player_injury_profiles",
    "player_profiles",
    "team_systems",
    "agent_cache",
    "api_usage_log",
    "players",
]


async def get_counts() -> dict[str, int]:
    counts = {}
    async with engine.begin() as conn:
        for table in TABLES:
            row = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))  # noqa: S608
            counts[table] = row.scalar_one()
    return counts


async def truncate_all() -> None:
    # Single statement — CASCADE handles any FK references we missed
    tables_sql = ", ".join(TABLES)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables_sql} CASCADE"))  # noqa: S608


async def main() -> None:
    print("\n=== Pipeline Data Clear ===\n")

    print("Current row counts:")
    counts = await get_counts()
    total = sum(counts.values())
    for table, count in counts.items():
        marker = "  " if count == 0 else ">>"
        print(f"  {marker} {table:<30} {count:>6} rows")
    print(f"\n  Total: {total} rows across {len(TABLES)} tables\n")

    if total == 0:
        print("All tables are already empty. Nothing to do.")
        return

    answer = input("Type 'yes' to TRUNCATE all tables, or anything else to cancel: ").strip()
    if answer != "yes":
        print("Cancelled.")
        sys.exit(0)

    print("\nTruncating...")
    await truncate_all()

    print("\nVerifying...")
    counts_after = await get_counts()
    all_zero = all(c == 0 for c in counts_after.values())
    for table, count in counts_after.items():
        status = "OK" if count == 0 else "FAIL"
        print(f"  [{status}] {table:<30} {count} rows")

    if all_zero:
        print("\nDatabase cleared successfully.")
    else:
        print("\nERROR: Some tables still have rows — check FK constraints.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
