"""
Tests for league auction history — get_market_context + CSV import + refresh.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.engines.valuation import (
    compute_bid_ceiling,
    compute_value_gap,
    get_market_context,
)


# ---------------------------------------------------------------------------
# Helpers — fake Player-like objects
# ---------------------------------------------------------------------------

def _player(
    market_value=None,
    market_value_fantasypros=None,
    market_value_league=None,
):
    """Build a minimal mock with the fields get_market_context needs."""
    p = MagicMock()
    p.market_value = Decimal(str(market_value)) if market_value is not None else None
    p.market_value_fantasypros = Decimal(str(market_value_fantasypros)) if market_value_fantasypros is not None else None
    p.market_value_league = Decimal(str(market_value_league)) if market_value_league is not None else None
    return p


# ===========================================================================
# get_market_context — 6 tests
# ===========================================================================

def test_market_context_league_only():
    """League price set, no FP → effective = league, no bias."""
    p = _player(market_value_league=25)
    ctx = get_market_context(p)
    assert ctx["effective_market_value"] == Decimal("25")
    assert ctx["league_bias"] is None
    assert ctx["league_bias_signal"] is None


def test_market_context_fp_only():
    """FP set, no league → effective = FP, no bias."""
    p = _player(market_value_fantasypros=30)
    ctx = get_market_context(p)
    assert ctx["effective_market_value"] == Decimal("30")
    assert ctx["league_bias"] is None
    assert ctx["league_bias_signal"] is None


def test_market_context_both_aligned():
    """Both set, difference ≤ $5 → aligned."""
    p = _player(market_value_fantasypros=28, market_value_league=30)
    ctx = get_market_context(p)
    assert ctx["effective_market_value"] == Decimal("30")
    assert ctx["league_bias"] == Decimal("2.00")
    assert ctx["league_bias_signal"] == "league_aligned"


def test_market_context_league_overpays():
    """League pays $15 more than FP → overpays signal."""
    p = _player(market_value_fantasypros=20, market_value_league=35)
    ctx = get_market_context(p)
    assert ctx["league_bias"] == Decimal("15.00")
    assert ctx["league_bias_signal"] == "league_overpays"


def test_market_context_league_underpays():
    """League pays $13 less than FP → underpays signal."""
    p = _player(market_value_fantasypros=40, market_value_league=27)
    ctx = get_market_context(p)
    assert ctx["league_bias"] == Decimal("-13.00")
    assert ctx["league_bias_signal"] == "league_underpays"


def test_market_context_neither():
    """No market values at all → all None."""
    p = _player()
    ctx = get_market_context(p)
    assert ctx["effective_market_value"] is None
    assert ctx["league_bias"] is None
    assert ctx["league_bias_signal"] is None


# ===========================================================================
# Ceiling differs with league vs FP
# ===========================================================================

def test_ceiling_differs_with_league_vs_fp():
    """Verify compute_bid_ceiling responds differently to league vs FP market value."""
    sv = Decimal("30")
    fp_mv = Decimal("40")
    league_mv = Decimal("25")

    ceiling_fp = compute_bid_ceiling(sv, fp_mv, tier=2, position="WR", risk_level="low")
    ceiling_league = compute_bid_ceiling(sv, league_mv, tier=2, position="WR", risk_level="low")

    # T2-3 blend = sv * 0.85 + mv * 0.15
    # With FP=40: 30*0.85 + 40*0.15 = 25.50 + 6.00 = 31.50
    # With league=25: 30*0.85 + 25*0.15 = 25.50 + 3.75 = 29.25
    assert ceiling_fp > ceiling_league
    assert ceiling_fp == Decimal("31.50")
    assert ceiling_league == Decimal("29.25")


# ===========================================================================
# FP unchanged after league import (conceptual)
# ===========================================================================

def test_fp_unchanged_after_league_import():
    """market_value (FP consensus) is never modified by league context."""
    p = _player(market_value=30, market_value_fantasypros=30, market_value_league=15)
    ctx = get_market_context(p)
    # effective uses league, but FP is still returned untouched
    assert ctx["market_value_fantasypros"] == Decimal("30")
    assert ctx["effective_market_value"] == Decimal("15")


# ===========================================================================
# Valuation pass uses effective_market_value (unit-level)
# ===========================================================================

def test_valuation_pass_uses_effective_mv():
    """When league price is available, ceiling computation uses it."""
    p = _player(market_value=40, market_value_fantasypros=40, market_value_league=20)
    ctx = get_market_context(p)
    effective = ctx["effective_market_value"]
    # effective should be league price
    assert effective == Decimal("20")

    # Compute ceiling with effective (league) vs with FP
    sv = Decimal("35")
    ceiling_effective = compute_bid_ceiling(sv, effective, tier=1, position="RB", risk_level="low")
    ceiling_fp = compute_bid_ceiling(sv, Decimal("40"), tier=1, position="RB", risk_level="low")
    # They should differ because market values differ
    assert ceiling_effective != ceiling_fp


def test_valuation_pass_fallback_to_fp():
    """No league price → effective = FP → same ceiling as before."""
    p = _player(market_value=40, market_value_fantasypros=40)
    ctx = get_market_context(p)
    effective = ctx["effective_market_value"]
    assert effective == Decimal("40")

    sv = Decimal("35")
    ceiling_effective = compute_bid_ceiling(sv, effective, tier=1, position="RB", risk_level="low")
    ceiling_fp = compute_bid_ceiling(sv, Decimal("40"), tier=1, position="RB", risk_level="low")
    assert ceiling_effective == ceiling_fp


# ===========================================================================
# Bias boundary tests
# ===========================================================================

def test_market_context_boundary_plus_5():
    """Exactly +$5 bias → aligned (threshold is strictly > 5)."""
    p = _player(market_value_fantasypros=20, market_value_league=25)
    ctx = get_market_context(p)
    assert ctx["league_bias"] == Decimal("5.00")
    assert ctx["league_bias_signal"] == "league_aligned"


def test_market_context_boundary_minus_5():
    """Exactly -$5 bias → aligned (threshold is strictly < -5)."""
    p = _player(market_value_fantasypros=25, market_value_league=20)
    ctx = get_market_context(p)
    assert ctx["league_bias"] == Decimal("-5.00")
    assert ctx["league_bias_signal"] == "league_aligned"


def test_market_context_fallback_to_market_value():
    """When market_value_fantasypros is None, falls back to market_value."""
    p = _player(market_value=28, market_value_league=20)
    ctx = get_market_context(p)
    assert ctx["market_value_fantasypros"] == Decimal("28")
    assert ctx["league_bias"] == Decimal("-8.00")
    assert ctx["league_bias_signal"] == "league_underpays"
