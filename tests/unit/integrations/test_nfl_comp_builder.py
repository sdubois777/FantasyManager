"""
tests/unit/integrations/test_nfl_comp_builder.py

Tests for the NFL comp builder that uses nfl_data_py (no R/cfbfastR).
"""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch

from backend.integrations.nfl_comp_builder import (
    build_comp_table,
    find_comps,
    get_draft_tier,
    get_tier_averages,
    grade_college_profile_by_pick,
)


# ---------------------------------------------------------------------------
# Draft tier mapping
# ---------------------------------------------------------------------------


def test_draft_tier_pick_1_is_elite():
    assert get_draft_tier(1) == "elite"


def test_draft_tier_pick_10_is_elite():
    assert get_draft_tier(10) == "elite"


def test_draft_tier_pick_11_is_strong():
    assert get_draft_tier(11) == "strong"


def test_draft_tier_pick_32_is_strong():
    assert get_draft_tier(32) == "strong"


def test_draft_tier_pick_33_is_average():
    assert get_draft_tier(33) == "average"


def test_draft_tier_pick_105_is_average():
    assert get_draft_tier(105) == "average"


def test_draft_tier_pick_106_is_weak():
    assert get_draft_tier(106) == "weak"


def test_draft_tier_pick_250_is_weak():
    assert get_draft_tier(250) == "weak"


def test_grade_college_profile_by_pick_uses_draft_tier():
    assert grade_college_profile_by_pick(1) == "elite"
    assert grade_college_profile_by_pick(15) == "strong"
    assert grade_college_profile_by_pick(50) == "average"
    assert grade_college_profile_by_pick(200) == "weak"


# ---------------------------------------------------------------------------
# Tier averages
# ---------------------------------------------------------------------------


def test_tier_averages_groups_by_position_and_tier():
    comp_df = pd.DataFrame([
        {"player_name": "A", "position": "WR", "capital_tier": "elite",
         "yr1_ppg": 10.0, "yr2_ppg": 14.0, "draft_year": 2020,
         "pick_number": 5, "capital_value": 85.0, "draft_round": 1},
        {"player_name": "B", "position": "WR", "capital_tier": "elite",
         "yr1_ppg": 12.0, "yr2_ppg": 16.0, "draft_year": 2021,
         "pick_number": 8, "capital_value": 76.0, "draft_round": 1},
        {"player_name": "C", "position": "RB", "capital_tier": "strong",
         "yr1_ppg": 8.0, "yr2_ppg": None, "draft_year": 2022,
         "pick_number": 20, "capital_value": 54.0, "draft_round": 1},
    ])

    avgs = get_tier_averages(comp_df)

    assert ("WR", "elite") in avgs
    assert avgs[("WR", "elite")]["yr1_avg_ppg"] == 11.0  # (10+12)/2
    assert avgs[("WR", "elite")]["yr2_avg_ppg"] == 15.0  # (14+16)/2
    assert avgs[("WR", "elite")]["sample_size"] == 2

    assert ("RB", "strong") in avgs
    assert avgs[("RB", "strong")]["yr1_avg_ppg"] == 8.0
    assert avgs[("RB", "strong")]["yr2_avg_ppg"] is None  # all NaN


def test_tier_averages_empty_table():
    assert get_tier_averages(pd.DataFrame()) == {}


# ---------------------------------------------------------------------------
# Find comps
# ---------------------------------------------------------------------------


def test_find_comps_returns_closest_picks():
    comp_df = pd.DataFrame([
        {"player_name": "Near", "position": "WR", "pick_number": 6,
         "yr1_ppg": 12.0, "yr2_ppg": 15.0, "draft_year": 2020,
         "capital_tier": "elite", "capital_value": 82.0, "draft_round": 1},
        {"player_name": "Far", "position": "WR", "pick_number": 100,
         "yr1_ppg": 5.0, "yr2_ppg": 6.0, "draft_year": 2020,
         "capital_tier": "average", "capital_value": 20.0, "draft_round": 3},
        {"player_name": "Medium", "position": "WR", "pick_number": 15,
         "yr1_ppg": 9.0, "yr2_ppg": 11.0, "draft_year": 2021,
         "capital_tier": "strong", "capital_value": 62.0, "draft_round": 1},
    ])

    comps = find_comps(comp_df, "WR", pick_number=5, n=2)
    assert len(comps) == 2
    assert comps[0]["name"] == "Near"  # pick 6, closest to 5
    assert comps[1]["name"] == "Medium"  # pick 15, second closest


def test_find_comps_filters_by_position():
    comp_df = pd.DataFrame([
        {"player_name": "WR1", "position": "WR", "pick_number": 10,
         "yr1_ppg": 10.0, "yr2_ppg": 12.0, "draft_year": 2020,
         "capital_tier": "elite", "capital_value": 72.0, "draft_round": 1},
        {"player_name": "RB1", "position": "RB", "pick_number": 10,
         "yr1_ppg": 15.0, "yr2_ppg": 18.0, "draft_year": 2020,
         "capital_tier": "elite", "capital_value": 72.0, "draft_round": 1},
    ])

    comps = find_comps(comp_df, "RB", pick_number=10, n=5)
    assert len(comps) == 1
    assert comps[0]["name"] == "RB1"


def test_find_comps_empty_table():
    assert find_comps(pd.DataFrame(), "WR", pick_number=5) == []


# ---------------------------------------------------------------------------
# Build comp table (mocked nfl_data calls)
# ---------------------------------------------------------------------------


def test_build_comp_table_structure():
    """Verify build_comp_table produces expected columns."""
    mock_picks = pd.DataFrame([
        {"pfr_player_name": "Test WR", "position": "WR", "pick": 5,
         "round": 1, "team": "LAC", "gsis_id": "00-001"},
    ])
    mock_seasonal = pd.DataFrame([
        {"player_id": "00-001", "player_display_name": "Test WR",
         "fantasy_points_ppr": 170.0, "games": 17},
    ])

    # Clear lru_cache before test
    build_comp_table.cache_clear()

    with patch("backend.integrations.nfl_comp_builder.nfl_data") as mock_nfl:
        mock_nfl.fetch_nfl_draft_picks.return_value = mock_picks
        mock_nfl.fetch_seasonal_data.return_value = mock_seasonal
        mock_nfl.get_draft_capital_value.return_value = 85.0

        result = build_comp_table(start_year=2020, end_year=2020)

    assert not result.empty
    assert "player_name" in result.columns
    assert "position" in result.columns
    assert "capital_tier" in result.columns
    assert "yr1_ppg" in result.columns
    assert "yr2_ppg" in result.columns

    row = result.iloc[0]
    assert row["player_name"] == "Test WR"
    assert row["capital_tier"] == "elite"  # pick 5 = elite
    assert row["yr1_ppg"] == 10.0  # 170/17

    # Clean up cache
    build_comp_table.cache_clear()
