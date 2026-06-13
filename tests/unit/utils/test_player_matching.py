"""Tests for backend/utils/player_matching.py — shared season-stats resolver."""
from __future__ import annotations

import types

import pandas as pd
import pytest

from backend.utils.player_matching import (
    resolve_player_season_stats,
    resolve_player_season_stats_by_fields,
)


def _warehouse(target_share_by_season: dict[int, pd.DataFrame]):
    """Minimal stand-in exposing get_target_share(season)."""
    return types.SimpleNamespace(
        get_target_share=lambda season: target_share_by_season.get(season)
    )


def _player(**kw):
    """Player-like object with the identity attributes the resolver reads."""
    defaults = {
        "name": "Christian McCaffrey",
        "team_abbr": "SF",
        "position": "RB",
        "gsis_id": None,
        "sportradar_id": None,
        "sleeper_id": None,
    }
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


def test_resolves_by_sleeper_id_regardless_of_name_format():
    """sleeper_id match wins even when the frame uses abbreviated names (2025 case)."""
    df = pd.DataFrame([
        {"player_name": "C.McCaffrey", "recent_team": "SF", "position": "RB",
         "sleeper_id": "4034", "games": 17, "total_carries": 240},
    ])
    wh = _warehouse({2025: df})

    stats = resolve_player_season_stats(
        _player(name="Christian McCaffrey", sleeper_id="4034"), 2025, wh
    )

    assert stats is not None
    assert stats["games"] == 17
    assert stats["carries"] == 240


def test_returns_none_when_season_frame_missing():
    """No frame for the season → None, not an error."""
    wh = _warehouse({})
    assert resolve_player_season_stats(_player(sleeper_id="4034"), 2099, wh) is None


def test_position_filter_prevents_cross_position_collision():
    """A same-last-name player at a different position is never matched by name."""
    df = pd.DataFrame([
        {"player_name": "J.Taylor", "recent_team": "IND", "position": "RB",
         "sleeper_id": "rb1", "games": 14, "total_carries": 300},
        {"player_name": "B.Taylor", "recent_team": "IND", "position": "WR",
         "sleeper_id": "wr1", "games": 10, "total_carries": 0},
    ])
    wh = _warehouse({2024: df})

    # WR lookup by name+team+position must not pick up the RB row.
    stats = resolve_player_season_stats_by_fields(
        wh, player_name="B.Taylor", team="IND", season=2024, position="WR",
    )
    assert stats is not None
    assert stats["games"] == 10
    assert stats["carries"] == 0


def test_zero_games_row_returns_none():
    """A row with games=0 is treated as no data."""
    df = pd.DataFrame([
        {"player_name": "C.McCaffrey", "recent_team": "SF", "position": "RB",
         "sleeper_id": "4034", "games": 0},
    ])
    wh = _warehouse({2025: df})
    assert resolve_player_season_stats(_player(sleeper_id="4034"), 2025, wh) is None
