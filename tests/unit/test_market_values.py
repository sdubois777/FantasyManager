"""
tests/unit/test_market_values.py

Tests for market value year resolution and sync engine.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.utils.seasons import (
    get_fantasypros_auction_year,
    get_best_available_auction_year,
)


# ---------------------------------------------------------------------------
# get_fantasypros_auction_year() — always returns current season
# ---------------------------------------------------------------------------

def test_fantasypros_year_march():
    """March — current_season=2026, always is_current=True."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 3, 15)
        year, is_current = get_fantasypros_auction_year()
        assert year == 2026
        assert is_current is True


def test_fantasypros_year_may():
    """May — current_season=2026, always is_current=True."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 6)
        year, is_current = get_fantasypros_auction_year()
        assert year == 2026
        assert is_current is True


def test_fantasypros_year_july_returns_current():
    """In months 7-12: returns current_season."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 7, 15)
        year, is_current = get_fantasypros_auction_year()
        assert year == 2026
        assert is_current is True


def test_fantasypros_year_august_returns_current():
    """August — peak draft prep season — uses current."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 8, 20)
        year, is_current = get_fantasypros_auction_year()
        assert year == 2026
        assert is_current is True


def test_fantasypros_year_december_returns_current():
    """December — still current season."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 12, 1)
        year, is_current = get_fantasypros_auction_year()
        assert year == 2026
        assert is_current is True


def test_fantasypros_year_january():
    """January — current_season=2025 (playoffs), still is_current=True."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 1, 15)
        year, is_current = get_fantasypros_auction_year()
        assert year == 2025
        assert is_current is True


# ---------------------------------------------------------------------------
# get_best_available_auction_year() — no fallback, always current season
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_best_available_returns_current_year():
    """Returns current season year with is_current=True."""
    async def mock_scraper(fmt, yr):
        return [{"name": f"p{i}"} for i in range(200)]

    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 1)
        values, year, is_current = await get_best_available_auction_year(
            mock_scraper, format="ppr"
        )

    assert len(values) == 200
    assert year == 2026
    assert is_current is True


@pytest.mark.asyncio
async def test_best_available_low_count_still_returns():
    """Even with fewer than 100 results, still returns current year (no fallback)."""
    async def mock_scraper(fmt, yr):
        return [{"name": f"p{i}"} for i in range(50)]

    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 1)
        values, year, is_current = await get_best_available_auction_year(
            mock_scraper, format="ppr"
        )

    assert len(values) == 50
    assert year == 2026
    assert is_current is True


@pytest.mark.asyncio
async def test_best_available_error_propagates():
    """Scraper errors propagate (no silent fallback to wrong year)."""
    async def mock_scraper(fmt, yr):
        raise RuntimeError("scrape failed")

    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 1)
        with pytest.raises(RuntimeError, match="scrape failed"):
            await get_best_available_auction_year(mock_scraper, format="ppr")


# ---------------------------------------------------------------------------
# No hardcoded years in market value modules
# ---------------------------------------------------------------------------

def test_no_hardcoded_years_in_market_values_engine():
    """No hardcoded years in backend/engines/market_values.py."""
    import re
    from pathlib import Path

    path = Path(__file__).parent.parent.parent / "backend" / "engines" / "market_values.py"
    content = path.read_text(encoding="utf-8")
    year_pattern = re.compile(r"\b(202[2-9])\b")

    violations = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if line.strip().startswith("#"):
            continue
        if year_pattern.search(line):
            violations.append(f"market_values.py:{lineno}: {line.strip()}")

    assert not violations, (
        "Hardcoded years found:\n" + "\n".join(violations)
    )


def test_no_hardcoded_years_in_refresh_script():
    """No hardcoded years in scripts/refresh_market_values.py."""
    import re
    from pathlib import Path

    path = Path(__file__).parent.parent.parent / "scripts" / "refresh_market_values.py"
    content = path.read_text(encoding="utf-8")
    year_pattern = re.compile(r"\b(202[2-9])\b")

    violations = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if line.strip().startswith("#"):
            continue
        if year_pattern.search(line):
            violations.append(f"refresh_market_values.py:{lineno}: {line.strip()}")

    assert not violations, (
        "Hardcoded years found:\n" + "\n".join(violations)
    )


def test_no_hardcoded_years_in_fantasypros_module():
    """No hardcoded years in backend/integrations/fantasypros.py."""
    import re
    from pathlib import Path

    path = Path(__file__).parent.parent.parent / "backend" / "integrations" / "fantasypros.py"
    content = path.read_text(encoding="utf-8")
    year_pattern = re.compile(r"\b(202[2-9])\b")

    violations = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if line.strip().startswith("#"):
            continue
        if year_pattern.search(line):
            violations.append(f"fantasypros.py:{lineno}: {line.strip()}")

    assert not violations, (
        "Hardcoded years found:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Sync engine (mocked scraper)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_market_values_returns_year_info():
    """sync_market_values result includes year and is_current_season."""
    from backend.engines.market_values import sync_market_values

    # Provide some player data so it doesn't hit the "empty" branch
    fake_values = [{"name": "Test Player", "avg_value": 10.0, "min_value": None, "max_value": None}]

    session = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()

    with patch("asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(
            return_value=(fake_values, 2026, True)
        )

        result = await sync_market_values(session, scoring_format="ppr")

    assert result["year"] == 2026
    assert result["is_current_season"] is True
    # Player won't match (empty DB) so it goes to unmatched
    assert result["unmatched"] == 1
