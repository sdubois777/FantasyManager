"""
League router — league tendencies and auction bias analysis.

Endpoints:
  GET /league/tendencies — positional bias breakdown + top opportunities/traps
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import AsyncSessionLocal
from backend.engines.valuation import get_market_context
from backend.models.player import Player

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/league", tags=["league"])


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


class LeagueTendenciesResponse(BaseModel):
    positional_biases: list[PositionBias]
    top_opportunities: list[BiasPlayer]
    top_traps: list[BiasPlayer]
    total_players_with_league_data: int


@router.get("/tendencies", response_model=LeagueTendenciesResponse)
async def get_league_tendencies():
    """Positional bias breakdown plus top opportunities and traps."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Player)
            .where(Player.market_value_league.isnot(None))
            .where(Player.position.in_(["QB", "RB", "WR", "TE"]))
        )
        players = result.scalars().all()

    if not players:
        return LeagueTendenciesResponse(
            positional_biases=[],
            top_opportunities=[],
            top_traps=[],
            total_players_with_league_data=0,
        )

    # Build market context for each player
    player_contexts: list[tuple] = []  # (player, mctx)
    for p in players:
        mctx = get_market_context(p)
        player_contexts.append((p, mctx))

    # Positional bias aggregation
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

    positional_biases = []
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

    # Top opportunities (league underpays — negative bias) and traps (league overpays)
    with_bias = [
        (p, mctx) for p, mctx in player_contexts
        if mctx["league_bias"] is not None
    ]

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

    # Opportunities: league underpays (most negative bias first)
    sorted_opps = sorted(with_bias, key=lambda x: float(x[1]["league_bias"]))
    top_opportunities = [_to_bias_player(p, m) for p, m in sorted_opps[:5] if float(m["league_bias"]) < -5]

    # Traps: league overpays (most positive bias first)
    sorted_traps = sorted(with_bias, key=lambda x: float(x[1]["league_bias"]), reverse=True)
    top_traps = [_to_bias_player(p, m) for p, m in sorted_traps[:5] if float(m["league_bias"]) > 5]

    return LeagueTendenciesResponse(
        positional_biases=positional_biases,
        top_opportunities=top_opportunities,
        top_traps=top_traps,
        total_players_with_league_data=len(players),
    )
