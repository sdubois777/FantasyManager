"""
Tests for Yahoo API historical league functions.

All tests mock _api_get to avoid real HTTP calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.integrations.yahoo_api import (
    get_all_user_leagues,
    get_draft_results_for_league,
    get_player_details_batch,
    get_teams_in_league,
)


# ---------------------------------------------------------------------------
# get_all_user_leagues
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_all_user_leagues_parses_response():
    """Verify parsing of nested Yahoo users/games/leagues response."""
    mock_response = {
        "fantasy_content": {
            "users": {
                "0": {
                    "user": [
                        {"guid": "ABCDEF"},
                        {
                            "games": {
                                "0": {
                                    "game": [
                                        {"game_key": "nfl"},
                                        {
                                            "leagues": {
                                                "0": {
                                                    "league": [
                                                        {
                                                            "league_key": "nfl.l.12345",
                                                            "league_id": "12345",
                                                            "name": "My League",
                                                            "season": "2024",
                                                            "num_teams": 14,
                                                            "draft_type": "auction",
                                                            "draft_status": "postdraft",
                                                        }
                                                    ]
                                                },
                                                "1": {
                                                    "league": [
                                                        {
                                                            "league_key": "nfl.l.12345",
                                                            "league_id": "12345",
                                                            "name": "My League",
                                                            "season": "2023",
                                                            "num_teams": 14,
                                                            "draft_type": "auction",
                                                            "draft_status": "postdraft",
                                                        }
                                                    ]
                                                },
                                                "count": 2,
                                            }
                                        },
                                    ]
                                },
                                "count": 1,
                            }
                        },
                    ]
                },
                "count": 1,
            }
        }
    }

    with patch("backend.integrations.yahoo_api._api_get", new_callable=AsyncMock, return_value=mock_response):
        leagues = await get_all_user_leagues()

    assert len(leagues) == 2
    assert leagues[0]["season"] == "2023"  # sorted ascending
    assert leagues[1]["season"] == "2024"
    assert leagues[0]["league_id"] == "12345"
    assert leagues[0]["is_auction"] is True


@pytest.mark.asyncio
async def test_get_all_user_leagues_non_auction_not_flagged():
    """Non-auction leagues have is_auction=False."""
    mock_response = {
        "fantasy_content": {
            "users": {
                "0": {
                    "user": [
                        {"guid": "X"},
                        {
                            "games": {
                                "0": {
                                    "game": [
                                        {"game_key": "nfl"},
                                        {
                                            "leagues": {
                                                "0": {
                                                    "league": [
                                                        {
                                                            "league_key": "nfl.l.99",
                                                            "league_id": "99",
                                                            "name": "Snake League",
                                                            "season": "2024",
                                                            "draft_type": "live",
                                                        }
                                                    ]
                                                },
                                                "count": 1,
                                            }
                                        },
                                    ]
                                },
                                "count": 1,
                            }
                        },
                    ]
                },
                "count": 1,
            }
        }
    }

    with patch("backend.integrations.yahoo_api._api_get", new_callable=AsyncMock, return_value=mock_response):
        leagues = await get_all_user_leagues()

    assert len(leagues) == 1
    assert leagues[0]["is_auction"] is False


# ---------------------------------------------------------------------------
# get_draft_results_for_league
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_draft_results_for_league_returns_picks():
    """Verify draft result parsing including cost field."""
    mock_response = {
        "fantasy_content": {
            "league": [
                {"league_key": "nfl.l.12345"},
                {
                    "draft_results": {
                        "0": {
                            "draft_result": {
                                "pick": 1,
                                "round": 1,
                                "team_key": "nfl.l.12345.t.3",
                                "player_key": "nfl.p.31883",
                                "cost": "45",
                            }
                        },
                        "1": {
                            "draft_result": {
                                "pick": 2,
                                "round": 1,
                                "team_key": "nfl.l.12345.t.7",
                                "player_key": "nfl.p.32685",
                                "cost": "62",
                            }
                        },
                        "count": 2,
                    }
                },
            ]
        }
    }

    with patch("backend.integrations.yahoo_api._api_get", new_callable=AsyncMock, return_value=mock_response):
        picks = await get_draft_results_for_league("nfl.l.12345")

    assert len(picks) == 2
    assert picks[0]["cost"] == "45"
    assert picks[0]["player_key"] == "nfl.p.31883"
    assert picks[1]["pick"] == 2


# ---------------------------------------------------------------------------
# get_player_details_batch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_player_details_batch_flattens_yahoo_format():
    """Verify player name/position extraction from Yahoo nested format."""
    mock_response = {
        "fantasy_content": {
            "players": {
                "0": {
                    "player": [
                        [
                            {"player_key": "nfl.p.31883"},
                            {"player_id": "31883"},
                            {"name": {"full": "Ja'Marr Chase", "first": "Ja'Marr", "last": "Chase"}},
                            {"editorial_team_abbr": "Cin"},
                            {"display_position": "WR"},
                        ]
                    ]
                },
                "count": 1,
            }
        }
    }

    with patch("backend.integrations.yahoo_api._api_get", new_callable=AsyncMock, return_value=mock_response):
        players = await get_player_details_batch(["nfl.p.31883"])

    assert len(players) == 1
    assert players[0]["name"] == "Ja'Marr Chase"
    assert players[0]["position"] == "WR"
    assert players[0]["nfl_team"] == "Cin"


# ---------------------------------------------------------------------------
# get_teams_in_league
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_teams_in_league_extracts_managers():
    """Verify team name and manager name extraction."""
    mock_response = {
        "fantasy_content": {
            "league": [
                {"league_key": "nfl.l.12345"},
                {
                    "teams": {
                        "0": {
                            "team": [
                                [
                                    {"team_key": "nfl.l.12345.t.3"},
                                    {"name": "The Lord"},
                                    {"managers": {
                                        "0": {
                                            "manager": {
                                                "nickname": "BigBoss",
                                                "guid": "XYZ",
                                            }
                                        },
                                        "count": 1,
                                    }},
                                ]
                            ]
                        },
                        "count": 1,
                    }
                },
            ]
        }
    }

    with patch("backend.integrations.yahoo_api._api_get", new_callable=AsyncMock, return_value=mock_response):
        teams = await get_teams_in_league("nfl.l.12345")

    assert len(teams) == 1
    assert teams[0]["team_name"] == "The Lord"
    assert teams[0]["manager_name"] == "BigBoss"
