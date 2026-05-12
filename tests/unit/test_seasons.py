"""
tests/unit/test_seasons.py

All required named test cases from stage-01-foundation.md.
These tests use date mocking — never depend on the actual current date.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.utils.seasons import (
    get_analysis_seasons,
    get_analysis_year,
    get_current_season,
    get_draft_prep_window,
    get_previous_season,
)


# ---------------------------------------------------------------------------
# get_current_season()
# ---------------------------------------------------------------------------

def test_current_season_before_june_returns_previous_year():
    """In January–May, the current season is the previous calendar year."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 3, 15)
        assert get_current_season() == 2025


def test_current_season_after_june_returns_current_year():
    """In June–December, the current season is the current calendar year."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 7, 1)
        assert get_current_season() == 2026


def test_current_season_exactly_june_first_is_current_year():
    """June 1 is the exact boundary — should return current calendar year."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 6, 1)
        assert get_current_season() == 2026


def test_current_season_december_is_current_year():
    """December should return current calendar year (season ongoing)."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 12, 31)
        assert get_current_season() == 2026


# ---------------------------------------------------------------------------
# get_analysis_year()
# ---------------------------------------------------------------------------

def test_analysis_year_is_one_ahead_of_current():
    """get_analysis_year() always returns get_current_season() + 1."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 30)
        assert get_analysis_year() == get_current_season() + 1


def test_analysis_year_before_june():
    """In March 2026, analysis_year = 2026 (preparing for 2026 draft)."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 3, 15)
        assert get_analysis_year() == 2026


def test_analysis_year_after_june():
    """In July 2026, analysis_year = 2027 (preparing for 2027 draft)."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 7, 1)
        assert get_analysis_year() == 2027


# ---------------------------------------------------------------------------
# get_analysis_seasons()
# ---------------------------------------------------------------------------

def test_analysis_seasons_returns_correct_lookback():
    """get_analysis_seasons(3) returns exactly 3 seasons."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 30)
        seasons = get_analysis_seasons(3)
        assert len(seasons) == 3


def test_analysis_seasons_includes_current_season():
    """
    The current (most recently completed) season MUST be in the analysis window.
    In May 2026, current=2025 (completed season) — must be included.
    """
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 30)
        current = get_current_season()
        seasons = get_analysis_seasons(3)
        assert current in seasons


def test_analysis_seasons_correct_values_before_june():
    """In March 2026, current=2025, analysis_seasons(3) = [2023, 2024, 2025]."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 3, 15)
        seasons = get_analysis_seasons(3)
        assert seasons == [2023, 2024, 2025]


def test_analysis_seasons_correct_values_after_june():
    """In July 2026, current=2026, analysis_seasons(3) = [2024, 2025, 2026]."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 7, 1)
        seasons = get_analysis_seasons(3)
        assert seasons == [2024, 2025, 2026]


def test_analysis_seasons_five_season_lookback():
    """get_analysis_seasons(5) returns 5 seasons."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 30)
        seasons = get_analysis_seasons(5)
        assert len(seasons) == 5
        assert seasons == sorted(seasons)  # must be ascending
        assert seasons == [2021, 2022, 2023, 2024, 2025]


def test_analysis_seasons_includes_current_in_may():
    """In May 2026, current=2025, analysis should include 2025."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 15)
        seasons = get_analysis_seasons(3)
        assert get_current_season() in seasons
        assert len(seasons) == 3
        assert seasons == sorted(seasons)  # ascending order


def test_analysis_seasons_most_recent_is_current():
    """Most recent season in window = current season."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 15)
        seasons = get_analysis_seasons(3)
        assert max(seasons) == get_current_season()


def test_analysis_seasons_correct_count():
    """Lookback count is exact."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 5, 15)
        assert len(get_analysis_seasons(3)) == 3
        assert len(get_analysis_seasons(5)) == 5


# ---------------------------------------------------------------------------
# get_draft_prep_window()
# ---------------------------------------------------------------------------

def test_get_draft_prep_window_returns_all_fields():
    """get_draft_prep_window() must return all four expected keys."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 30)
        window = get_draft_prep_window()
        assert "current_season" in window
        assert "previous_season" in window
        assert "analysis_year" in window
        assert "analysis_seasons" in window
        assert isinstance(window["analysis_seasons"], list)


# ---------------------------------------------------------------------------
# Codebase scanner — no hardcoded years in agent files
# ---------------------------------------------------------------------------

def test_no_hardcoded_years_in_agent_files():
    """
    Scan all agent Python files for hardcoded year integers (2022-2029).
    Any found outside of seasons.py itself is a bug.

    Excludes:
    - seasons.py (the one allowed source of truth)
    - model strings (claude-haiku-4-5-20251001 contains 2025 — acceptable)
    - Comments referencing years for documentation purposes
    """
    agents_dir = Path(__file__).parent.parent.parent / "backend" / "agents"
    year_pattern = re.compile(r"\b(202[2-9])\b")
    # Model strings are OK — they contain year-like digits as part of the name
    model_pattern = re.compile(r"claude-[a-z]+-[\d]+-[\d]+-\w+")

    violations: list[str] = []

    for py_file in agents_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(content.splitlines(), start=1):
            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Remove model strings before checking
            cleaned = model_pattern.sub("", line)
            if year_pattern.search(cleaned):
                violations.append(f"{py_file.name}:{lineno}: {line.strip()}")

    assert not violations, (
        "Hardcoded year integers found in agent files:\n"
        + "\n".join(violations)
        + "\nFix: use get_current_season(), get_analysis_seasons(), or get_analysis_year()"
    )


# ---------------------------------------------------------------------------
# Seed script — no hardcoded years
# ---------------------------------------------------------------------------

def test_seed_nfl_data_uses_dynamic_seasons():
    """Verify no hardcoded [2022, 2023, 2024] exists in scripts/seed_nfl_data.py."""
    source = (Path(__file__).parent.parent.parent / "scripts" / "seed_nfl_data.py").read_text()
    assert "[2022, 2023, 2024]" not in source, "seed_nfl_data.py still has hardcoded [2022, 2023, 2024]"
    assert "[2023, 2024]" not in source, "seed_nfl_data.py still has hardcoded [2023, 2024]"


def test_get_analysis_seasons_returns_3_consecutive_seasons():
    """get_analysis_seasons(3) returns a list of 3 consecutive seasons."""
    with patch("backend.utils.seasons.date") as mock_date:
        mock_date.today.return_value = date(2026, 8, 1)
        seasons = get_analysis_seasons(3)
        assert len(seasons) == 3
        assert seasons[1] - seasons[0] == 1
        assert seasons[2] - seasons[1] == 1
