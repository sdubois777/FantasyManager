# Stages 14-16

Stages 11, 12, and 13 have been moved to individual files:
- `docs/stages/stage-11-yahoo-playwright.md`
- `docs/stages/stage-12-live-draft.md`
- `docs/stages/stage-13-draft-ui.md`

---

# Stage 14: Season Roster Store + Post-Draft Sync

## Before starting, read:
- `docs/INSEASON.md`
- `docs/ARCHITECTURE.md` — season_roster table schema

---

## Goal
After draft completes, all drafted players flow into season roster store.
Draft bible records preserved and extended with weekly tracking fields.

---

## Tasks

### 1. Post-draft sync
After draft ends, pull final results from Yahoo API.
Match each pick to draft bible player records.
Populate `season_roster` table:
- `player_id` — linked to draft bible
- `yahoo_team_id` — who owns them
- `acquisition_price` — what was paid
- `acquisition_week` — 0 (draft)

### 2. Initialize weekly tracking arrays
`weekly_stats`, `weekly_snap_counts`, `weekly_target_share` — all initialized as `[]`.

### 3. APScheduler in-season jobs
Register all weekly jobs (don't implement the agents yet — just register the jobs):
- Roster Monitor: Wednesday 8am ET
- Trade Value: Wednesday 9am ET
- Opponent Analyzer: Wednesday 10am ET
- Waiver Wire: Tuesday 11pm ET
- Beat Reporter: daily 7am ET (already registered from Stage 8)

### 4. Season roster API endpoints
```
GET /roster/mine                 → your current roster
GET /roster/league               → all teams' rosters
GET /roster/opponent/{team_id}   → specific opponent roster
```

---

## Required test cases
```python
def test_draft_results_synced_to_season_roster()
def test_acquisition_price_stored_correctly()
def test_weekly_arrays_initialized_empty()
def test_scheduler_jobs_registered()
def test_roster_endpoint_returns_correct_players()
```

---

## Commit
```
feat(season-store): implement season roster store and post-draft sync

Draft results synced to season_roster table.
APScheduler weekly jobs registered.
Roster API endpoints implemented.
Coverage: X%.
```

---
---

# Stage 15: Roster Monitor Agent

## Before starting, read:
- `docs/INSEASON.md` — Roster Monitor section
- `docs/rules/COST_RULES.md`

---

## Goal
Weekly data refresh keeps season roster store current.
Sell-high and buy-low flags updated after every week.

---

## Model: `claude-haiku-4-5-20251001`

---

## Tasks

### 1. Weekly stats pull
Every Wednesday: pull stats from Yahoo API for all rostered players.
Update `weekly_stats`, `weekly_snap_counts`, `weekly_target_share` arrays.

### 2. Usage trend detection
Detect snap count dropping 2+ consecutive weeks → set `injury_concern_flag`.
Detect target share rising 2+ consecutive weeks → positive signal.

### 3. Injury report monitoring
Pull Wednesday injury report practice participation from Yahoo API.
Flag any rostered players listed as Limited or DNP.
Set `injury_concern_flag` = true.

### 4. Trade value flags
`sell_high_flag`: recent TDs outpacing target share (TD regression likely).
`buy_low_flag`: recent slump confirmed as matchup-driven by schedule data.
`value_trend`: compare current trade value to last week's.

---

## Required test cases
```python
def test_snap_count_decline_2_weeks_sets_flag()
def test_injury_report_limited_sets_flag()
def test_sell_high_flag_td_spike_low_targets()
def test_buy_low_flag_matchup_slump()
def test_value_trend_updated_weekly()
def test_weekly_arrays_appended_not_replaced()
```

---

## Commit
```
feat(roster-monitor): implement Roster Monitor Agent

Weekly stats sync, usage trend detection, injury flags.
Sell-high and buy-low flags automated.
Coverage: X%.
```

---
---

# Stage 16: Opponent Analyzer Agent

## Before starting, read:
- `docs/INSEASON.md` — Opponent Analyzer section

---

## Goal
Running profiles on all other managers, updated weekly.
Management style detection enables acceptance probability modeling for trades.

---

## Model: `claude-sonnet-4-6` (behavioral reasoning required)

---

## Tasks

### 1. Per-opponent profile
Build and maintain in DB (new table `opponent_profiles`):
```json
{
  "team_id": "...",
  "team_name": "...",
  "positional_scores": {},
  "threat_score": 0,
  "apparent_management_style": "reactive|analytical|name_brand|urgency_driven",
  "roster_vulnerabilities": [],
  "trade_history": [],
  "current_record": "",
  "playoff_position": 0
}
```

### 2. Management style detection
- **Reactive**: frequently starts players off big recent games
- **Name-brand biased**: holds big names past their value
- **Analytical**: trade offers show schedule/usage awareness
- **Urgency-driven**: losing streak = willing to overpay

### 3. Vulnerability detection
- Bye week conflicts (multiple starters on same bye)
- Injury exposure (multiple high-risk players)
- Playoff schedule problems (brutal weeks 14-17)
- Positional weakness (bottom-tier at a starting position)

### 4. Threat score
0-100 composite of roster quality, updated after every weekly sync.

---

## Required test cases
```python
def test_management_style_reactive_detected()
def test_management_style_analytical_detected()
def test_bye_conflict_vulnerability_detected()
def test_playoff_schedule_vulnerability_detected()
def test_threat_score_updates_weekly()
def test_opponent_profile_created_for_all_teams()
```

---

## Commit
```
feat(opponent-analyzer): implement Opponent Analyzer Agent

Per-opponent profiles with management style and vulnerability detection.
Threat scores updated weekly. Coverage: X%.
```
