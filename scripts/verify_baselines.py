"""Quick spot check on clean_season_baseline correctness."""
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


CHECK_PLAYERS = ["Saquon Barkley", "Justin Jefferson", "Brock Bowers", "Ja'Marr Chase", "Christian McCaffrey"]


async def main() -> None:
    yr = get_analysis_year()
    async with AsyncSessionLocal() as session:
        for name in CHECK_PLAYERS:
            last = name.split()[-1]
            player = (
                await session.execute(
                    select(Player)
                    .where(Player.name.ilike(f"%{last}%"))
                    .options(selectinload(Player.profile))
                )
            ).scalars().first()
            if not player:
                print(f"{name}: NOT FOUND")
                continue
            p = player.profile
            if not p:
                print(f"{name}: no profile")
                continue
            b = p.clean_season_baseline or {}
            ppr = b.get("ppr_points", "N/A")
            yards = b.get("yards", "N/A")
            rec = b.get("receptions", "N/A")
            tds = b.get("touchdowns", "N/A")
            # Verify formula
            if isinstance(ppr, (int, float)) and isinstance(rec, (int, float)):
                expected = rec * 1.0 + (yards or 0) * 0.1 + (tds or 0) * 6.0
                match = abs(float(ppr) - expected) < 2.0
                print(f"{player.name} ({player.team_abbr}): ppr={ppr}, yards={yards}, rec={rec}, tds={tds} | formula_match={match}")
            else:
                print(f"{player.name}: ppr={ppr}, yards={yards}")


if __name__ == "__main__":
    asyncio.run(main())
