"""Tests for PlayerRepository.find_by_name_fuzzy — draft-room name resolution."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.repositories.player_repo import PlayerRepository


def _player(name, position="TE", ypid="nfl_x", ceiling=10):
    p = MagicMock()
    p.name = name
    p.position = position
    p.yahoo_player_id = ypid
    p.recommended_bid_ceiling = ceiling
    return p


def _exact_result(player):
    r = MagicMock()
    r.scalar_one_or_none.return_value = player
    return r


def _candidates_result(players):
    r = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = players
    r.scalars.return_value = scalars
    return r


def _repo(side_effects):
    session = MagicMock()
    session.execute = AsyncMock(side_effect=side_effects)
    return PlayerRepository(session)


@pytest.mark.asyncio
async def test_fuzzy_empty_name_returns_none():
    repo = _repo([])  # no query should run
    assert await repo.find_by_name_fuzzy("") is None
    assert await repo.find_by_name_fuzzy("   ") is None


@pytest.mark.asyncio
async def test_fuzzy_exact_match():
    laporta = _player("Sam LaPorta", ypid="nfl_1")
    repo = _repo([_exact_result(laporta)])
    result = await repo.find_by_name_fuzzy("sam laporta")
    assert result is laporta


@pytest.mark.asyncio
async def test_fuzzy_suffix_normalized_match():
    # DOM sends "Brian Thomas"; DB has "Brian Thomas Jr."
    thomas = _player("Brian Thomas Jr.", position="WR", ypid="nfl_2")
    repo = _repo([_exact_result(None), _candidates_result([thomas])])
    result = await repo.find_by_name_fuzzy("Brian Thomas")
    assert result is thomas


@pytest.mark.asyncio
async def test_fuzzy_first_initial_last_name_match():
    # DOM sends "Sam LaPorta"; DB has "Samuel LaPorta"
    samuel = _player("Samuel LaPorta", ypid="nfl_3")
    repo = _repo([_exact_result(None), _candidates_result([samuel])])
    result = await repo.find_by_name_fuzzy("Sam LaPorta")
    assert result is samuel


@pytest.mark.asyncio
async def test_fuzzy_no_candidates_returns_none():
    repo = _repo([_exact_result(None), _candidates_result([])])
    assert await repo.find_by_name_fuzzy("Nonexistent Player") is None


@pytest.mark.asyncio
async def test_fuzzy_contains_fallback_prefers_first_candidate():
    # Neither normalized nor initial+last matches; best-ceiling candidate wins.
    other = _player("Mike Williams", position="WR", ypid="nfl_4", ceiling=30)
    repo = _repo([_exact_result(None), _candidates_result([other])])
    result = await repo.find_by_name_fuzzy("Mookie Williams")
    assert result is other
