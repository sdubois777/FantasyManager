"""Debug Josh Allen's QB valuation."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.database import AsyncSessionLocal
from backend.models.player import Player, PlayerProfile
from backend.utils.seasons import get_analysis_year


async def main() -> None:
    yr = get_analysis_year()
    async with AsyncSessionLocal() as session:
        # Find all QBs with profiles
        players = (
            await session.execute(
                select(Player)
                .where(Player.position == "QB", Player.baseline_value.is_not(None))
                .options(selectinload(Player.profile))
                .order_by(Player.baseline_value.desc())
                .limit(10)
            )
        ).scalars().all()

        print(f"QBs with valuations (analysis_year={yr}):")
        for p in players:
            prof = p.profile
            if prof:
                b = prof.clean_season_baseline or {}
                print(f"  {p.name} ({p.team_abbr}): baseline_value=${float(p.baseline_value):.0f}, ppr={b.get('ppr_points')}, rec={b.get('receptions')}, yards={b.get('yards')}, tds={b.get('touchdowns')}")
            else:
                print(f"  {p.name}: no profile, baseline_value=${float(p.baseline_value):.0f}")


if __name__ == "__main__":
    asyncio.run(main())
