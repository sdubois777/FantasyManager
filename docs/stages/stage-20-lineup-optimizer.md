# Stage 20: Lineup Optimizer

## Before starting, read:
- `docs/INSEASON.md` — Lineup Optimizer section
- `docs/rules/COST_RULES.md`
- Stage 15 (Roster Monitor) must be complete — snap count and usage data needed

---

## Goal
Every Thursday, the app tells you who to start. The reasoning is always
visible so you can override intelligently. The most important input is
Vegas implied team totals — this single number captures everything the
market knows about offensive environment for a given week.

---

## Model and cost parameters
- Model: `claude-haiku-4-5-20251001` — scoring and formatting, not reasoning
- Max tokens: 1000
- Trigger: Thursday weekly job (after injury reports and Vegas lines finalize)
- Also available on-demand via endpoint for mid-week check

---

## Run schedule

APScheduler job: Thursday 1pm ET (after Thursday injury reports and lines set)

```python
scheduler.add_job(
    lineup_optimizer.run_weekly,
    'cron',
    day_of_week='thu',
    hour=13,  # 1pm ET — after injury reports, lines set
    timezone='America/New_York',
    id='lineup_optimizer_weekly'
)
```

Also callable on-demand: `GET /lineup/week/{week_number}`

---

## Step 1 — Data collection (Python only, no API calls)

Collect all inputs for your rostered players before any AI call.
Pre-aggregate everything — never pass raw data to the model.

### Vegas implied team totals

```python
async def _get_vegas_implied_totals(week: int) -> dict[str, float]:
    """
    Scrape Vegas implied team totals for the week.
    This is the most predictive single input for weekly scoring.
    
    Sources (try in order, use first that works):
    1. The Odds API (free tier) — https://api.the-odds-api.com
    2. Scrape from covers.com or vegasinsider.com
    3. Fall back to ESPN's game lines if above fail
    
    Returns: {team_abbr: implied_total}
    e.g. {"KC": 28.5, "LAC": 21.0, ...}
    
    Implied total = (over/under + spread) / 2
    If KC is -7 with O/U of 49:
      KC implied = (49 + 7) / 2 = 28.0
      opponent implied = 49 - 28 = 21.0
    """
    # ASK USER which data source to use if none are configured
```

**ASK USER:** "For Vegas implied totals we need a data source.
Options:
1. The Odds API — free tier gives 500 requests/month, should be plenty
   Sign up at: https://the-odds-api.com
   Provide your API key and I'll integrate it.
2. I can scrape from a public site but it's less reliable.
Which do you prefer?"

### Weather data

```python
async def _get_weather_data(week: int) -> dict[str, dict]:
    """
    Get weather forecasts for outdoor stadiums.
    Only matters for outdoor cold-weather teams Nov-Jan.
    
    Outdoor stadiums to monitor:
    BUF (Buffalo), GB (Green Bay), CHI (Chicago), 
    NE (New England), CLE (Cleveland), PIT (Pittsburgh),
    NYG/NYJ (MetLife — shared outdoor), PHI (Philadelphia),
    DAL (Arlington — technically outdoor)
    
    Apply passing game penalty when:
    - Wind > 15mph → -10% to QB, WR, TE scores
    - Wind > 25mph → -25% to QB, WR, TE scores
    - Temperature < 20°F → -5% to all skill positions
    - Rain/snow → -8% to passing game
    
    Source: OpenWeatherMap API (free tier sufficient)
    """
```

**ASK USER:** "For weather data I can use OpenWeatherMap (free).
Do you have an API key, or should I sign up for one?"

### Injury report status

```python
async def _get_injury_statuses(week: int) -> dict[str, str]:
    """
    Pull practice participation from Yahoo API for rostered players.
    Status values: "full" | "limited" | "dnp" | "questionable" | "out"
    
    Confidence multipliers by status:
    - full: 1.0
    - questionable: 0.75
    - limited: 0.65
    - dnp (week of game): 0.30
    - out: 0.0
    """
```

### Snap count trend

```python
async def _get_snap_trends(db: AsyncSession) -> dict[str, dict]:
    """
    Pull from season_roster weekly_snap_counts arrays.
    Already populated by Roster Monitor agent.
    
    Returns trend signal per player:
    - "rising": snap count up 2+ consecutive weeks → upward trend
    - "stable": consistent snap counts
    - "declining": down 2+ consecutive weeks → concern
    - "new_role": sudden spike from low baseline → emerging
    """
```

---

## Step 2 — Player scoring (Python, no API)

Score every rostered player for the week before the AI call.

```python
def _score_player_for_week(
    player: dict,
    vegas_total: float,
    weather: dict,
    injury_status: str,
    snap_trend: str,
    matchup_grade: str,  # from player_schedules table, this week's opponent
) -> dict:
    """
    Returns a scoring dict. All math done in Python.
    Haiku only gets the pre-scored summary.
    """
    
    base_score = player["baseline_value"] / 17  # Weekly average
    
    # Vegas implied total — most important factor
    # League average implied total ≈ 23 points
    # +/- impact based on deviation from average
    vegas_multiplier = 1.0 + ((vegas_total - 23) * 0.025)
    
    # Matchup grade
    matchup_multiplier = {
        "favorable": 1.15,
        "neutral": 1.00,
        "tough": 0.85
    }.get(matchup_grade, 1.00)
    
    # Injury status
    injury_multiplier = {
        "full": 1.0,
        "questionable": 0.75,
        "limited": 0.65,
        "dnp": 0.30,
        "out": 0.0
    }.get(injury_status, 1.0)
    
    # Snap trend
    trend_multiplier = {
        "rising": 1.08,
        "stable": 1.00,
        "declining": 0.90,
        "new_role": 1.12
    }.get(snap_trend, 1.00)
    
    # Weather (only affects passing game positions)
    weather_multiplier = 1.0
    if player["position"] in ("QB", "WR", "TE"):
        if weather.get("wind_mph", 0) > 25:
            weather_multiplier = 0.75
        elif weather.get("wind_mph", 0) > 15:
            weather_multiplier = 0.90
        if weather.get("temp_f", 60) < 20:
            weather_multiplier *= 0.95
    
    projected_score = (
        base_score *
        vegas_multiplier *
        matchup_multiplier *
        injury_multiplier *
        trend_multiplier *
        weather_multiplier
    )
    
    # Determine confidence
    if injury_status in ("questionable", "limited"):
        confidence = "low"
    elif matchup_grade == "tough" or snap_trend == "declining":
        confidence = "medium"
    elif matchup_grade == "favorable" and vegas_total > 27:
        confidence = "high"
    else:
        confidence = "medium"
    
    # Key reasons for this score
    reasons = []
    if vegas_total > 27: reasons.append(f"Team implied {vegas_total:.1f} pts — excellent offensive environment")
    if vegas_total < 19: reasons.append(f"Team implied {vegas_total:.1f} pts — tough offensive environment")
    if matchup_grade == "favorable": reasons.append("Favorable matchup this week")
    if matchup_grade == "tough": reasons.append("Tough matchup this week")
    if snap_trend == "rising": reasons.append("Snap count trending up last 2 weeks")
    if snap_trend == "declining": reasons.append("⚠️ Snap count declining last 2 weeks")
    if injury_status == "questionable": reasons.append("⚠️ Questionable — monitor status")
    if weather_multiplier < 0.90: reasons.append(f"⚠️ Wind {weather.get('wind_mph')}mph — passing game suppressed")
    
    return {
        "player_id": player["id"],
        "player_name": player["name"],
        "position": player["position"],
        "projected_score": round(projected_score, 1),
        "confidence": confidence,
        "injury_status": injury_status,
        "reasons": reasons[:3],  # Top 3 reasons
        "locked": False  # User can lock players regardless of recommendation
    }
```

---

## Step 3 — Lineup optimization (Python, no API)

```python
def _optimize_lineup(
    scored_players: list[dict],
    league_settings: LeagueSettings,
    locked_players: set[str]  # Player IDs user has manually locked
) -> dict:
    """
    Find optimal starting lineup given roster slot constraints.
    Handles flex slot optimization.
    
    Slots: 1 QB, 2 RB, 2 WR, 1 FLEX (RB/WR/TE), 1 TE, 1 K, 1 DEF
    """
    lineup = {}
    available = [p for p in scored_players if p["injury_status"] != "out"]
    
    # First: lock any manually locked players into their slots
    for p in available:
        if p["player_id"] in locked_players:
            lineup[p["position"]] = p  # Lock them in
    
    # Fill QB
    qbs = sorted([p for p in available if p["position"] == "QB"],
                 key=lambda p: p["projected_score"], reverse=True)
    if "QB" not in lineup:
        lineup["QB"] = qbs[0] if qbs else None
    
    # Fill RB (2 slots)
    rbs = sorted([p for p in available if p["position"] == "RB"],
                 key=lambda p: p["projected_score"], reverse=True)
    # ... fill RB1, RB2
    
    # Fill WR (2 slots), TE (1 slot), K, DEF similarly
    
    # FLEX optimization: choose the highest-scoring remaining 
    # eligible player (RB/WR/TE) not already starting
    flex_eligible = [
        p for p in available
        if p["position"] in ("RB", "WR", "TE")
        and p not in lineup.values()
    ]
    flex_eligible.sort(key=lambda p: p["projected_score"], reverse=True)
    lineup["FLEX"] = flex_eligible[0] if flex_eligible else None
    
    return lineup
```

---

## Step 4 — Haiku call (formatting and edge cases only)

```python
SYSTEM_PROMPT = """You are a fantasy football lineup advisor.
You will receive pre-scored player data with all calculations already done.
Your job is to identify any non-obvious considerations the scores might miss
and write clear start/sit reasoning.

Do NOT recalculate scores — use the provided projected_score values.
Focus on: injury risk nuances, matchup context the scores don't capture,
and any start/sit decisions that are genuinely close calls.

Output ONLY valid JSON array. No preamble. No markdown.
One object per roster player with these fields:
{
  "player_id": "...",
  "recommendation": "start|sit|flex_start|flex_sit",
  "reasoning": "one sentence — most important factor",
  "flag": null or "injury_concern|matchup_mismatch|snap_risk"
}"""
```

---

## Required test cases

```python
def test_high_vegas_total_boosts_player_score():
    """Team implied 30pts → player score higher than league average context"""
    score = _score_player(player, vegas_total=30.0, ...)
    avg_score = _score_player(player, vegas_total=23.0, ...)
    assert score["projected_score"] > avg_score["projected_score"]

def test_low_vegas_total_depresses_score():
    """Team implied 17pts → player score lower than average"""
    score = _score_player(player, vegas_total=17.0, ...)
    avg_score = _score_player(player, vegas_total=23.0, ...)
    assert score["projected_score"] < avg_score["projected_score"]

def test_weather_penalty_applied_passing_game():
    """Wind 20mph → WR projected_score reduced"""
    no_wind = _score_player(wr_player, weather={"wind_mph": 5}, ...)
    wind = _score_player(wr_player, weather={"wind_mph": 20}, ...)
    assert wind["projected_score"] < no_wind["projected_score"]

def test_weather_not_applied_to_rb():
    """Wind penalty should NOT affect RB scores"""
    no_wind = _score_player(rb_player, weather={"wind_mph": 5}, ...)
    wind = _score_player(rb_player, weather={"wind_mph": 25}, ...)
    assert wind["projected_score"] == pytest.approx(no_wind["projected_score"])

def test_questionable_player_low_confidence():
    score = _score_player(player, injury_status="questionable", ...)
    assert score["confidence"] == "low"

def test_out_player_zero_score():
    score = _score_player(player, injury_status="out", ...)
    assert score["projected_score"] == 0.0

def test_flex_slot_optimized_correctly():
    """Highest projected RB/WR/TE not already starting goes in FLEX"""
    lineup = _optimize_lineup(scored_players, league_settings, locked={})
    flex = lineup["FLEX"]
    all_non_starters = [
        p for p in scored_players
        if p["position"] in ("RB", "WR", "TE")
        and p not in lineup.values()
        and p != flex
    ]
    assert all(
        flex["projected_score"] >= p["projected_score"]
        for p in all_non_starters
    )

def test_locked_player_not_overridden():
    """Locked player stays in lineup regardless of projected score"""
    worst_qb = min(qbs, key=lambda p: p["projected_score"])
    lineup = _optimize_lineup(scored_players, league_settings,
                              locked={worst_qb["player_id"]})
    assert lineup["QB"]["player_id"] == worst_qb["player_id"]

def test_reasoning_always_included_in_output():
    """Every player in lineup output must have non-empty reasoning"""
    lineup = _optimize_lineup(...)
    for pos, player in lineup.items():
        if player:
            assert len(player["reasons"]) > 0

def test_vegas_totals_fetched_for_correct_week():
    """Vegas totals use dynamic week number, not hardcoded"""
    # Verify no hardcoded week numbers in the fetcher
```

---

## Verification before marking complete
1. **ASK USER** which Vegas data source to use, configure it
2. **ASK USER** to confirm weather API setup
3. Run for a real week — lineup recommendations look reasonable
4. Flex slot optimization picks the right player
5. Locked player stays in lineup
6. Reasoning is always present and makes sense
7. **ASK USER** to compare recommendation to their gut instinct on a few players
8. All tests passing, coverage 80%+

---

## Commit
```
feat(lineup-optimizer): implement Lineup Optimizer

Weekly start/sit with Vegas lines, matchups, injury reports, weather.
Flex slot optimization implemented.
Lock toggle allows manual overrides.
Reasoning always included for every decision.
Coverage: X%.
```
