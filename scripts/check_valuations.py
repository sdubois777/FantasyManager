"""Spot-check bid ceilings after valuation re-run."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from backend.database import AsyncSessionLocal
from backend.models.player import Player


async def main() -> None:
    async with AsyncSessionLocal() as session:
        # Get top players by position
        for pos in ("RB", "WR", "QB", "TE"):
            players = (
                await session.execute(
                    select(Player)
                    .where(
                        Player.position == pos,
                        Player.recommended_bid_ceiling.is_not(None),
                    )
                    .order_by(Player.recommended_bid_ceiling.desc())
                    .limit(5)
                )
            ).scalars().all()

            print(f"\n--- Top 5 {pos} by bid ceiling ---")
            for p in players:
                ceiling = float(p.recommended_bid_ceiling or 0)
                sv = float(p.baseline_value or 0)
                tier = p.tier or "?"
                flag = " *** OVER $80 SANITY CAP ***" if ceiling > 80 else ""
                print(f"  {p.name} ({p.team_abbr}): T{tier}, sv=${sv:.0f}, ceiling=${ceiling:.2f}{flag}")

        # Check overall max ceiling
        all_players = (
            await session.execute(
                select(Player)
                .where(Player.recommended_bid_ceiling.is_not(None))
                .order_by(Player.recommended_bid_ceiling.desc())
                .limit(3)
            )
        ).scalars().all()
        print(f"\n--- Overall top 3 by ceiling ---")
        for p in all_players:
            print(f"  {p.name} ({p.position}): ${float(p.recommended_bid_ceiling):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
