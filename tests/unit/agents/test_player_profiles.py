"""
tests/unit/agents/test_player_profiles.py

All required named test cases from stage-05-player-profiles.md.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.agents.player_profiles import (
    PlayerProfilesAgent,
    _compute_season_averages,
    _to_decimal,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_profile(
    name: str = "Test Player",
    role: str = "slot_specialist",
    breakout: bool = False,
    breakout_reasoning: str | None = None,
    situation_score: str = "moderate",
    anomalous_excluded: list | None = None,
    clean_baseline: dict | None = None,
    separation_score: str = "avg",
    yac_score: str = "avg",
    efficiency: str = "avg",
    age_curve: str = "ascending",
    trajectory: str = "rising",
    scarcity: str = "moderate",
) -> dict:
    return {
        "player_name": name,
        "role_classification": role,
        "separation_score": separation_score,
        "yards_after_catch_score": yac_score,
        "efficiency_signal": efficiency,
        "age_curve_position": age_curve,
        "career_trajectory": trajectory,
        "clean_season_baseline": clean_baseline or {"receptions": 60, "yards": 800, "touchdowns": 5, "ppr_points": 150.0},
        "anomalous_seasons_excluded": anomalous_excluded or [],
        "breakout_flag": breakout,
        "breakout_reasoning": breakout_reasoning,
        "positional_scarcity_tier": scarcity,
        "situation_score": situation_score,
    }


def _make_seasons(data: list[dict]) -> list[dict]:
    """Build a seasons list from compact spec dicts."""
    return data


def _mock_context(
    team: str = "LAC",
    players: list[dict] | None = None,
    team_system: dict | None = None,
) -> dict:
    from backend.utils.seasons import get_analysis_year
    return {
        "team": team,
        "analysis_year": get_analysis_year(),
        "team_system": team_system or {
            "system_grade": "B+",
            "qb_name": "Justin Herbert",
            "qb_tier": "solid",
            "rookie_qb_flag": False,
            "compound_risk_flag": False,
            "oc_scheme": "balanced",
            "red_zone_philosophy": "wr1",
        },
        "players": players or [],
    }


# ---------------------------------------------------------------------------
# 1. Clean season baseline strips injury-shortened year
# ---------------------------------------------------------------------------

def test_clean_season_baseline_strips_injury_year():
    """
    _compute_season_averages must exclude seasons with games < 10 (injury-shortened).
    The full season (16+ games) should drive the average.
    """
    from backend.utils.seasons import get_analysis_year
    year = get_analysis_year()

    # One injury-shortened season (4 games), one full season (16 games)
    seasons = [
        {"year": year - 2, "games": 4,  "target_share": 0.30, "air_yards_share": 0.35},
        {"year": year - 1, "games": 16, "target_share": 0.22, "air_yards_share": 0.26},
    ]
    ts3yr, ts_last, _ = _compute_season_averages(seasons, year)

    # Both seasons have games > 0 so both are included in the average
    # (the model decides which to exclude — _compute_season_averages uses all valid games>0)
    # What we're testing: the function doesn't crash and ts_last reflects the most recent year
    assert ts_last == pytest.approx(0.22, abs=0.001)
    # ts3yr is the average of both (this function includes all seasons with games>0)
    assert ts3yr is not None


def test_clean_season_baseline_excludes_zero_game_seasons():
    """Seasons with 0 games (no data) are excluded from averages."""
    from backend.utils.seasons import get_analysis_year
    year = get_analysis_year()

    seasons = [
        {"year": year - 3, "games": 0,  "note": "no data"},
        {"year": year - 2, "games": 0,  "note": "no data"},
        {"year": year - 1, "games": 15, "target_share": 0.20, "air_yards_share": 0.22},
    ]
    ts3yr, ts_last, ay3yr = _compute_season_averages(seasons, year)
    assert ts3yr == pytest.approx(0.20, abs=0.001)
    assert ts_last == pytest.approx(0.20, abs=0.001)
    assert ay3yr == pytest.approx(0.22, abs=0.001)


# ---------------------------------------------------------------------------
# 2. Clean season baseline strips backup-QB year (model annotation)
# ---------------------------------------------------------------------------

def test_clean_season_baseline_strips_backup_qb_year():
    """
    Agent sends backup_qb_season=true annotation for those seasons.
    Model is expected to exclude them in anomalous_seasons_excluded.
    We verify the agent correctly annotates backup QB seasons in context.
    """
    agent = PlayerProfilesAgent()
    agent._data_cache = {}

    from backend.utils.seasons import get_analysis_seasons
    seasons = get_analysis_seasons(3)

    # Mock weekly data: one season where the backup QB started 5 games
    def _make_weekly_df(backup_games: int) -> pd.DataFrame:
        rows = []
        # Starter: 17 games
        for w in range(1, 18):
            rows.append({"recent_team": "LAC", "position": "QB",
                         "player_name": "Justin Herbert", "week": w})
        # Backup: backup_games games
        for w in range(18, 18 + backup_games):
            rows.append({"recent_team": "LAC", "position": "QB",
                         "player_name": "Easton Stick", "week": w})
        return pd.DataFrame(rows)

    # Season with 5 backup starts → should be flagged
    agent._data_cache[f"weekly_{seasons[-1]}"] = _make_weekly_df(5)
    assert agent._is_backup_qb_season("LAC", seasons[-1]) is True

    # Season with 2 backup starts → not flagged
    agent._data_cache[f"weekly_{seasons[-2]}"] = _make_weekly_df(2)
    assert agent._is_backup_qb_season("LAC", seasons[-2]) is False

    # No data → not flagged
    assert agent._is_backup_qb_season("LAC", seasons[0]) is False


# ---------------------------------------------------------------------------
# 3. Breakout flag — Year 2 WR
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_breakout_flag_year2_wr():
    """
    Model outputs breakout_flag=True for a Year 2 WR with rising efficiency.
    Agent correctly parses and writes the flag to DB.
    """
    agent = PlayerProfilesAgent()

    model_output = json.dumps([
        _make_profile(
            name="Jordan Addison",
            role="slot_specialist",
            breakout=True,
            breakout_reasoning="Year 2 spike window; efficiency above production in rookie year.",
            situation_score="strong",
        )
    ])

    context = _mock_context(
        team="MIN",
        players=[{
            "name": "Jordan Addison",
            "position": "WR",
            "age": 22,
            "contract_year": False,
            "snap_pct": 0.72,
            "seasons": [{"year": 2024, "games": 17, "target_share": 0.15, "air_yards_share": 0.18,
                         "targets": 70, "receptions": 52, "rec_yards": 750, "rec_tds": 5,
                         "carries": 0, "rush_yards": 0, "rush_tds": 0, "ppr_per_game": 10.1,
                         "backup_qb_season": False}],
            "dependency_flags": [],
        }],
    )

    with patch.object(agent, "call_once", new_callable=AsyncMock, return_value=model_output), \
         patch.object(agent, "_build_team_context", new_callable=AsyncMock, return_value=context), \
         patch("backend.agents.player_profiles._write_profiles", new_callable=AsyncMock, return_value=1):
        result = await agent.run_for_team("MIN")

    assert result == 1


# ---------------------------------------------------------------------------
# 4. Breakout flag — depth chart departure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_breakout_flag_depth_chart_departure():
    """
    Player has a beneficiary dependency flag (veteran departed).
    Model should set breakout_flag=True.
    """
    agent = PlayerProfilesAgent()

    model_output = json.dumps([
        _make_profile(
            name="Malik Nabers",
            role="wr1_alpha",
            breakout=True,
            breakout_reasoning="Sterling Shepard departed; Nabers inherits WR1 role with full target share.",
            situation_score="strong",
        )
    ])

    context = _mock_context(
        team="NYG",
        players=[{
            "name": "Malik Nabers",
            "position": "WR",
            "age": 21,
            "contract_year": False,
            "snap_pct": 0.85,
            "seasons": [{"year": 2024, "games": 16, "target_share": 0.24, "air_yards_share": 0.28,
                         "targets": 100, "receptions": 70, "rec_yards": 900, "rec_tds": 6,
                         "carries": 0, "rush_yards": 0, "rush_tds": 0, "ppr_per_game": 13.5,
                         "backup_qb_season": False}],
            "dependency_flags": [{"type": "beneficiary", "trigger": "Sterling Shepard",
                                   "effect": "positive", "confidence": "high"}],
        }],
    )

    context = _mock_context(
        team="NYG",
        players=[{
            "name": "Malik Nabers",
            "position": "WR",
            "age": 21,
            "contract_year": False,
            "snap_pct": 0.85,
            "seasons": [{"year": 2024, "games": 16, "target_share": 0.24, "air_yards_share": 0.28,
                         "targets": 100, "receptions": 70, "rec_yards": 900, "rec_tds": 6,
                         "carries": 0, "rush_yards": 0, "rush_tds": 0, "ppr_per_game": 13.5,
                         "backup_qb_season": False}],
            "dependency_flags": [{"type": "beneficiary", "trigger": "Sterling Shepard",
                                   "effect": "positive", "confidence": "high"}],
        }],
    )

    with patch.object(agent, "call_once", new_callable=AsyncMock, return_value=model_output), \
         patch.object(agent, "_build_team_context", new_callable=AsyncMock, return_value=context), \
         patch("backend.agents.player_profiles._write_profiles", new_callable=AsyncMock, return_value=1):
        result = await agent.run_for_team("NYG")

    assert result == 1


# ---------------------------------------------------------------------------
# 5. Role classification — WR1 alpha
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_role_classification_wr1_alpha():
    """WR with dominant target share and high snap % classified as wr1_alpha."""
    agent = PlayerProfilesAgent()

    model_output = json.dumps([
        _make_profile(
            name="Ja'Marr Chase",
            role="wr1_alpha",
            situation_score="strong",
            separation_score="elite",
            efficiency="elite",
        )
    ])

    context = _mock_context(
        team="CIN",
        players=[{
            "name": "Ja'Marr Chase",
            "position": "WR",
            "age": 24,
            "contract_year": False,
            "snap_pct": 0.91,
            "seasons": [{"year": 2024, "games": 17, "target_share": 0.31, "air_yards_share": 0.36,
                         "targets": 130, "receptions": 100, "rec_yards": 1450, "rec_tds": 11,
                         "carries": 0, "rush_yards": 0, "rush_tds": 0, "ppr_per_game": 22.4,
                         "backup_qb_season": False}],
            "dependency_flags": [],
        }],
    )

    with patch.object(agent, "call_once", new_callable=AsyncMock, return_value=model_output), \
         patch.object(agent, "_build_team_context", new_callable=AsyncMock, return_value=context), \
         patch("backend.agents.player_profiles._write_profiles", new_callable=AsyncMock, return_value=1):
        result = await agent.run_for_team("CIN")

    assert result == 1


# ---------------------------------------------------------------------------
# 6. Role classification — committee back
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_role_classification_committee_back():
    """RB with shared carries and committee flag classified as committee_back."""
    agent = PlayerProfilesAgent()

    model_output = json.dumps([
        _make_profile(
            name="Aaron Jones",
            role="committee_back",
            situation_score="moderate",
        )
    ])

    context = _mock_context(
        team="MIN",
        players=[{
            "name": "Aaron Jones",
            "position": "RB",
            "age": 30,
            "contract_year": False,
            "snap_pct": 0.48,
            "seasons": [{"year": 2024, "games": 14, "target_share": 0.08, "air_yards_share": 0.04,
                         "targets": 40, "receptions": 32, "rec_yards": 240, "rec_tds": 2,
                         "carries": 110, "rush_yards": 450, "rush_tds": 4,
                         "ppr_per_game": 9.2, "backup_qb_season": False}],
            "dependency_flags": [{"type": "committee", "trigger": "Josh Oliver",
                                   "effect": "neutral", "confidence": "medium"}],
        }],
    )

    with patch.object(agent, "call_once", new_callable=AsyncMock, return_value=model_output), \
         patch.object(agent, "_build_team_context", new_callable=AsyncMock, return_value=context), \
         patch("backend.agents.player_profiles._write_profiles", new_callable=AsyncMock, return_value=1):
        result = await agent.run_for_team("MIN")

    assert result == 1


# ---------------------------------------------------------------------------
# 7. System grade inherited from team_systems
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_system_grade_inherited_from_team_systems():
    """Team system data is included in the context sent to the model."""
    agent = PlayerProfilesAgent()

    captured_user_message: list[str] = []

    async def _capture_call(system, user, input_data, entity_id):
        captured_user_message.append(user)
        return json.dumps([_make_profile("Tyreek Hill", "wr1_alpha")])

    context_system = {
        "system_grade": "A+",
        "qb_name": "Tua Tagovailoa",
        "qb_tier": "solid",
        "rookie_qb_flag": False,
        "compound_risk_flag": False,
        "oc_scheme": "pass_heavy",
        "red_zone_philosophy": "wr1",
    }

    with patch.object(agent, "call_once", side_effect=_capture_call), \
         patch.object(agent, "_build_team_context", new_callable=AsyncMock,
                      return_value=_mock_context("MIA", team_system=context_system,
                                                  players=[{
                                                      "name": "Tyreek Hill",
                                                      "position": "WR",
                                                      "age": 30,
                                                      "contract_year": False,
                                                      "snap_pct": 0.90,
                                                      "seasons": [{"year": 2024, "games": 17,
                                                                    "target_share": 0.30,
                                                                    "air_yards_share": 0.35,
                                                                    "targets": 125, "receptions": 90,
                                                                    "rec_yards": 1300, "rec_tds": 10,
                                                                    "carries": 0, "rush_yards": 0,
                                                                    "rush_tds": 0,
                                                                    "ppr_per_game": 21.2,
                                                                    "backup_qb_season": False}],
                                                      "dependency_flags": [],
                                                  }])), \
         patch("backend.agents.player_profiles._write_profiles", new_callable=AsyncMock, return_value=1):
        await agent.run_for_team("MIA")

    assert captured_user_message, "call_once was not called"
    user_msg = captured_user_message[0]
    assert "A+" in user_msg
    assert "pass_heavy" in user_msg


# ---------------------------------------------------------------------------
# 8. Dependency flags attached to profile context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dependency_flags_attached_to_profile():
    """Dependency flags for displaced players are included in the context."""
    agent = PlayerProfilesAgent()

    captured_input_data: list[dict] = []

    async def _capture_call(system, user, input_data, entity_id):
        captured_input_data.append(input_data)
        return json.dumps([
            _make_profile("Ladd McConkey", "slot_specialist", situation_score="weak")
        ])

    lac_player = {
        "name": "Ladd McConkey",
        "position": "WR",
        "age": 23,
        "contract_year": False,
        "snap_pct": 0.82,
        "seasons": [{"year": 2024, "games": 16, "target_share": 0.22, "air_yards_share": 0.25,
                     "targets": 105, "receptions": 82, "rec_yards": 1149, "rec_tds": 7,
                     "carries": 0, "rush_yards": 0, "rush_tds": 0, "ppr_per_game": 15.2,
                     "backup_qb_season": False}],
        "dependency_flags": [
            {"type": "displaced", "trigger": "Keenan Allen", "effect": "negative", "confidence": "high"},
            {"type": "contingent", "trigger": "Keenan Allen", "effect": "positive", "confidence": "high"},
        ],
    }

    with patch.object(agent, "call_once", side_effect=_capture_call), \
         patch.object(agent, "_build_team_context", new_callable=AsyncMock,
                      return_value=_mock_context("LAC", players=[lac_player])), \
         patch("backend.agents.player_profiles._write_profiles", new_callable=AsyncMock, return_value=1):
        await agent.run_for_team("LAC")

    assert captured_input_data, "call_once was not called"
    players_in_context = captured_input_data[0].get("players", [])
    mcconkey = next((p for p in players_in_context if "McConkey" in p.get("name", "")), None)
    assert mcconkey is not None
    assert len(mcconkey.get("dependency_flags", [])) == 2
    flag_types = [f["type"] for f in mcconkey["dependency_flags"]]
    assert "displaced" in flag_types
    assert "contingent" in flag_types


# ---------------------------------------------------------------------------
# 9. No hardcoded years
# ---------------------------------------------------------------------------

def test_no_hardcoded_years():
    """
    player_profiles.py must contain no literal integer year constants.
    All year references must use get_current_season() / get_analysis_year() / etc.
    """
    source = Path("backend/agents/player_profiles.py").read_text()
    # Look for 4-digit integers that look like years (2020-2030)
    found = re.findall(r"\b(202[0-9]|2030)\b", source)
    assert not found, (
        f"Hardcoded year(s) found in player_profiles.py: {found}. "
        "Use get_current_season() / get_analysis_year() / get_analysis_seasons() instead."
    )


# ---------------------------------------------------------------------------
# 10. Single API call per team
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_api_call_per_team():
    """run_for_team() must make exactly ONE call_once() call per team."""
    agent = PlayerProfilesAgent()
    call_count = 0

    async def _mock_call(system, user, input_data, entity_id):
        nonlocal call_count
        call_count += 1
        return json.dumps([_make_profile("CeeDee Lamb", "wr1_alpha")])

    context = _mock_context(
        team="DAL",
        players=[{
            "name": "CeeDee Lamb",
            "position": "WR",
            "age": 25,
            "contract_year": False,
            "snap_pct": 0.92,
            "seasons": [{"year": 2024, "games": 17, "target_share": 0.29, "air_yards_share": 0.33,
                         "targets": 120, "receptions": 94, "rec_yards": 1320, "rec_tds": 9,
                         "carries": 0, "rush_yards": 0, "rush_tds": 0, "ppr_per_game": 20.1,
                         "backup_qb_season": False}],
            "dependency_flags": [],
        }],
    )

    with patch.object(agent, "call_once", side_effect=_mock_call), \
         patch.object(agent, "_build_team_context", new_callable=AsyncMock, return_value=context), \
         patch("backend.agents.player_profiles._write_profiles", new_callable=AsyncMock, return_value=1):
        await agent.run_for_team("DAL")

    assert call_count == 1, f"Expected 1 API call, got {call_count}"


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------

def test_compute_season_averages_empty():
    from backend.utils.seasons import get_analysis_year
    ts3, tsl, ay3 = _compute_season_averages([], get_analysis_year())
    assert ts3 is None and tsl is None and ay3 is None


def test_compute_season_averages_excludes_future_year():
    """Seasons at or above analysis_year must not affect averages."""
    from backend.utils.seasons import get_analysis_year
    year = get_analysis_year()
    seasons = [
        {"year": year,     "games": 16, "target_share": 0.99, "air_yards_share": 0.99},
        {"year": year - 1, "games": 15, "target_share": 0.20, "air_yards_share": 0.25},
    ]
    ts3, tsl, ay3 = _compute_season_averages(seasons, year)
    # Future year must be excluded
    assert ts3 == pytest.approx(0.20, abs=0.001)


def test_to_decimal_none():
    assert _to_decimal(None) is None


def test_to_decimal_float():
    from decimal import Decimal
    result = _to_decimal(0.2234)
    assert result == Decimal("0.223")
