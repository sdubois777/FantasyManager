"""
Stage 9: Draft Bible Valuation Pass

Pure Python computation — no AI calls.

Synthesizes all pre-draft agent outputs (PlayerProfile, PlayerInjuryProfile)
into final valuation fields on the players table:
  - tier (1-5 per position)
  - baseline_value (PPR points → auction dollars via PAR method)
  - risk_adjusted_value (baseline × (1 + risk_modifier))
  - recommended_bid_ceiling (two-value formula from ARCHITECTURE.md)
  - let_go_threshold (bid ceiling × 1.15)
  - value_gap and value_gap_signal (system vs market gap)

Formulas from docs/ARCHITECTURE.md — Two-Value Auction System:

  Tier 1:
    blend = system_value × (1 - anchor_weight) + market_value × anchor_weight
    ceiling = blend × positional_scarcity_modifier × (1 + risk_modifier)

  Tier 2-3:
    blend = system_value × 0.85 + market_value × 0.15
    ceiling = blend × (1 + risk_modifier)

  Tier 4-5:
    ceiling = system_value × (1 + risk_modifier)

Anchor weights: T1=0.80, T2=0.40, T3=0.15, T4-5=0.00
Scarcity:       T1 RB=1.35, T1 WR=1.20, T1 QB/TE=1.10
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import AsyncSessionLocal
from backend.models.player import Player, PlayerProfile, PlayerInjuryProfile
from backend.utils.seasons import get_analysis_year

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# League defaults — matches docs/rules/LEAGUE_RULES.md
# ---------------------------------------------------------------------------

# SKILL_STARTER_BUDGET ($185) × 12 teams = $2,220 total skill position pool
# This is the CORRECT calibration pool per LEAGUE_RULES.md Rule #3.
# NOT $200×12=$2,400 (full auction budget — wrong) and NOT $183×12=$2,196 (wrong).
LEAGUE_SKILL_BUDGET = 185   # skill starter budget per team
LEAGUE_TEAMS        = 12
LEAGUE_SKILL_DOLLAR_POOL = LEAGUE_SKILL_BUDGET * LEAGUE_TEAMS  # = 2220

# Positional budget allocation targets (% of LEAGUE_SKILL_DOLLAR_POOL)
# From LEAGUE_RULES.md: RB=38%, WR=32%, QB=10%, TE=10%
# Do NOT invert WR and QB. QB is 10%, not 38%.
POSITION_BUDGET_SHARE: dict[str, float] = {
    "QB": 0.10,
    "RB": 0.38,
    "WR": 0.32,
    "TE": 0.10,
}

# Maximum realistic bid per position — hard cap enforced (not just logged)
# per LEAGUE_RULES.md Rule #1 and #3
MAX_REALISTIC_BID: dict[str, int] = {
    "RB": 80,
    "WR": 70,
    "QB": 50,
    "TE": 45,
    "K":   2,
    "DEF": 2,
}

# Minimum replacement-level PPR per game — sanity floor for dynamic computation.
# If the dynamically computed replacement PPR/game falls below these values,
# something is wrong with the data (too few profiles, skewed sample).
REPLACEMENT_LEVEL_PPR_PER_GAME: dict[str, float] = {
    "QB": 18.0,
    "RB": 8.0,
    "WR": 7.0,
    "TE": 5.0,
}

# Injury recovery discount applied to PPR baseline for players with major injuries
POST_MAJOR_INJURY_DISCOUNT = 0.75  # 25% discount

# Replacement rank cutoff — lowest draftable starter at each position
REPLACEMENT_RANK: dict[str, int] = {
    "QB": 12,
    "RB": 30,
    "WR": 42,
    "TE": 12,
}

# Draftable positions for this pass
DRAFTABLE_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})

# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------

# Tier boundaries by positional rank (1-indexed, inclusive upper bound)
_TIER_CUTOFFS = [3, 9, 19, 34]  # T1≤3, T2≤9, T3≤19, T4≤34, T5=rest


def assign_tier(rank: int) -> int:
    """Return tier 1-5 for a player ranked `rank` among their position."""
    for tier, cutoff in enumerate(_TIER_CUTOFFS, start=1):
        if rank <= cutoff:
            return tier
    return 5


# ---------------------------------------------------------------------------
# Anchor weights and scarcity modifiers
# ---------------------------------------------------------------------------

ANCHOR_WEIGHTS: dict[int, Decimal] = {
    1: Decimal("0.80"),
    2: Decimal("0.40"),
    3: Decimal("0.15"),
    4: Decimal("0.00"),
    5: Decimal("0.00"),
}

SCARCITY_MODIFIERS: dict[str, Decimal] = {
    "RB": Decimal("1.35"),
    "WR": Decimal("1.20"),
    "QB": Decimal("1.10"),
    "TE": Decimal("1.10"),
}

# ---------------------------------------------------------------------------
# Value gap thresholds
# ---------------------------------------------------------------------------

VALUE_GAP_OVERVALUE_THRESHOLD  = Decimal("-5")   # gap < -5  → market_overvalues
VALUE_GAP_UNDERVALUE_THRESHOLD = Decimal("5")    # gap > 5   → market_undervalues

# ---------------------------------------------------------------------------
# Pure computation functions (stateless — easy to unit test)
# ---------------------------------------------------------------------------


def ppr_to_system_value(
    ppr_points: float,
    replacement_ppr: float,
    total_par: float,
    position_budget: float,
) -> Decimal:
    """
    Convert PPR points to auction-dollar system_value via Points Above Replacement.

    Args:
        ppr_points:       Player's projected clean-season PPR total.
        replacement_ppr:  PPR of the player at the replacement rank cutoff.
        total_par:        Sum of PAR for all draftable players at this position.
        position_budget:  Total auction dollars allocated to this position group.

    Returns:
        Decimal system_value in dollars (minimum $1).
    """
    par = max(0.0, ppr_points - replacement_ppr)
    if total_par <= 0 or par <= 0:
        return Decimal("1.00")
    raw = (par / total_par) * position_budget
    return _to_dec(max(1.0, round(raw, 2)))


def compute_bid_ceiling(
    system_value: Decimal,
    market_value: Optional[Decimal],
    tier: int,
    position: str,
    risk_modifier: Optional[Decimal],
) -> Decimal:
    """
    Compute the recommended bid ceiling using the two-value formula.

    When market_value is None, treat market_value = system_value for blending
    (neutral blend — system value drives the result entirely).

    Returns:
        Decimal bid ceiling in dollars (minimum $1).
    """
    mv = market_value if market_value is not None else system_value
    rm = risk_modifier if risk_modifier is not None else Decimal("0")
    risk_factor = Decimal("1") + rm

    if tier == 1:
        anchor = ANCHOR_WEIGHTS[1]
        blend = system_value * (Decimal("1") - anchor) + mv * anchor
        scarcity = SCARCITY_MODIFIERS.get(position, Decimal("1.00"))
        ceiling = blend * scarcity * risk_factor

    elif tier in (2, 3):
        blend = system_value * Decimal("0.85") + mv * Decimal("0.15")
        ceiling = blend * risk_factor

    else:  # Tier 4-5
        ceiling = system_value * risk_factor

    return _to_dec(max(Decimal("1.00"), ceiling))


def compute_value_gap(
    system_value: Decimal,
    market_value: Optional[Decimal],
) -> tuple[Optional[Decimal], Optional[str]]:
    """
    Compute value_gap (system_value - market_value) and value_gap_signal.

    Returns (None, None) when market_value is not available.
    """
    if market_value is None:
        return None, None

    gap = system_value - market_value
    gap = _to_dec(gap)

    if gap < VALUE_GAP_OVERVALUE_THRESHOLD:
        signal = "market_overvalues"
    elif gap > VALUE_GAP_UNDERVALUE_THRESHOLD:
        signal = "market_undervalues"
    else:
        signal = "aligned"

    return gap, signal


def compute_let_go_threshold(bid_ceiling: Decimal) -> Decimal:
    """Let-go threshold = bid ceiling + 15%."""
    return _to_dec(bid_ceiling * Decimal("1.15"))


def _to_dec(value: float | Decimal) -> Decimal:
    """Normalize to Decimal with 2dp."""
    return Decimal(str(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Async valuation pass — loads data, computes, writes back
# ---------------------------------------------------------------------------


async def run_valuation_pass(
    skill_budget: int = LEAGUE_SKILL_BUDGET,
    league_teams: int = LEAGUE_TEAMS,
) -> dict:
    """
    Load all players with profiles, compute valuations, write back to DB.

    Uses LEAGUE_SKILL_DOLLAR_POOL = skill_budget × league_teams = $185 × 12 = $2,220
    as the total calibration pool per docs/rules/LEAGUE_RULES.md Rule #3.

    Args:
        skill_budget:  Skill starter budget per team (default 185).
        league_teams:  Number of teams in league (default 12).

    Returns:
        Summary dict: {processed, updated, skipped, analysis_year}.
    """
    analysis_year = get_analysis_year()
    total_budget = float(skill_budget * league_teams)  # = 185 × 12 = 2220

    async with AsyncSessionLocal() as session:
        # Eager-load profiles and injury profiles — one query, no N+1
        stmt = (
            select(Player)
            .options(
                selectinload(Player.profile),
                selectinload(Player.injury_profile),
            )
        )
        players: list[Player] = (await session.execute(stmt)).scalars().all()

        # --------------- Group by position, extract ppr_points ---------------
        pos_groups: dict[str, list[tuple[Player, float]]] = {
            p: [] for p in DRAFTABLE_POSITIONS
        }
        valued_player_ids: set = set()

        for player in players:
            pos = player.position
            if pos not in DRAFTABLE_POSITIONS:
                continue
            ppr = _extract_ppr(player.profile)
            # FIX 4: Apply injury discount to PPR baseline for players with
            # post-ACL or major injury recovery flags
            if ppr > 0:
                ppr = _apply_injury_discount(ppr, player.injury_profile, player.profile)
            if ppr > 0:
                pos_groups[pos].append((player, ppr))

        # Sort each group descending by PPR
        for pos in pos_groups:
            pos_groups[pos].sort(key=lambda x: x[1], reverse=True)

        # --------------- Compute replacement levels + PAR per position -------
        par_context: dict[str, dict] = {}
        for pos, group in pos_groups.items():
            repl_rank = REPLACEMENT_RANK[pos]
            if len(group) >= repl_rank:
                repl_ppr = group[repl_rank - 1][1]
            else:
                repl_ppr = group[-1][1] if group else 0.0

            # FIX 2: Verify replacement level against per-game floor.
            # If dynamic value is unreasonably low, use floor × 17 games.
            ppg_floor = REPLACEMENT_LEVEL_PPR_PER_GAME.get(pos, 5.0)
            season_floor = ppg_floor * 17
            if repl_ppr < season_floor:
                logger.warning(
                    "REPLACEMENT LEVEL LOW: %s dynamic=%.1f < floor=%.1f (%.1f ppg × 17). "
                    "Using floor.",
                    pos, repl_ppr, season_floor, ppg_floor,
                )
                repl_ppr = season_floor

            total_par = sum(max(0.0, ppr - repl_ppr) for _, ppr in group)
            pos_budget = total_budget * POSITION_BUDGET_SHARE[pos]

            par_context[pos] = {
                "replacement_ppr": repl_ppr,
                "total_par":       total_par,
                "position_budget": pos_budget,
            }

        # --------------- Compute and write valuations ------------------------
        processed = 0
        updated   = 0
        skipped   = 0

        for pos, group in pos_groups.items():
            ctx = par_context[pos]
            for rank_0, (player, ppr) in enumerate(group):
                rank = rank_0 + 1
                tier = assign_tier(rank)

                sv = ppr_to_system_value(
                    ppr_points        = ppr,
                    replacement_ppr   = ctx["replacement_ppr"],
                    total_par         = ctx["total_par"],
                    position_budget   = ctx["position_budget"],
                )

                rm = _get_risk_modifier(player.injury_profile)

                ceiling  = compute_bid_ceiling(sv, player.market_value, tier, pos, rm)

                # FIX 5: Hard cap enforcement — cap ceiling to MAX_REALISTIC_BID
                max_bid = MAX_REALISTIC_BID.get(pos, 80)
                max_bid_dec = Decimal(str(max_bid))
                if ceiling > max_bid_dec:
                    logger.info(
                        "BID CEILING CAPPED: %s (%s T%d) ceiling=$%s → $%d max. "
                        "sv=$%s, total_par=%.1f, pool=$%.0f",
                        player.name, pos, tier, ceiling, max_bid,
                        sv, ctx["total_par"], ctx["position_budget"],
                    )
                    ceiling = max_bid_dec

                let_go   = compute_let_go_threshold(ceiling)
                gap, sig = compute_value_gap(sv, player.market_value)
                risk_adj = _to_dec(sv * (Decimal("1") + (rm or Decimal("0"))))
                anchor   = ANCHOR_WEIGHTS.get(tier, Decimal("0.00"))
                scarcity = SCARCITY_MODIFIERS.get(pos, Decimal("1.00")) if tier == 1 else Decimal("1.00")

                # Update in-session player object
                player.tier                       = tier
                player.baseline_value             = sv
                player.risk_adjusted_value        = _to_dec(max(Decimal("1.00"), risk_adj))
                player.recommended_bid_ceiling    = ceiling
                player.let_go_threshold           = let_go
                player.elite_anchor_weight        = anchor
                player.positional_scarcity_modifier = scarcity
                player.value_gap                  = gap
                player.value_gap_signal           = sig
                player.data_confidence            = _confidence(player)

                session.add(player)
                valued_player_ids.add(player.id)
                processed += 1
                updated   += 1

        # Clear stale valuations for players that were skipped (no profile or
        # below usage threshold). This prevents ghost values from previous runs.
        cleared = 0
        for player in players:
            if player.position in DRAFTABLE_POSITIONS and player.id not in valued_player_ids:
                if player.baseline_value is not None:
                    player.tier                       = None
                    player.baseline_value             = None
                    player.risk_adjusted_value        = None
                    player.recommended_bid_ceiling    = None
                    player.let_go_threshold           = None
                    player.elite_anchor_weight        = None
                    player.positional_scarcity_modifier = None
                    player.value_gap                  = None
                    player.value_gap_signal           = None
                    player.data_confidence            = "low"
                    session.add(player)
                    cleared += 1
                skipped += 1

        await session.commit()

    logger.info(
        "Valuation pass (%d): %d updated, %d skipped, %d cleared, analysis_year=%d",
        processed, updated, skipped, cleared, analysis_year,
    )
    return {
        "processed":     processed,
        "updated":       updated,
        "skipped":       skipped,
        "cleared":       cleared,
        "analysis_year": analysis_year,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_ppr(profile: Optional[PlayerProfile]) -> float:
    """Extract ppr_points from clean_season_baseline JSONB, or 0."""
    if not profile or not profile.clean_season_baseline:
        return 0.0
    val = profile.clean_season_baseline.get("ppr_points", 0)
    try:
        return max(0.0, float(val or 0))
    except (TypeError, ValueError):
        return 0.0


def _get_risk_modifier(injury_profile: Optional[PlayerInjuryProfile]) -> Optional[Decimal]:
    """Return risk_adjusted_value_modifier from injury profile, or None."""
    if not injury_profile or injury_profile.risk_adjusted_value_modifier is None:
        return None
    return Decimal(str(injury_profile.risk_adjusted_value_modifier))


def _apply_injury_discount(
    ppr: float,
    injury_profile: Optional[PlayerInjuryProfile],
    profile: Optional[PlayerProfile],
) -> float:
    """
    FIX 4: Apply injury recovery discount to PPR baseline.

    Players with post_acl_flag or other major injury indicators get their
    baseline discounted by POST_MAJOR_INJURY_DISCOUNT (25% reduction).
    This ensures the discount affects the baseline dollar value, not just
    the risk modifier overlay.

    Also applies discount if the profile's clean_season_baseline has the
    'declining' flag (set by career decline detection in player_profiles).
    """
    discount = 1.0

    # Check injury profile for major injury flags
    if injury_profile:
        if injury_profile.post_acl_flag:
            discount *= POST_MAJOR_INJURY_DISCOUNT
        elif injury_profile.workload_cliff_flag:
            discount *= 0.85  # 15% discount for workload cliff

    # Check profile for career decline flag
    if profile and profile.clean_season_baseline:
        if profile.clean_season_baseline.get("declining"):
            # Only apply decline discount if injury discount hasn't already been applied
            if discount >= 1.0:
                discount *= 0.85  # 15% decline discount

    return ppr * discount


def _confidence(player: Player) -> str:
    """Infer data_confidence based on available profile data."""
    has_profile = player.profile is not None and player.profile.clean_season_baseline
    has_injury  = player.injury_profile is not None
    if has_profile and has_injury:
        return "high"
    if has_profile or has_injury:
        return "medium"
    return "low"
