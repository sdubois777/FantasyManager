"""
Preferences router — watchlist and draft strategy management.

Endpoints:
  GET    /preferences/watchlist      — list watchlist player IDs
  POST   /preferences/watchlist      — add player to watchlist
  DELETE /preferences/watchlist/{id}  — remove player from watchlist
  GET    /preferences/strategy       — get active draft strategy
  PUT    /preferences/strategy       — set draft strategy
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select

from backend.core.dependencies import get_current_user
from backend.database import AsyncSessionLocal
from backend.models.user import User
from backend.models.user_preference import UserPreference

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preferences", tags=["preferences"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class WatchlistItem(BaseModel):
    id: str
    player_id: str
    added_at: Optional[str] = None


class WatchlistResponse(BaseModel):
    items: list[WatchlistItem]
    total: int


class AddWatchlistRequest(BaseModel):
    player_id: str


class StrategyResponse(BaseModel):
    strategy: Optional[str] = None


class SetStrategyRequest(BaseModel):
    strategy: str  # "hero_rb" / "zero_rb" / "stars_and_scrubs" / "balanced"


# ---------------------------------------------------------------------------
# Watchlist endpoints
# ---------------------------------------------------------------------------

@router.get("/watchlist", response_model=WatchlistResponse)
async def get_watchlist(user: User = Depends(get_current_user)):
    """List all watchlist player IDs for current user."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserPreference)
            .where(UserPreference.preference_type == "watchlist")
            .where(UserPreference.user_id == user.id)
            .order_by(UserPreference.created_at.desc())
        )
        prefs = result.scalars().all()

    items = [
        WatchlistItem(
            id=str(p.id),
            player_id=p.entity_id or "",
            added_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in prefs
    ]
    return WatchlistResponse(items=items, total=len(items))


@router.post("/watchlist", response_model=WatchlistItem, status_code=201)
async def add_to_watchlist(body: AddWatchlistRequest, user: User = Depends(get_current_user)):
    """Add a player to the watchlist."""
    async with AsyncSessionLocal() as session:
        # Check if already in watchlist for this user
        existing = await session.execute(
            select(UserPreference)
            .where(UserPreference.preference_type == "watchlist")
            .where(UserPreference.entity_id == body.player_id)
            .where(UserPreference.user_id == user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Player already in watchlist")

        pref = UserPreference(
            preference_type="watchlist",
            entity_id=body.player_id,
            user_id=user.id,
            value={},
        )
        session.add(pref)
        await session.commit()
        await session.refresh(pref)

    return WatchlistItem(
        id=str(pref.id),
        player_id=pref.entity_id or "",
        added_at=pref.created_at.isoformat() if pref.created_at else None,
    )


@router.delete("/watchlist/{player_id}", status_code=204)
async def remove_from_watchlist(player_id: str, user: User = Depends(get_current_user)):
    """Remove a player from the watchlist."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(UserPreference)
            .where(UserPreference.preference_type == "watchlist")
            .where(UserPreference.entity_id == player_id)
            .where(UserPreference.user_id == user.id)
        )
        await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Player not in watchlist")


# ---------------------------------------------------------------------------
# Strategy endpoints
# ---------------------------------------------------------------------------

VALID_STRATEGIES = {"hero_rb", "zero_rb", "stars_and_scrubs", "balanced"}


@router.get("/strategy", response_model=StrategyResponse)
async def get_strategy(user: User = Depends(get_current_user)):
    """Get the active draft strategy for current user."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserPreference)
            .where(UserPreference.preference_type == "strategy")
            .where(UserPreference.user_id == user.id)
            .limit(1)
        )
        pref = result.scalar_one_or_none()

    strategy = None
    if pref and pref.value:
        strategy = pref.value.get("strategy")

    return StrategyResponse(strategy=strategy)


@router.put("/strategy", response_model=StrategyResponse)
async def set_strategy(body: SetStrategyRequest, user: User = Depends(get_current_user)):
    """Set the draft strategy for current user."""
    if body.strategy not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy. Must be one of: {sorted(VALID_STRATEGIES)}",
        )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserPreference)
            .where(UserPreference.preference_type == "strategy")
            .where(UserPreference.user_id == user.id)
            .limit(1)
        )
        pref = result.scalar_one_or_none()

        if pref:
            pref.value = {"strategy": body.strategy}
        else:
            pref = UserPreference(
                preference_type="strategy",
                entity_id=None,
                user_id=user.id,
                value={"strategy": body.strategy},
            )
            session.add(pref)

        await session.commit()

    return StrategyResponse(strategy=body.strategy)
