# Stage 12: Live Draft Agent

## Before starting, read:
- `docs/LIVE_DRAFT.md` — Live Draft Agent section
- `docs/ARCHITECTURE.md` — Two-Value Auction System, Opponent Modeling
- `docs/rules/PATTERNS.md` — Pattern 6: run_agent() only for live draft
- Stage 11 must be complete before starting this stage

---

## Goal
When a player is nominated at auction, the app surfaces a recommendation
within 2 seconds: what to bid, whether to block, and whether an opponent
is building a dangerous roster. All intelligence is pre-loaded from the
draft bible — the live agent queries results, it does not do research.

---

## Model and cost parameters
- Model: `claude-sonnet-4-6`
- Max tokens: 400 per recommendation
- This is the ONE agent that may use direct `messages.create()` without
  the iterative tool loop — single call, structured JSON output
- Expected: ~1 API call per nomination, ~30-50 nominations per draft

---

## Architecture

```
Nomination event received from Playwright bridge
  ↓
DraftStateManager.record_nomination(player_id)
  ↓
DraftBibleService.get_player_record(player_id)  ← single DB query
  ↓
DependencyResolver.apply_active_flags(record, drafted_players)
  ↓
BudgetCalculator.get_constraints(your_roster, league_settings)
  ↓
OpponentThreatAnalyzer.evaluate_block_value(player, opponent_rosters)
  ↓
Claude Sonnet call (400 tokens max) → recommendation JSON
  ↓
WebSocket broadcast to React UI
```

Total target: under 2000ms end-to-end.

---

## Component 1: DraftStateManager

File: `backend/engines/draft_state.py`

Maintains live state updated after EVERY pick event from the bridge.
This is pure Python — no API calls.

```python
class DraftStateManager:
    def __init__(self, league_settings: LeagueSettings):
        self.league_settings = league_settings
        self.picks: list[DraftPick] = []
        self.opponent_rosters: dict[str, list[DraftPick]] = {}
        self.your_roster: list[DraftPick] = []
        self.opponent_budgets: dict[str, int] = {}
        self.your_budget: int = league_settings.auction_budget
    
    def record_pick(self, pick: DraftPick) -> None:
        """Called after every draft_pick event from bridge."""
        self.picks.append(pick)
        if pick.team_id == YOUR_TEAM_ID:
            self.your_roster.append(pick)
            self.your_budget -= pick.price
        else:
            self.opponent_rosters.setdefault(pick.team_id, []).append(pick)
            self.opponent_budgets[pick.team_id] = (
                self.opponent_budgets.get(pick.team_id,
                self.league_settings.auction_budget) - pick.price
            )
    
    def get_drafted_player_ids(self) -> set[str]:
        return {p.player_id for p in self.picks}
    
    def get_your_remaining_budget(self) -> int:
        return self.your_budget
    
    def get_minimum_completion_budget(self) -> int:
        """Minimum $1 per remaining roster slot."""
        slots_filled = len(self.your_roster)
        slots_remaining = (
            self.league_settings.total_roster_size - slots_filled
        )
        return slots_remaining  # $1 per slot minimum
    
    def get_spendable_on_this_player(self) -> int:
        return (
            self.get_your_remaining_budget() -
            self.get_minimum_completion_budget()
        )
```

---

## Component 2: DependencyResolver

File: `backend/engines/dependency_resolver.py`

Applies active flags based on current draft state.
This is what catches the McConkey/Allen scenario in real time.

```python
class DependencyResolver:
    
    def apply_active_flags(
        self,
        player_record: dict,
        drafted_player_ids: set[str]
    ) -> tuple[list[dict], float]:
        """
        Check all dependency flags for a player.
        If trigger player is already drafted → flag is active.
        
        Returns:
          active_flags: list of flag dicts with their value impacts
          total_value_modifier: combined multiplier to apply to bid ceiling
        """
        active_flags = []
        total_modifier = 0.0
        
        for flag in player_record.get("dependencies", []):
            trigger_id = flag.get("trigger_player_id")
            if not trigger_id:
                continue
            
            trigger_drafted = trigger_id in drafted_player_ids
            
            # DISPLACED: active when trigger IS drafted (playing)
            if (flag["flag_type"] == "displaced" and
                flag["trigger_condition"] == "active_and_healthy" and
                trigger_drafted):
                active_flags.append({
                    **flag,
                    "active": True,
                    "reason": f"{flag['trigger_player_name']} already drafted"
                })
                total_modifier += flag["value_impact_pct"]
            
            # BENEFICIARY: active when trigger is NOT drafted (or gone)
            # Note: during draft, not-drafted ≠ absent
            # Only activate beneficiary if trigger was drafted by someone
            # else AND is now injured (can't know during draft, skip this)
            
            # CONTINGENT: surface as info, not active during draft
            # (can't know injury status during auction)
        
        return active_flags, total_modifier
```

---

## Component 3: OpponentThreatAnalyzer

File: `backend/engines/opponent_threat.py`

```python
class OpponentThreatAnalyzer:
    
    # Named combo patterns — these get flagged explicitly
    COMBO_PATTERNS = [
        {
            "name": "Elite RB Stack",
            "condition": "2+ tier-1 RBs on same roster",
            "severity": "critical",
            "message": "Elite RB stack — historically dominant. Block if possible."
        },
        {
            "name": "Elite RB + Elite TE",
            "condition": "tier-1 RB + tier-1 TE",
            "severity": "high",
            "message": "Positional scarcity lock — dangerous floor."
        },
        {
            "name": "QB/WR Stack",
            "condition": "QB + WR1 from same NFL team",
            "severity": "medium",
            "message": "Stack bonus upside — volatile ceiling."
        }
    ]
    
    def get_threat_score(self, roster: list[DraftPick]) -> int:
        """0-100 composite threat score for an opponent's current roster."""
    
    def get_block_value(
        self,
        player: dict,
        opponent_roster: list[DraftPick],
        opponent_budget: int
    ) -> float:
        """
        What is this player worth to THIS opponent specifically?
        Higher than player's personal value = block flag warranted.
        Suppress if opponent budget < $15 (they can't afford danger).
        """
        if opponent_budget < 15:
            return 0.0  # Suppress — they're tapped out
        
        # Calculate how much player would elevate opponent's threat score
        ...
    
    def get_active_combo_flags(
        self, opponent_roster: list[DraftPick]
    ) -> list[str]:
        """Check if opponent's current roster matches any named combos."""
    
    def get_nomination_targets(
        self,
        all_players: list[dict],
        your_roster: list[DraftPick],
        your_budget: int
    ) -> list[dict]:
        """
        Players to nominate when it's your turn.
        Target: high market value, you don't want them.
        Forces opponents to spend, drains their budgets.
        """
```

---

## Component 4: Live Draft Engine (main orchestrator)

File: `backend/engines/live_draft.py`

```python
class LiveDraftEngine:
    
    def __init__(
        self,
        state: DraftStateManager,
        resolver: DependencyResolver,
        threat_analyzer: OpponentThreatAnalyzer,
        db: AsyncSession,
        ws_manager: WebSocketManager,
    ):
        self._client = anthropic.AsyncAnthropic()
    
    async def on_nomination(self, event: dict) -> None:
        """
        Called immediately when a nomination event fires from bridge.
        Must complete and emit recommendation in under 2 seconds.
        """
        player_id = event["player_id"]
        start = time.monotonic()
        
        # Step 1: Pull player record (single DB query)
        record = await self._get_player_record(player_id)
        if not record:
            await self._emit_unknown_player(player_id)
            return
        
        # Step 2: Apply dependency flags (pure Python, instant)
        drafted_ids = self.state.get_drafted_player_ids()
        active_flags, flag_modifier = self.resolver.apply_active_flags(
            record, drafted_ids
        )
        
        # Step 3: Calculate budget constraints (pure Python, instant)
        spendable = self.state.get_spendable_on_this_player()
        
        # Step 4: Calculate block values per opponent (pure Python)
        block_analysis = {}
        for team_id, roster in self.state.opponent_rosters.items():
            budget = self.state.opponent_budgets.get(team_id, 0)
            block_val = self.threat_analyzer.get_block_value(
                record, roster, budget
            )
            block_analysis[team_id] = block_val
        max_block_value = max(block_analysis.values(), default=0)
        
        # Step 5: Get opponent combo alerts
        opponent_alerts = []
        for team_id, roster in self.state.opponent_rosters.items():
            combos = self.threat_analyzer.get_active_combo_flags(roster)
            opponent_alerts.extend(combos)
        
        # Step 6: Single Sonnet call to synthesize recommendation
        recommendation = await self._get_recommendation(
            record=record,
            active_flags=active_flags,
            flag_modifier=flag_modifier,
            spendable=spendable,
            max_block_value=max_block_value,
            budget_allows_block=spendable >= max_block_value,
            opponent_alerts=opponent_alerts,
        )
        
        elapsed = (time.monotonic() - start) * 1000
        logger.info("Recommendation in %.0fms", elapsed)
        
        # Step 7: Broadcast to React UI
        await self.ws_manager.broadcast({
            "type": "recommendation",
            **recommendation,
            "elapsed_ms": elapsed
        })
    
    async def _get_recommendation(self, **context) -> dict:
        """
        Single Sonnet call. 400 tokens max.
        Output is structured JSON only.
        """
        system = """You are a fantasy football auction draft advisor.
Analyze the nomination and output ONLY a JSON object. No explanation.
No preamble. No markdown. Your response must be parseable by json.loads().

Output schema:
{
  "action": "buy|bid_to|block|pass",
  "bid_ceiling": integer,
  "reasoning": "one sentence max",
  "confidence": "high|medium|low"
}"""
        
        response = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system,
            messages=[{
                "role": "user",
                "content": json.dumps(context, default=str)
            }]
        )
        
        raw = parse_json_output(response.content[0].text)
        
        # Merge with pre-computed context
        return {
            **raw,
            "player_name": context["record"]["name"],
            "system_value": context["record"]["system_value"],
            "market_value": context["record"]["market_value"],
            "active_flags": context["active_flags"],
            "opponent_alerts": context["opponent_alerts"],
            "block_value": context["max_block_value"],
            "budget_allows_block": context["budget_allows_block"],
            "budget_summary": {
                "your_remaining": self.state.get_your_remaining_budget(),
                "spendable_on_this_player": context["spendable"],
                "minimum_completion_budget": (
                    self.state.get_minimum_completion_budget()
                ),
                "roster_slots_remaining": (
                    self.state.league_settings.total_roster_size -
                    len(self.state.your_roster)
                )
            }
        }
    
    async def on_pick_confirmed(self, event: dict) -> None:
        """Update state after every pick — runs after every draft_pick event."""
        pick = DraftPick(
            player_id=event["player_id"],
            team_id=event["team_id"],
            price=event["final_price"]
        )
        self.state.record_pick(pick)
        
        # Recalculate all opponent threat scores
        for team_id, roster in self.state.opponent_rosters.items():
            score = self.threat_analyzer.get_threat_score(roster)
            combos = self.threat_analyzer.get_active_combo_flags(roster)
            if combos:
                await self.ws_manager.broadcast({
                    "type": "opponent_combo_alert",
                    "team_id": team_id,
                    "combos": combos,
                    "threat_score": score
                })
```

---

## Required test cases

```python
# tests/unit/engines/test_live_draft.py

def test_displaced_flag_activates_when_trigger_drafted():
    """
    McConkey has DISPLACED flag triggered by Allen.
    Allen is in drafted_player_ids.
    McConkey's active_flags must contain the displacement.
    bid_ceiling must be lower than pre-flag value.
    """
    record = load_fixture("players.json")[0]  # McConkey with DISPLACED flag
    drafted = {ALLEN_PLAYER_ID}
    flags, modifier = resolver.apply_active_flags(record, drafted)
    assert any(f["flag_type"] == "displaced" for f in flags)
    assert modifier < 0  # Negative impact applied

def test_displaced_flag_inactive_when_trigger_not_drafted():
    record = load_fixture("players.json")[0]
    drafted = set()  # Allen not drafted
    flags, modifier = resolver.apply_active_flags(record, drafted)
    assert not any(f["flag_type"] == "displaced" for f in flags)
    assert modifier == 0.0

def test_block_flag_fires_on_combo_threat():
    """Opponent has CMC. Jonathan Taylor nominated. Block value > personal value."""
    opponent_roster = [DraftPick(player_id=CMC_ID, tier=1, position="RB")]
    block_val = threat_analyzer.get_block_value(
        TAYLOR_RECORD, opponent_roster, opponent_budget=80
    )
    assert block_val > TAYLOR_RECORD["system_value"]

def test_block_flag_suppressed_low_opponent_budget():
    """Opponent has $12 left. Block value returns 0 regardless."""
    block_val = threat_analyzer.get_block_value(
        TAYLOR_RECORD, [], opponent_budget=12
    )
    assert block_val == 0.0

def test_block_flag_suppressed_insufficient_own_budget():
    """Can't afford block without going below minimum completion budget."""
    state = DraftStateManager(league_settings)
    state.your_budget = 20
    state.your_roster = [Mock()] * 9  # 6 slots left, need $6 minimum
    spendable = state.get_spendable_on_this_player()
    # If block value is $18 and spendable is $14, budget_allows_block = False
    assert spendable < 18

def test_bid_ceiling_tier1_uses_anchor_weight():
    """Tier 1 player: ceiling blends system + market at 0.80 anchor."""
    player = {"tier": 1, "system_value": 58, "market_value": 68}
    ceiling = calculate_bid_ceiling(player, active_flags=[], flag_modifier=0)
    # 58 * 0.20 + 68 * 0.80 = 65.6 * scarcity_modifier
    assert 60 < ceiling < 85

def test_bid_ceiling_tier4_ignores_anchor():
    """Tier 4: ceiling uses system value only."""
    player = {"tier": 4, "system_value": 12, "market_value": 18}
    ceiling = calculate_bid_ceiling(player, active_flags=[], flag_modifier=0)
    assert ceiling == pytest.approx(12, abs=2)

def test_nomination_suggestion_drains_opponent_budget():
    """Nominated players should have high market value, user doesn't want them."""
    targets = threat_analyzer.get_nomination_targets(
        all_players, your_roster=[], your_budget=150
    )
    for target in targets:
        assert target["market_value"] > target["system_value"]

def test_budget_summary_accurate_mid_draft():
    """After 5 known picks, budget summary reflects correct remaining amounts."""
    state = DraftStateManager(league_settings)
    for pick in FIXTURE_PICKS[:5]:
        state.record_pick(pick)
    assert state.get_your_remaining_budget() == 200 - sum(
        p.price for p in FIXTURE_PICKS[:5] if p.team_id == YOUR_TEAM_ID
    )

def test_recommendation_fires_under_2_seconds(mock_anthropic):
    """End-to-end recommendation must complete in under 2000ms with mocked deps."""
    import time
    start = time.monotonic()
    asyncio.run(engine.on_nomination(FIXTURE_NOMINATION_EVENT))
    elapsed = (time.monotonic() - start) * 1000
    assert elapsed < 2000, f"Recommendation took {elapsed:.0f}ms — too slow"

def test_opponent_threat_score_updates_after_pick():
    """After recording a pick, opponent threat score reflects new roster."""
    state = DraftStateManager(league_settings)
    score_before = threat_analyzer.get_threat_score([])
    state.record_pick(DraftPick(player_id=CMC_ID, team_id="opp1", price=65))
    score_after = threat_analyzer.get_threat_score(
        state.opponent_rosters["opp1"]
    )
    assert score_after > score_before

def test_combo_threat_flag_fires_second_elite_rb():
    """Second tier-1 RB drafted by same opponent → combo alert broadcast."""
    roster = [
        DraftPick(player_id=CMC_ID, tier=1, position="RB"),
        DraftPick(player_id=TAYLOR_ID, tier=1, position="RB"),
    ]
    combos = threat_analyzer.get_active_combo_flags(roster)
    assert any("RB Stack" in c or "Elite RB" in c for c in combos)
```

---

## Verification before marking complete
1. `test_recommendation_fires_under_2_seconds` passes — non-negotiable
2. All 12 named test cases pass
3. Dependency flag activation verified with McConkey/Allen fixture
4. Block suppression tested at $12 and $80 opponent budgets
5. Combo threat fires when second elite RB drafted by opponent
6. Coverage 80%+ on `live_draft.py`, `draft_state.py`, `dependency_resolver.py`, `opponent_threat.py`

---

## Commit
```
feat(live-draft): implement Live Draft Agent

Real-time recommendations with dependency flag activation.
McConkey/Allen displacement logic verified in tests.
Opponent combo threat detection and block flag logic.
All recommendations under 2 seconds (tested).
Coverage: X%.
```
