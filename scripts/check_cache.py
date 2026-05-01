"""Debug: inspect agent_cache for schedule agent."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from backend.database import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as session:
        # Count by agent_name
        rows = (await session.execute(
            text("SELECT agent_name, COUNT(*) as cnt FROM agent_cache GROUP BY agent_name ORDER BY agent_name")
        )).fetchall()
        print("agent_cache by agent_name:")
        for row in rows:
            print(f"  {row[0]}: {row[1]} entries")

        # Check schedule-specific
        sched_rows = (await session.execute(
            text("SELECT id, agent_name, entity_id, input_hash, created_at FROM agent_cache WHERE agent_name = 'schedule' LIMIT 5")
        )).fetchall()
        print(f"\nSchedule entries: {len(sched_rows)}")
        if sched_rows:
            for r in sched_rows:
                print(f"  id={r[0]}, entity={r[2]}, hash={r[3][:8]}...")

        # Check api_usage_log for schedule
        log_rows = (await session.execute(
            text("SELECT agent_name, cache_hit, COUNT(*) FROM api_usage_log WHERE agent_name = 'schedule' GROUP BY agent_name, cache_hit")
        )).fetchall()
        print("\napi_usage_log for schedule:")
        for row in log_rows:
            print(f"  agent={row[0]}, cache_hit={row[1]}, count={row[2]}")

        # Show agent_cache columns
        cols = (await session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'agent_cache' ORDER BY ordinal_position")
        )).fetchall()
        print(f"\nagent_cache columns: {[r[0] for r in cols]}")


if __name__ == "__main__":
    asyncio.run(main())
