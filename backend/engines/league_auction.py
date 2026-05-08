"""
League Auction Engine — import and manage historical league auction prices.

Three entry points:
  1. import_league_auction_csv()  — Parse CSV from Yahoo Draft Recap copy-paste
  2. sync_league_auction_from_yahoo() — Pull from Yahoo API (August+)
  3. refresh_market_value_league() — Set player.market_value_league from history table
"""
from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.integrations.nfl_data import normalize_player_name
from backend.models.league_auction_history import LeagueAuctionHistory
from backend.models.player import Player

logger = logging.getLogger(__name__)


async def import_league_auction_csv(
    session: AsyncSession,
    csv_path: str | Path,
    season_year: int,
) -> dict:
    """
    Parse CSV from Yahoo Draft Recap copy-paste and import into league_auction_history.

    Supports flexible formats:
      - player_name,position,price  (minimal)
      - player_name,position,team,price  (with team)
      - Tab or comma separated
      - Rows with extra columns (takes name from col 0, price from last numeric col)

    Returns: {matched: int, unmatched: int, unmatched_names: list[str]}
    """
    path = Path(csv_path)
    raw_text = path.read_text(encoding="utf-8-sig")

    # Detect delimiter
    delimiter = "\t" if "\t" in raw_text.split("\n")[0] else ","

    rows = list(csv.reader(io.StringIO(raw_text), delimiter=delimiter))

    # Skip header row if present
    if rows and rows[0] and not _looks_like_price(rows[0][-1]):
        rows = rows[1:]

    # Load all players for matching
    result = await session.execute(select(Player))
    all_players = result.scalars().all()
    name_map: dict[str, Player] = {}
    for p in all_players:
        name_map[normalize_player_name(p.name)] = p

    matched = 0
    unmatched = 0
    unmatched_names: list[str] = []

    for row in rows:
        if not row or len(row) < 2:
            continue

        player_name = row[0].strip()
        # Find price: last column that looks numeric
        price = None
        for cell in reversed(row[1:]):
            cell = cell.strip().replace("$", "").replace(",", "")
            if cell.isdigit():
                price = int(cell)
                break

        if price is None:
            continue

        norm = normalize_player_name(player_name)
        player = name_map.get(norm)
        if not player:
            unmatched += 1
            unmatched_names.append(player_name)
            continue

        # Upsert into history table
        stmt = pg_insert(LeagueAuctionHistory).values(
            id=uuid.uuid4(),
            player_id=player.id,
            season_year=season_year,
            price=price,
            source="manual_csv",
        ).on_conflict_do_update(
            constraint="uq_auction_player_season_source",
            set_={"price": price},
        )
        await session.execute(stmt)
        matched += 1

    await session.commit()
    logger.info(
        "League auction CSV import: %d matched, %d unmatched (year=%d)",
        matched, unmatched, season_year,
    )
    return {
        "matched": matched,
        "unmatched": unmatched,
        "unmatched_names": unmatched_names,
    }


async def sync_league_auction_from_yahoo(
    session: AsyncSession,
    season_year: int,
) -> dict:
    """
    Pull draft results from Yahoo API and import into league_auction_history.
    Requires active league + YAHOO_LEAGUE_ID. For August+.
    """
    from backend.integrations.yahoo_api import get_draft_results

    draft_results = await get_draft_results()
    if not draft_results:
        return {"matched": 0, "unmatched": 0, "error": "No draft results from Yahoo"}

    # Build yahoo_player_id -> Player mapping
    result = await session.execute(
        select(Player).where(Player.yahoo_player_id.isnot(None))
    )
    yahoo_map: dict[str, Player] = {}
    for p in result.scalars().all():
        yahoo_map[p.yahoo_player_id] = p

    matched = 0
    unmatched = 0
    unmatched_names: list[str] = []

    for pick in draft_results:
        yahoo_id = pick.get("player_key") or pick.get("yahoo_player_id")
        price = pick.get("cost") or pick.get("price")
        team_key = pick.get("team_key")

        if yahoo_id is None or price is None:
            continue

        player = yahoo_map.get(str(yahoo_id))
        if not player:
            unmatched += 1
            unmatched_names.append(pick.get("player_name", yahoo_id))
            continue

        stmt = pg_insert(LeagueAuctionHistory).values(
            id=uuid.uuid4(),
            player_id=player.id,
            season_year=season_year,
            price=int(price),
            team_key=str(team_key) if team_key else None,
            source="yahoo",
        ).on_conflict_do_update(
            constraint="uq_auction_player_season_source",
            set_={"price": int(price), "team_key": str(team_key) if team_key else None},
        )
        await session.execute(stmt)
        matched += 1

    await session.commit()
    logger.info(
        "League auction Yahoo import: %d matched, %d unmatched (year=%d)",
        matched, unmatched, season_year,
    )
    return {
        "matched": matched,
        "unmatched": unmatched,
        "unmatched_names": unmatched_names,
    }


async def refresh_market_value_league(
    session: AsyncSession,
    season_year: int | None = None,
) -> dict:
    """
    Set player.market_value_league from the latest year in league_auction_history.
    If season_year is None, uses the most recent year in the history table.

    Returns: {updated: int, year_used: int | None}
    """
    # Determine which year to use
    if season_year is None:
        result = await session.execute(
            select(func.max(LeagueAuctionHistory.season_year))
        )
        season_year = result.scalar()
        if season_year is None:
            return {"updated": 0, "year_used": None}

    # Get all history records for this year
    result = await session.execute(
        select(LeagueAuctionHistory)
        .where(LeagueAuctionHistory.season_year == season_year)
    )
    records = result.scalars().all()

    # Build player_id -> price mapping
    price_map: dict[uuid.UUID, int] = {}
    for rec in records:
        price_map[rec.player_id] = rec.price

    if not price_map:
        return {"updated": 0, "year_used": season_year}

    # Update players
    player_ids = list(price_map.keys())
    result = await session.execute(
        select(Player).where(Player.id.in_(player_ids))
    )
    players = result.scalars().all()

    updated = 0
    for p in players:
        from decimal import Decimal
        p.market_value_league = Decimal(str(price_map[p.id]))
        updated += 1

    await session.commit()
    logger.info(
        "Refreshed market_value_league for %d players (year=%d)", updated, season_year
    )
    return {"updated": updated, "year_used": season_year}


def _looks_like_price(value: str) -> bool:
    """Check if a string looks like a price (numeric, possibly with $ prefix)."""
    cleaned = value.strip().replace("$", "").replace(",", "")
    return cleaned.isdigit()
