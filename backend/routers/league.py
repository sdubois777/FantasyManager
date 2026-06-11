"""
League router — league tendencies, multi-year history, and auction bias analysis.

Endpoints:
  GET /league/tendencies          — positional bias + multi-year trends + manager patterns
  GET /league/history/seasons     — list of seasons with pick counts
  GET /league/history/{season}    — full draft results for one season

All endpoints require auth and scope data to user_id + user_league_id.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.dependencies import get_current_user, get_db
from backend.engines.valuation import get_market_context
from backend.models.user import User
from backend.repositories.league_auction_repo import (
    LeagueAuctionHistoryRepository,
)
from backend.repositories.player_repo import PlayerRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/league", tags=["league"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class PositionBias(BaseModel):
    position: str
    avg_league_price: float
    avg_fp_price: float
    avg_bias: float
    player_count: int


class BiasPlayer(BaseModel):
    id: str
    name: str
    position: Optional[str] = None
    market_value_league: Optional[float] = None
    market_value_fantasypros: Optional[float] = None
    bias: float
    bias_signal: str


class PositionTrend(BaseModel):
    season: int
    position: str
    avg_price: float
    max_price: int
    total_spent: int
    player_count: int


class ManagerTendency(BaseModel):
    manager_name: str
    position: str
    avg_spend: float
    total_spend: int
    picks: int


class LeagueTendenciesResponse(BaseModel):
    positional_biases: list[PositionBias]
    top_opportunities: list[BiasPlayer]
    top_traps: list[BiasPlayer]
    total_players_with_league_data: int
    seasons_available: list[int] = []
    positional_trends: list[PositionTrend] = []
    manager_tendencies: list[ManagerTendency] = []


class SeasonSummary(BaseModel):
    season: int
    pick_count: int
    total_spent: int
    source: str


class DraftPick(BaseModel):
    player_name: Optional[str] = None
    position: Optional[str] = None
    price: int
    manager_name: Optional[str] = None
    draft_pick_number: Optional[int] = None
    matched_to_db: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tendencies", response_model=LeagueTendenciesResponse)
async def get_league_tendencies(
    league_id: uuid.UUID = Query(..., description="user_leagues.id to scope data"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Positional bias breakdown plus multi-year trends and manager patterns."""
    history_repo = LeagueAuctionHistoryRepository(db)

    # Current bias analysis (from player.market_value_league — global, not scoped)
    players = await PlayerRepository(db).list_with_league_market_values()

    # Multi-year data from history table — scoped to user + league
    seasons_available = await history_repo.list_seasons(user.id, league_id)

    positional_trends = [
        PositionTrend(
            season=row.season_year,
            position=row.position,
            avg_price=round(float(row.avg_price), 1),
            max_price=int(row.max_price),
            total_spent=int(row.total_spent),
            player_count=int(row.player_count),
        )
        for row in await history_repo.position_trends(user.id, league_id)
    ]

    manager_tendencies = [
        ManagerTendency(
            manager_name=row.manager_name,
            position=row.position,
            avg_spend=round(float(row.avg_spend), 1),
            total_spend=int(row.total_spend),
            picks=int(row.picks),
        )
        for row in await history_repo.manager_tendencies(user.id, league_id)
    ]

    # Current season bias analysis
    positional_biases: list[PositionBias] = []
    top_opportunities: list[BiasPlayer] = []
    top_traps: list[BiasPlayer] = []

    if players:
        player_contexts = [(p, get_market_context(p)) for p in players]

        pos_data: dict[str, dict] = {}
        for p, mctx in player_contexts:
            pos = p.position
            if pos not in pos_data:
                pos_data[pos] = {"league_sum": 0.0, "fp_sum": 0.0, "bias_sum": 0.0, "count": 0}
            league = float(mctx["market_value_league"]) if mctx["market_value_league"] is not None else 0
            fp = float(mctx["market_value_fantasypros"]) if mctx["market_value_fantasypros"] is not None else 0
            bias = float(mctx["league_bias"]) if mctx["league_bias"] is not None else 0
            pos_data[pos]["league_sum"] += league
            pos_data[pos]["fp_sum"] += fp
            pos_data[pos]["bias_sum"] += bias
            pos_data[pos]["count"] += 1

        for pos in ["QB", "RB", "WR", "TE"]:
            d = pos_data.get(pos)
            if not d or d["count"] == 0:
                continue
            positional_biases.append(PositionBias(
                position=pos,
                avg_league_price=round(d["league_sum"] / d["count"], 1),
                avg_fp_price=round(d["fp_sum"] / d["count"], 1),
                avg_bias=round(d["bias_sum"] / d["count"], 1),
                player_count=d["count"],
            ))

        with_bias = [(p, m) for p, m in player_contexts if m["league_bias"] is not None]

        def _to_bias_player(p, mctx) -> BiasPlayer:
            return BiasPlayer(
                id=str(p.id),
                name=p.name,
                position=p.position,
                market_value_league=float(mctx["market_value_league"]) if mctx["market_value_league"] is not None else None,
                market_value_fantasypros=float(mctx["market_value_fantasypros"]) if mctx["market_value_fantasypros"] is not None else None,
                bias=float(mctx["league_bias"]),
                bias_signal=mctx["league_bias_signal"],
            )

        sorted_opps = sorted(with_bias, key=lambda x: float(x[1]["league_bias"]))
        top_opportunities = [_to_bias_player(p, m) for p, m in sorted_opps[:5] if float(m["league_bias"]) < -5]

        sorted_traps = sorted(with_bias, key=lambda x: float(x[1]["league_bias"]), reverse=True)
        top_traps = [_to_bias_player(p, m) for p, m in sorted_traps[:5] if float(m["league_bias"]) > 5]

    return LeagueTendenciesResponse(
        positional_biases=positional_biases,
        top_opportunities=top_opportunities,
        top_traps=top_traps,
        total_players_with_league_data=len(players),
        seasons_available=seasons_available,
        positional_trends=positional_trends,
        manager_tendencies=manager_tendencies,
    )


@router.get("/history/seasons", response_model=list[SeasonSummary])
async def get_history_seasons(
    league_id: uuid.UUID = Query(..., description="user_leagues.id to scope data"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all seasons with pick counts and total spend."""
    repo = LeagueAuctionHistoryRepository(db)
    rows = await repo.season_summaries(user.id, league_id)

    return [
        SeasonSummary(
            season=row.season_year,
            pick_count=row.pick_count,
            total_spent=int(row.total_spent or 0),
            source=row.source,
        )
        for row in rows
    ]


@router.get("/history/{season}", response_model=list[DraftPick])
async def get_history_season(
    season: int,
    league_id: uuid.UUID = Query(..., description="user_leagues.id to scope data"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full draft results for one season."""
    repo = LeagueAuctionHistoryRepository(db)
    records = await repo.list_picks(user.id, league_id, season)

    if not records:
        raise HTTPException(status_code=404, detail=f"No draft data for season {season}")

    return [
        DraftPick(
            player_name=r.player_name,
            position=r.position,
            price=r.price,
            manager_name=r.manager_name,
            draft_pick_number=r.draft_pick_number,
            matched_to_db=r.player_id is not None,
        )
        for r in records
    ]
