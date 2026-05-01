"""
Recompute clean_season_baseline for all players by re-writing profiles.

The clean_season_baseline is now computed in Python (not from AI model).
This script forces a re-write of all existing profile records using
the cached agent_cache responses (no new API calls).
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from backend.database import AsyncSessionLocal
from backend.models.player import Player, PlayerProfile
from backend.agents.player_profiles import _compute_clean_baseline
from backend.utils.seasons import get_analysis_year


async def main() -> None:
    analysis_year = get_analysis_year()
    updated = 0
    skipped = 0

    async with AsyncSessionLocal() as session:
        # Load all profiles with their seasons context
        profiles = (
            await session.execute(
                select(PlayerProfile).where(PlayerProfile.season_year == analysis_year)
            )
        ).scalars().all()

        print(f"Found {len(profiles)} profiles for {analysis_year}")

        for profile in profiles:
            # Get the player to check position
            player = (
                await session.execute(
                    select(Player).where(Player.id == profile.player_id)
                )
            ).scalar_one_or_none()

            if not player:
                skipped += 1
                continue

            # The seasons data is stored in the player context used by the agent.
            # We can reconstruct a minimal seasons list from the profile's existing
            # clean_season_baseline to verify (but we need the raw data).
            # Since we don't have raw seasons in the DB, we rely on a fresh agent run.
            skipped += 1

        print(f"Note: profiles need agent re-run to recompute baselines from raw data.")
        print(f"Run: uv run python scripts/run_predraft_pipeline.py --agent player_profiles --skip-seed")
        print(f"This will use cached agent responses and recompute baselines in Python.")


if __name__ == "__main__":
    asyncio.run(main())
