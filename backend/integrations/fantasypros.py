"""
FantasyPros integration — auction values and ADP via Playwright.

FantasyPros uses JavaScript-rendered DataTables so we need a real browser.
Playwright launches headless Chromium, waits for the table, and parses it.

Scoring formats: 'ppr' | 'half_ppr' | 'standard'
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)

FP_BASE = "https://www.fantasypros.com/nfl"

AUCTION_URLS: dict[str, str] = {
    "ppr":      f"{FP_BASE}/auction-values/ppr.php",
    "half_ppr": f"{FP_BASE}/auction-values/half-point-ppr.php",
    "standard": f"{FP_BASE}/auction-values/standard.php",
}

ADP_URLS: dict[str, str] = {
    "ppr":      f"{FP_BASE}/adp/ppr-overall.php",
    "half_ppr": f"{FP_BASE}/adp/half-point-ppr-overall.php",
    "standard": f"{FP_BASE}/adp/overall.php",
}


def _clean_dollar(value: str) -> Optional[float]:
    try:
        return float(Decimal(value.replace("$", "").strip()))
    except (InvalidOperation, ValueError):
        return None


def _clean_float(value: str) -> Optional[float]:
    try:
        return float(value.strip())
    except ValueError:
        return None


async def get_auction_values(scoring_format: str = "half_ppr") -> list[dict]:
    """
    Scrape FantasyPros auction values for the given scoring format.

    Returns a list of dicts:
      {name, team, position, avg_value, min_value, max_value, scoring_format}

    avg_value is the consensus auction dollar value across experts.
    """
    from playwright.async_api import async_playwright

    url = AUCTION_URLS.get(scoring_format)
    if not url:
        raise ValueError(f"Unknown scoring format '{scoring_format}'. Use: {list(AUCTION_URLS)}")

    logger.info("Fetching FantasyPros auction values (%s) from %s", scoring_format, url)

    players: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)

            # Wait for the DataTable to render
            await page.wait_for_selector("table#data", timeout=20_000)

            # Some pages show a "show all" button — click it to get full list
            show_all = page.locator("select[name='data_length'] option[value='-1']")
            if await show_all.count() > 0:
                await page.select_option("select[name='data_length']", value="-1")
                await page.wait_for_timeout(1_500)

            rows = await page.query_selector_all("table#data tbody tr")

            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 5:
                    continue

                # Col layout: Rank | Player (with team/pos badge) | Avg | Min | Max
                # The player cell contains a link with the name plus separate spans for team/pos
                player_cell = cells[1]
                name_el = await player_cell.query_selector("a")
                name = (await name_el.inner_text()).strip() if name_el else (await player_cell.inner_text()).strip()

                team_el = await player_cell.query_selector("small")
                team_pos = (await team_el.inner_text()).strip() if team_el else ""
                # team_pos looks like "DAL - WR" or "WR - DAL"
                parts = [p.strip() for p in team_pos.replace("-", " ").split()]
                position = next((p for p in parts if p in {"QB", "RB", "WR", "TE", "K", "DST", "DEF"}), "")
                team = next((p for p in parts if p not in {"QB", "RB", "WR", "TE", "K", "DST", "DEF"} and len(p) <= 4), "")

                avg_raw   = (await cells[2].inner_text()).strip()
                min_raw   = (await cells[3].inner_text()).strip() if len(cells) > 3 else ""
                max_raw   = (await cells[4].inner_text()).strip() if len(cells) > 4 else ""

                players.append({
                    "name":           name,
                    "team":           team,
                    "position":       position,
                    "avg_value":      _clean_dollar(avg_raw),
                    "min_value":      _clean_dollar(min_raw),
                    "max_value":      _clean_dollar(max_raw),
                    "scoring_format": scoring_format,
                })

        finally:
            await browser.close()

    logger.info("Retrieved %d players from FantasyPros auction values", len(players))
    return players


async def get_adp(scoring_format: str = "half_ppr") -> list[dict]:
    """
    Scrape FantasyPros ADP for the given scoring format.

    Returns a list of dicts:
      {rank, name, team, position, bye, adp, best, worst, scoring_format}

    adp is the consensus average draft position across experts.
    """
    from playwright.async_api import async_playwright

    url = ADP_URLS.get(scoring_format)
    if not url:
        raise ValueError(f"Unknown scoring format '{scoring_format}'. Use: {list(ADP_URLS)}")

    logger.info("Fetching FantasyPros ADP (%s) from %s", scoring_format, url)

    players: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.wait_for_selector("table#data", timeout=20_000)

            show_all = page.locator("select[name='data_length'] option[value='-1']")
            if await show_all.count() > 0:
                await page.select_option("select[name='data_length']", value="-1")
                await page.wait_for_timeout(1_500)

            rows = await page.query_selector_all("table#data tbody tr")

            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 5:
                    continue

                # Col layout: Rank | Player | Team | POS | BYE | AVG | STDDEV | BEST | WORST | ...
                rank_raw = (await cells[0].inner_text()).strip()

                player_cell = cells[1]
                name_el = await player_cell.query_selector("a")
                name = (await name_el.inner_text()).strip() if name_el else (await player_cell.inner_text()).strip()

                team     = (await cells[2].inner_text()).strip() if len(cells) > 2 else ""
                position = (await cells[3].inner_text()).strip() if len(cells) > 3 else ""
                bye_raw  = (await cells[4].inner_text()).strip() if len(cells) > 4 else ""
                adp_raw  = (await cells[5].inner_text()).strip() if len(cells) > 5 else ""
                best_raw = (await cells[7].inner_text()).strip() if len(cells) > 7 else ""
                worst_raw = (await cells[8].inner_text()).strip() if len(cells) > 8 else ""

                players.append({
                    "rank":           _clean_float(rank_raw),
                    "name":           name,
                    "team":           team,
                    "position":       position,
                    "bye":            _clean_float(bye_raw),
                    "adp":            _clean_float(adp_raw),
                    "best":           _clean_float(best_raw),
                    "worst":          _clean_float(worst_raw),
                    "scoring_format": scoring_format,
                })

        finally:
            await browser.close()

    logger.info("Retrieved %d players from FantasyPros ADP", len(players))
    return players


async def get_market_values(scoring_format: str = "half_ppr") -> dict[str, dict]:
    """
    Fetch both auction values and ADP, merge by name, return keyed by player name.
    This is the primary entry point for the draft bible market_value fields.
    """
    auction, adp = await asyncio.gather(
        get_auction_values(scoring_format),
        get_adp(scoring_format),
    )

    adp_lookup = {p["name"].lower(): p for p in adp}

    merged: dict[str, dict] = {}
    for p in auction:
        key = p["name"].lower()
        adp_data = adp_lookup.get(key, {})
        merged[p["name"]] = {
            "name":              p["name"],
            "team":              p["team"],
            "position":          p["position"],
            "auction_value":     p["avg_value"],
            "auction_min":       p["min_value"],
            "auction_max":       p["max_value"],
            "adp":               adp_data.get("adp"),
            "adp_best":          adp_data.get("best"),
            "adp_worst":         adp_data.get("worst"),
            "scoring_format":    scoring_format,
        }

    return merged


import asyncio  # noqa: E402 — needed for gather at module level
