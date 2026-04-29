"""
NFL data integration — wraps nfl_data_py with a parquet cache layer.

Sync functions (fetch_*) are for scripts.
Async functions (get_*) are for the agent pipeline / FastAPI.
Cache lives in data/cache/ (gitignored).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import nfl_data_py as nfl

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache")
SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}


def _ensure_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(name: str) -> Path:
    _ensure_cache()
    return CACHE_DIR / f"{name}.parquet"


def _load_or_fetch(cache_name: str, fetch_fn) -> pd.DataFrame:
    path = _cache_path(cache_name)
    if path.exists():
        logger.debug("Cache hit: %s", cache_name)
        return pd.read_parquet(path)
    logger.info("Downloading: %s", cache_name)
    df = fetch_fn()
    df.to_parquet(path, index=False)
    return df


# ---------------------------------------------------------------------------
# Sync fetch functions
# ---------------------------------------------------------------------------

def fetch_weekly_stats(season: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"weekly_{season}",
        lambda: nfl.import_weekly_data([season]),
    )


def fetch_seasonal_data(season: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"seasonal_{season}",
        lambda: nfl.import_seasonal_data([season]),
    )


def fetch_snap_counts(season: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"snaps_{season}",
        lambda: nfl.import_snap_counts([season]),
    )


def fetch_schedules(season: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"schedules_{season}",
        lambda: nfl.import_schedules([season]),
    )


def fetch_players() -> pd.DataFrame:
    return _load_or_fetch("players", nfl.import_players)


def fetch_rosters(season: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"rosters_{season}",
        lambda: nfl.import_weekly_rosters([season]),
    )


def fetch_injuries(season: int) -> pd.DataFrame:
    return _load_or_fetch(
        f"injuries_{season}",
        lambda: nfl.import_injuries([season]),
    )


def fetch_ngs_data(stat_type: str, season: int) -> pd.DataFrame:
    """stat_type: 'passing' | 'receiving' | 'rushing'"""
    return _load_or_fetch(
        f"ngs_{stat_type}_{season}",
        lambda: nfl.import_ngs_data(stat_type, [season]),
    )


def compute_target_share(season: int) -> pd.DataFrame:
    """
    Derive per-player target share and air yards share from weekly data.
    Returns one row per player with season-level averages.
    """
    cache_name = f"target_share_{season}"
    path = _cache_path(cache_name)
    if path.exists():
        return pd.read_parquet(path)

    weekly = fetch_weekly_stats(season)

    # Skill positions only
    weekly = weekly[weekly["position"].isin(SKILL_POSITIONS)].copy()

    # Team-level targets per week (denominator for target share)
    team_targets = (
        weekly.groupby(["season", "week", "recent_team"])["targets"]
        .sum()
        .reset_index()
        .rename(columns={"targets": "team_targets"})
    )
    weekly = weekly.merge(team_targets, on=["season", "week", "recent_team"], how="left")

    # nfl_data_py already provides target_share and air_yards_share columns
    # Use them directly; fall back to manual calculation if absent
    if "target_share" not in weekly.columns:
        weekly["target_share"] = weekly["targets"] / weekly["team_targets"].replace(0, pd.NA)

    # Season-level aggregation
    agg = (
        weekly.groupby(["player_id", "player_name", "recent_team", "position"])
        .agg(
            games=("week", "count"),
            total_targets=("targets", "sum"),
            total_receptions=("receptions", "sum"),
            total_rec_yards=("receiving_yards", "sum"),
            total_rec_tds=("receiving_tds", "sum"),
            avg_target_share=("target_share", "mean"),
            total_air_yards=("receiving_air_yards", "sum"),
            avg_air_yards_share=("air_yards_share", "mean"),
            total_carries=("carries", "sum"),
            total_rush_yards=("rushing_yards", "sum"),
            total_rush_tds=("rushing_tds", "sum"),
            total_fantasy_points=("fantasy_points_ppr", "sum"),
        )
        .reset_index()
    )
    agg["season"] = season

    # PPR per game
    agg["ppr_per_game"] = agg["total_fantasy_points"] / agg["games"].replace(0, pd.NA)

    agg.to_parquet(path, index=False)
    return agg


def compute_snap_pct(season: int) -> pd.DataFrame:
    """
    Derive season-level average offensive snap percentage from weekly snap data.
    """
    cache_name = f"snap_pct_{season}"
    path = _cache_path(cache_name)
    if path.exists():
        return pd.read_parquet(path)

    snaps = fetch_snap_counts(season)

    # Keep only offensive snap data
    needed = ["player", "pfr_player_id", "position", "team", "week", "season",
              "offense_snaps", "offense_pct"]
    snaps = snaps[[c for c in needed if c in snaps.columns]].copy()
    snaps = snaps[snaps["position"].isin(SKILL_POSITIONS)]

    agg = (
        snaps.groupby(["player", "pfr_player_id", "position", "team"])
        .agg(
            games=("week", "count"),
            total_offense_snaps=("offense_snaps", "sum"),
            avg_snap_pct=("offense_pct", "mean"),
        )
        .reset_index()
    )
    agg["season"] = season
    agg.to_parquet(path, index=False)
    return agg


def get_player_season_summary(player_name: str, season: int) -> Optional[dict]:
    """
    Convenience lookup: return a dict of key stats for a named player in a season.
    Used for verification and agent context.
    """
    ts = compute_target_share(season)
    # Case-insensitive partial match
    mask = ts["player_name"].str.contains(player_name, case=False, na=False)
    if mask.sum() == 0:
        return None
    row = ts[mask].iloc[0]
    return row.to_dict()


# ---------------------------------------------------------------------------
# Async wrappers (use run_in_executor to avoid blocking the event loop)
# ---------------------------------------------------------------------------

async def get_weekly_stats(season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_weekly_stats, season)


async def get_seasonal_data(season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_seasonal_data, season)


async def get_snap_counts(season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_snap_counts, season)


async def get_schedules(season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_schedules, season)


async def get_players() -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_players)


async def get_rosters(season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_rosters, season)


async def get_ngs_data(stat_type: str, season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_ngs_data, stat_type, season)


async def get_injuries(season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_injuries, season)


async def get_target_share(season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, compute_target_share, season)


async def get_snap_pct(season: int) -> pd.DataFrame:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, compute_snap_pct, season)
