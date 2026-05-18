"""
Tests for prior season market value — rotation, seeding, API exposure.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.engines.market_values import sync_market_values


# ---------------------------------------------------------------------------
# Rotation — existing FP value moves to prior_season on refresh
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rotation_on_refresh():
    """When FP value changes, old value rotates to prior_season."""
    # Create a fake player with existing market_value_fantasypros
    fake_player = MagicMock()
    fake_player.name = "Patrick Mahomes"
    fake_player.market_value = Decimal("35")
    fake_player.market_value_fantasypros = Decimal("35")
    fake_player.market_value_prior_season = None
    fake_player.market_value_prior_season_year = None
    fake_player.market_value_confidence = "medium"
    fake_player.market_value_updated_at = None

    # Mock session that returns our fake player
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_player]
    mock_session.execute.return_value = mock_result

    # Mock scraper returning new value
    scraped = [{"name": "Patrick Mahomes", "avg_value": 40.0, "min_value": 35, "max_value": 45}]

    with patch(
        "backend.engines.market_values._scrape_in_thread",
        return_value=(scraped, 2026, True),
    ), patch(
        "backend.engines.market_values._store_metadata",
        new_callable=AsyncMock,
    ):
        result = await sync_market_values(mock_session)

    assert result["matched"] == 1
    # Old FP value should have rotated to prior_season
    assert fake_player.market_value_prior_season == Decimal("35")
    assert fake_player.market_value_prior_season_year == 2025  # year_used - 1
    # New value should be written
    assert fake_player.market_value_fantasypros == 40.0


@pytest.mark.asyncio
async def test_no_rotation_when_same_value():
    """No rotation when refreshed value equals existing value."""
    fake_player = MagicMock()
    fake_player.name = "Patrick Mahomes"
    fake_player.market_value = Decimal("35")
    fake_player.market_value_fantasypros = Decimal("35")
    fake_player.market_value_prior_season = None
    fake_player.market_value_prior_season_year = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_player]
    mock_session.execute.return_value = mock_result

    scraped = [{"name": "Patrick Mahomes", "avg_value": 35.0, "min_value": 30, "max_value": 40}]

    with patch(
        "backend.engines.market_values._scrape_in_thread",
        return_value=(scraped, 2026, True),
    ), patch(
        "backend.engines.market_values._store_metadata",
        new_callable=AsyncMock,
    ):
        await sync_market_values(mock_session)

    # Should NOT have rotated since value didn't change
    assert fake_player.market_value_prior_season is None


@pytest.mark.asyncio
async def test_no_rotation_when_no_prior_value():
    """No rotation when player has no existing FP value."""
    fake_player = MagicMock()
    fake_player.name = "Patrick Mahomes"
    fake_player.market_value = None
    fake_player.market_value_fantasypros = None
    fake_player.market_value_prior_season = None
    fake_player.market_value_prior_season_year = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fake_player]
    mock_session.execute.return_value = mock_result

    scraped = [{"name": "Patrick Mahomes", "avg_value": 40.0, "min_value": 35, "max_value": 45}]

    with patch(
        "backend.engines.market_values._scrape_in_thread",
        return_value=(scraped, 2026, True),
    ), patch(
        "backend.engines.market_values._store_metadata",
        new_callable=AsyncMock,
    ):
        await sync_market_values(mock_session)

    # No prior value to rotate
    assert fake_player.market_value_prior_season is None


# ---------------------------------------------------------------------------
# Valuation agent context includes prior_season_price
# ---------------------------------------------------------------------------

def test_valuation_agent_context_includes_prior_season():
    """_build_player_context includes prior_season_price when set."""
    from backend.agents.valuation_agent import ValuationAgent

    agent = ValuationAgent.__new__(ValuationAgent)

    player = MagicMock()
    player.name = "CeeDee Lamb"
    player.position = "WR"
    player.team_abbr = "DAL"
    player.age = 26
    player.tier = 1
    player.is_rookie = False
    player.recommended_bid_ceiling = Decimal("55")
    player.baseline_value = Decimal("50")
    player.market_value = Decimal("48")
    player.value_gap = Decimal("2")
    player.value_gap_signal = "aligned"
    player.ceiling_value = Decimal("60")
    player.floor_value = Decimal("35")
    player.market_value_fantasypros = Decimal("48")
    player.market_value_prior_season = Decimal("42")
    player.market_value_prior_season_year = 2025
    player.profile = None
    player.injury_profile = None
    player.schedule = None
    player.dependencies = []

    ctx = agent._build_player_context(player)

    assert ctx["market_value_fantasypros"] == 48.0
    assert ctx["prior_season_price"] == 42.0
