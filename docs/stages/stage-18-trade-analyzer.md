# Stage 18: Trade Analyzer

## Before starting, read:
- `docs/INSEASON.md` — Trade Analyzer section
- `docs/ARCHITECTURE.md`
- Stages 15, 16, and 17 must be complete (Roster Monitor, Opponent Analyzer, Trade Value)

---

## Goal
User submits a trade — either one they received or one they're considering —
and gets back a structured analysis: whether it's good or bad for them,
why the other manager would or wouldn't accept it, and alternative proposals
if the submitted trade isn't favorable enough.

The key insight: FantasyPros trade suggestions are garbage because they
optimize for trades that are good for you without considering whether the
other person would ever accept them. This analyzer solves both problems
simultaneously.

---

## Model and cost parameters
- Model: `claude-sonnet-4-6`
- Max tokens: 1500
- Trigger: on-demand only (user submits a trade)
- Expected: a few calls per week in-season

---

## API endpoint

```
POST /trades/analyze
Authorization: Bearer {token}

Request body:
{
  "give": ["player_id_1", "player_id_2"],
  "receive": ["player_id_3"],
  "opponent_team_id": "yahoo_team_id"
}

Response: TradeAnalysis object (see output schema below)
```

---

## Input assembly (Python, before API call)

Assemble all context in Python first — no raw DB records to the model.

```python
async def _build_trade_context(
    give: list[str],
    receive: list[str],
    opponent_team_id: str,
    your_team_id: str,
    db: AsyncSession
) -> dict:
    """
    Pre-aggregate all context needed for trade analysis.
    This runs entirely in Python — no API calls.
    """
    
    # Pull player records for both sides
    give_players = await _get_players(db, give)
    receive_players = await _get_players(db, receive)
    
    # Calculate system values
    give_total = sum(p["current_trade_value"] for p in give_players)
    receive_total = sum(p["current_trade_value"] for p in receive_players)
    fairness_gap = receive_total - give_total  # positive = favorable for you
    
    # Pull your roster context
    your_roster = await _get_roster(db, your_team_id)
    your_positional_needs = _assess_positional_needs(your_roster)
    your_positional_surplus = _assess_positional_surplus(your_roster)
    
    # Timing flags from Trade Value agent
    timing_flags = []
    for p in give_players:
        if p.get("sell_high_flag"):
            timing_flags.append({
                "player": p["name"],
                "side": "give",
                "signal": "BUY_LOW_OPPORTUNITY",
                "reason": "You'd be selling low — recent slump is matchup-driven"
            })
    for p in receive_players:
        if p.get("sell_high_flag"):
            timing_flags.append({
                "player": p["name"],
                "side": "receive",
                "signal": "SELL_HIGH_WARNING",
                "reason": "Opponent is selling high — recent performance unsustainable"
            })
    
    # Opponent profile from Opponent Analyzer
    opponent_profile = await _get_opponent_profile(db, opponent_team_id)
    
    # Opponent's roster for need assessment
    opponent_roster = await _get_roster(db, opponent_team_id)
    opponent_needs = _assess_positional_needs(opponent_roster)
    
    # Does giving them what you're offering address their need?
    addresses_need = any(
        p["position"] in opponent_needs for p in give_players
    )
    
    # Does receiving what they're offering address your need?
    addresses_your_need = any(
        p["position"] in your_positional_needs for p in receive_players
    )
    
    return {
        "give": give_players,
        "receive": receive_players,
        "give_total_value": give_total,
        "receive_total_value": receive_total,
        "fairness_gap": fairness_gap,
        "timing_flags": timing_flags,
        "your_positional_needs": your_positional_needs,
        "your_positional_surplus": your_positional_surplus,
        "addresses_your_need": addresses_your_need,
        "opponent_profile": {
            "management_style": opponent_profile["apparent_management_style"],
            "current_record": opponent_profile["current_record"],
            "positional_needs": opponent_needs,
            "addresses_their_need": addresses_need,
            "threat_score": opponent_profile["threat_score"],
        }
    }
```

---

## Verdict calculation (Python, no API needed)

```python
def _calculate_verdict(
    fairness_gap: float,
    addresses_your_need: bool,
    timing_flags: list[dict]
) -> str:
    """
    Pure Python verdict — no AI needed for this part.
    Gap is receive_total - give_total (positive = you're getting more value).
    """
    
    # Start from raw fairness gap
    adjusted_gap = fairness_gap
    
    # Bonus if receiving at position of need
    if addresses_your_need:
        adjusted_gap += 5
    
    # Penalty if any SELL_HIGH_WARNING on received player
    sell_high_warnings = sum(
        1 for f in timing_flags
        if f["side"] == "receive" and f["signal"] == "SELL_HIGH_WARNING"
    )
    adjusted_gap -= sell_high_warnings * 8
    
    # Penalty if any BUY_LOW_OPPORTUNITY on given player
    buy_low_opps = sum(
        1 for f in timing_flags
        if f["side"] == "give" and f["signal"] == "BUY_LOW_OPPORTUNITY"
    )
    adjusted_gap -= buy_low_opps * 6
    
    if adjusted_gap > 10:    return "favorable"
    if adjusted_gap > 4:     return "slightly_favorable"
    if adjusted_gap > -4:    return "fair"
    if adjusted_gap > -10:   return "slightly_unfavorable"
    return "unfavorable"
```

---

## Acceptance probability (Python, informed by opponent profile)

```python
def _estimate_acceptance_probability(
    context: dict
) -> tuple[float, str]:
    """
    Estimate how likely the opponent is to accept this trade as submitted.
    Returns (probability 0.0-1.0, plain-language reason).
    """
    prob = 0.50  # Start at 50/50
    reasons = []
    
    opp = context["opponent_profile"]
    gap = context["fairness_gap"]
    
    # Does it address their need?
    if opp["addresses_their_need"]:
        prob += 0.20
        reasons.append(f"addresses their {context['give'][0]['position']} need")
    else:
        prob -= 0.15
        reasons.append("doesn't address a clear need")
    
    # Fairness perception (managers anchor on market value fairness)
    if gap < -8:   # You're getting much more
        prob -= 0.25
        reasons.append("appears lopsided at market value")
    elif gap > 8:  # They're getting much more
        prob += 0.15
        reasons.append("favorable for them at market value")
    
    # Management style adjustments
    style = opp["management_style"]
    if style == "urgency_driven" and opp["current_record"] in ["1-3","0-4","1-4","0-3"]:
        prob += 0.15
        reasons.append("they're struggling and likely motivated to shake things up")
    if style == "reactive":
        # Reactive managers overvalue recent performance
        for flag in context["timing_flags"]:
            if flag["side"] == "give" and flag["signal"] == "BUY_LOW_OPPORTUNITY":
                prob += 0.10  # They probably think that player is worse than they are
    if style == "name_brand":
        for p in context["give"]:
            if p.get("is_big_name"):
                prob += 0.08
    
    prob = max(0.05, min(0.95, prob))  # Clamp to reasonable range
    reason = " — ".join(reasons[:2])   # Top 2 reasons
    
    return round(prob, 2), reason
```

---

## Counter proposals

When verdict is `unfavorable` or `slightly_unfavorable`, generate alternatives:

```python
async def _generate_counter_proposals(
    context: dict,
    db: AsyncSession,
    max_proposals: int = 3
) -> list[dict]:
    """
    Find the nearest adjustments that:
    1. Flip verdict to favorable or slightly_favorable
    2. Keep acceptance_probability above 0.40
    3. Are actually feasible given your roster
    
    Strategies to try:
    - Swap one of your given players for a lesser player from your roster
    - Request a different (better) player from opponent instead
    - Add a player to your give side to sweeten the deal
    """
    proposals = []
    
    # Strategy 1: Swap given player down
    your_roster = await _get_roster(db, YOUR_TEAM_ID)
    for alt_player in your_roster:
        if alt_player["id"] in [p["id"] for p in context["give"]]:
            continue  # Already in the trade
        # Try replacing the highest-value give player with alt_player
        new_context = _simulate_trade_swap(context, give_swap=alt_player)
        new_verdict = _calculate_verdict(...)
        new_prob, new_reason = _estimate_acceptance_probability(new_context)
        if new_verdict in ("favorable", "slightly_favorable") and new_prob >= 0.40:
            proposals.append({
                "type": "swap_given",
                "description": f"Offer {alt_player['name']} instead of {context['give'][-1]['name']}",
                "new_verdict": new_verdict,
                "acceptance_probability": new_prob,
                "reasoning": new_reason
            })
    
    # Strategy 2: Request better player from opponent
    opponent_roster = await _get_roster(db, context["opponent_profile"]["team_id"])
    for alt_player in opponent_roster:
        if alt_player["current_trade_value"] <= context["receive"][0]["current_trade_value"]:
            continue  # Not an improvement
        new_context = _simulate_trade_swap(context, receive_swap=alt_player)
        new_verdict = _calculate_verdict(...)
        new_prob, new_reason = _estimate_acceptance_probability(new_context)
        if new_verdict in ("favorable", "slightly_favorable") and new_prob >= 0.40:
            proposals.append({
                "type": "request_upgrade",
                "description": f"Request {alt_player['name']} instead of {context['receive'][0]['name']}",
                "new_verdict": new_verdict,
                "acceptance_probability": new_prob,
                "reasoning": new_reason
            })
    
    # Sort by (probability × value_advantage), return top N
    proposals.sort(
        key=lambda p: p["acceptance_probability"] * (1 if "favorable" in p["new_verdict"] else 0.5),
        reverse=True
    )
    return proposals[:max_proposals]
```

---

## Sonnet call (synthesis only)

The Python code above handles fairness, verdict, and acceptance probability.
Sonnet is only used to write the human-readable reasoning summary — it should
NOT be recalculating values Python already computed.

```python
SYSTEM_PROMPT = """You are a fantasy football trade advisor.
You will receive a pre-analyzed trade with all calculations already done.
Your job is to write clear, plain-English explanations of the analysis.
Output ONLY valid JSON. No preamble. No markdown. No explanation outside the JSON.

Output schema:
{
  "timing_analysis": "1-2 sentences explaining the timing flags",
  "acceptance_reasoning": "1-2 sentences explaining why opponent would/wouldn't accept",
  "overall_summary": "1-2 sentences summarizing the overall recommendation"
}"""
```

---

## Final output schema

```json
{
  "verdict": "slightly_unfavorable",
  "fairness_gap": -8,
  "fairness_direction": "giving_more_value_than_receiving",
  "roster_fit_adjustment": "+5 (receiving at position of need)",
  "timing_flags": [
    {
      "player": "Justin Jefferson",
      "side": "receive",
      "signal": "SELL_HIGH_WARNING",
      "reason": "3 TDs last 2 weeks on 14% target share — TD regression likely"
    }
  ],
  "verdict_reasoning": "The value gap combined with a sell-high signal on Jefferson makes this unfavorable as submitted.",
  "acceptance_probability": 0.62,
  "acceptance_reasoning": "They're 3-4 and thin at RB — motivated to deal.",
  "counter_proposals": [
    {
      "type": "swap_given",
      "description": "Offer [Player D] instead of [Player B]",
      "new_verdict": "slightly_favorable",
      "acceptance_probability": 0.55,
      "reasoning": "Costs you bench depth not a starter, flips the value gap."
    }
  ],
  "overall_summary": "Pass on this trade as offered. Counter with the first proposal."
}
```

---

## React UI

### Trade input form
Two columns: "You Give" | "You Receive"
Each column: player search with autocomplete, add/remove players
Opponent selector: dropdown of league teams
"Analyze" button: triggers POST /trades/analyze

### Analysis results
After analysis returns:
- Verdict badge: FAVORABLE (green) / FAIR (blue) / UNFAVORABLE (red)
- Fairness breakdown: "You give $XX | You receive $XX | Gap: ±$XX"
- Roster fit note: if position of need
- Timing flags: yellow warning cards for each flag
- Acceptance probability: progress bar with percentage + reason
- Counter proposals: clickable cards
  - Clicking a counter pre-fills the trade input form with the adjusted trade
  - User can then re-analyze the counter before deciding whether to pitch it

---

## Required test cases

```python
def test_lopsided_trade_unfavorable_verdict():
    """$40 gap in opponent's favor → unfavorable"""

def test_balanced_trade_fair_verdict():
    """$3 gap → fair"""

def test_sell_high_flag_on_received_player():
    """Received player has sell_high_flag → SELL_HIGH_WARNING in timing_flags"""

def test_buy_low_flag_on_given_player():
    """Given player has buy_low_flag → BUY_LOW_OPPORTUNITY in timing_flags"""

def test_sell_high_warning_reduces_adjusted_gap():
    """SELL_HIGH_WARNING on received player worsens verdict"""

def test_buy_low_opportunity_reduces_adjusted_gap():
    """BUY_LOW_OPPORTUNITY on given player worsens verdict"""

def test_acceptance_probability_high_needy_opponent():
    """Opponent is 2-4, addresses their RB need → prob > 0.65"""

def test_acceptance_probability_low_no_need():
    """Opponent has no need for what's offered → prob < 0.40"""

def test_urgency_driven_losing_manager_higher_probability():
    """Urgency-driven manager on losing streak → acceptance bump"""

def test_counter_proposal_flips_to_favorable():
    """Counter proposal verdict must be favorable or slightly_favorable"""

def test_counter_proposal_acceptance_above_threshold():
    """All counter proposals must have acceptance_probability >= 0.40"""

def test_roster_context_adjusts_verdict():
    """Receiving at position of need adds positive adjustment"""

def test_counter_proposals_sorted_by_value_times_probability():
    """Best counter is first in list"""
```

---

## Verification before marking complete
1. Lopsided trade → unfavorable verdict with correct gap
2. Counter proposals flip verdict AND have >40% acceptance
3. Timing flags appear correctly for known sell-high/buy-low situations
4. **ASK USER** to test with 2-3 real trade scenarios from this season
5. Coverage 80%+

---

## Commit
```
feat(trade-analyzer): implement Trade Analyzer

Fairness analysis, timing flags, acceptance probability.
Counter proposal generation with feasibility filtering.
React UI with pre-fill from counter proposals.
Coverage: X%.
```
