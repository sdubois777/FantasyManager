"""
Pipeline router — manual triggers for each agent stage via HTTP POST.
Used for development, re-runs, and spot-checks. Not called by the UI.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineResponse(BaseModel):
    status: str
    message: str
    details: dict | list = {}


@router.post("/run-team-systems", response_model=PipelineResponse)
async def run_team_systems(background_tasks: BackgroundTasks):
    """
    Trigger Team Systems Agent for all 32 NFL teams.
    Runs in the background — returns immediately.
    Check logs for progress.
    """
    from backend.agents.team_systems import run_all_teams

    async def _run():
        results = await run_all_teams(concurrency=4)
        success = sum(1 for v in results.values() if v)
        logger.info("Team Systems pipeline finished: %d/32 succeeded", success)

    background_tasks.add_task(_run)
    return PipelineResponse(
        status="started",
        message="Team Systems Agent running for all 32 teams. Check logs for progress.",
    )


@router.post("/run-roster-changes", response_model=PipelineResponse)
async def run_roster_changes(background_tasks: BackgroundTasks):
    """Trigger Roster Changes Agent for all 32 teams. Runs in background."""
    from backend.agents.roster_changes import run_all_teams

    async def _run():
        results = await run_all_teams(concurrency=3)
        total = sum(results.values())
        logger.info("Roster Changes pipeline finished: %d total flags", total)

    background_tasks.add_task(_run)
    return PipelineResponse(
        status="started",
        message="Roster Changes Agent running for all 32 teams.",
    )


@router.post("/run-roster-changes/{team_abbr}", response_model=PipelineResponse)
async def run_roster_changes_single(team_abbr: str):
    """Run Roster Changes Agent for a single team synchronously."""
    from backend.agents.roster_changes import run_for_team
    from backend.agents.team_systems import NFL_TEAMS

    team = team_abbr.upper()
    if team not in NFL_TEAMS:
        raise HTTPException(status_code=400, detail=f"Unknown team: {team_abbr}")

    flags = await run_for_team(team)
    return PipelineResponse(
        status="complete",
        message=f"Roster Changes Agent completed for {team}: {len(flags)} flags",
        details=flags,
    )


@router.post("/run-team-systems/{team_abbr}", response_model=PipelineResponse)
async def run_team_systems_single(team_abbr: str):
    """
    Run Team Systems Agent for a single team. Runs synchronously — blocks until done.
    Good for spot-checking individual teams.
    """
    from backend.agents.team_systems import run_for_team, NFL_TEAMS

    team = team_abbr.upper()
    if team not in NFL_TEAMS:
        raise HTTPException(status_code=400, detail=f"Unknown team: {team_abbr}")

    data = await run_for_team(team)
    if data is None:
        raise HTTPException(status_code=500, detail=f"Agent failed for {team} — check logs")

    return PipelineResponse(
        status="complete",
        message=f"Team Systems Agent completed for {team}",
        details=data,
    )


@router.post("/sync-yahoo-players", response_model=PipelineResponse)
async def sync_yahoo_players():
    """
    Pull Yahoo player universe and match IDs to draft bible records.
    Updates yahoo_player_id on matched player rows.
    Requires YAHOO_REFRESH_TOKEN to be set in .env.
    """
    from backend.database import AsyncSessionLocal
    from backend.integrations.yahoo_api import sync_yahoo_player_ids

    async with AsyncSessionLocal() as session:
        result = await sync_yahoo_player_ids(session)

    return PipelineResponse(
        status="complete",
        message=(
            f"Yahoo player sync done — "
            f"{result['matched']} matched, {result['unmatched']} unmatched"
        ),
        details=result,
    )


@router.post("/sync-league-settings", response_model=PipelineResponse)
async def sync_league_settings():
    """
    Pull league settings from Yahoo and upsert into league_settings table.
    Requires YAHOO_REFRESH_TOKEN to be set in .env.
    """
    from backend.database import AsyncSessionLocal
    from backend.integrations.yahoo_api import sync_league_settings as _sync

    async with AsyncSessionLocal() as session:
        result = await _sync(session)

    return PipelineResponse(
        status="complete",
        message=f"League settings synced — {result['league_name']} ({result['scoring_format']}, {result['team_count']} teams)",
        details=result,
    )
