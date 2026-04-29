# Fantasy Football AI Platform — Project Context

## How to Use This Document

Read this entire document before writing any code. It contains every architectural decision, data schema, agent design, and build instruction for the project. When you need credentials, account access, API keys, or any external setup that requires human action, **stop and ask the user** before proceeding. Do not guess at credentials or skip steps that require human input.

When a build stage is complete, confirm it with the user before moving to the next stage.

---

## Project Overview

A full-season fantasy football management platform powered by AI agents. The system has three distinct phases:

1. **Pre-draft pipeline** — Six research agents run before draft day, producing a structured "draft bible" of every draftable player
2. **Live draft phase** — A live draft agent reads the draft bible and controls the Yahoo Fantasy draft room directly from the app UI, providing real-time bid ceilings, opponent block flags, and budget alerts
3. **In-season management** — Trade analyzer, trade suggester, lineup optimizer, and waiver wire agent run throughout the season

The core philosophy: **do not trust third-party projections**. Sites like FantasyPros aggregate consensus opinion which is slow to incorporate second-order effects (e.g. a veteran receiver returning to a team deflating the incumbent receiver's target share). This system builds its own valuations from raw data and chain-of-reasoning analysis.

The user's league is on **Yahoo Fantasy**. Draft format is **auction draft**.

---

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python 3.11+ | All backend and agent code |
| Package manager | uv | Faster than pip |
| AI model | Claude Sonnet (latest) | Via Anthropic SDK |
| Agent layer | Anthropic SDK native tool use | No LangChain/CrewAI — direct SDK for full transparency |
| Primary database | PostgreSQL 16 | Draft bible, season store, all structured data |
| Vector search | pgvector extension | RAG lookups within same DB |
| ORM | SQLAlchemy 2.0 | Async with asyncpg driver |
| Migrations | Alembic | Schema version control |
| Backend framework | FastAPI | Async, WebSocket support built in |
| Live events | WebSockets (FastAPI native) | Push-based, no polling |
| Task scheduling | APScheduler | Agent pipeline scheduling |
| HTTP client | httpx | Async HTTP |
| Yahoo draft control | Playwright | Browser automation for draft room |
| Frontend framework | React + Vite | |
| Frontend styling | Tailwind CSS | |
| Frontend state | Zustand | Lightweight, no Redux overhead |
| Frontend live updates | socket.io-client | Pairs with FastAPI WebSocket layer |
| NFL data | nfl_data_py | Free, comprehensive play-by-play |
| Advanced metrics | nflfastR (via R or pre-exported CSVs) | Separation, YAC, pressure rates |
| College data | cfbfastR (via pre-exported CSVs) | QB/WR college connection history |
| Roster/contracts | OverTheCap scraper | Free, no official API |
| Market values | FantasyPros scraper (Playwright) | No public API |
| Hosting | Railway | Zero-DevOps, managed Postgres available |
| CI/CD | GitHub Actions | Deploy on push to main |
| Secrets | Railway environment variables | Never hardcode credentials |

---

## Repository Structure

```
fantasy-football-ai/
├── PROJECT_CONTEXT.md          # This file
├── .env.example                # Template for required env vars
├── .env                        # Never commit — gitignored
├── .gitignore
├── pyproject.toml              # uv project config
├── alembic/                    # DB migrations
│   ├── env.py
│   └── versions/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Settings from env vars
│   ├── database.py             # SQLAlchemy async engine
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── player.py
│   │   ├── team_system.py
│   │   ├── dependency.py
│   │   ├── draft_state.py
│   │   └── season_roster.py
│   ├── agents/                 # All AI agent code
│   │   ├── base_agent.py       # Shared agent utilities
│   │   ├── team_systems.py
│   │   ├── roster_changes.py
│   │   ├── player_profiles.py
│   │   ├── injury_risk.py
│   │   ├── schedule.py
│   │   ├── beat_reporter.py
│   │   ├── roster_monitor.py
│   │   ├── opponent_analyzer.py
│   │   ├── trade_value.py
│   │   └── waiver_wire.py
│   ├── engines/                # Non-agent processing logic
│   │   ├── live_draft.py       # Live draft decision engine
│   │   ├── trade_proposal.py   # Trade suggestion engine
│   │   ├── trade_analyzer.py   # Trade analysis engine
│   │   └── lineup_optimizer.py
│   ├── integrations/
│   │   ├── yahoo_api.py        # Official Yahoo Fantasy API
│   │   ├── yahoo_playwright.py # Playwright draft room bridge
│   │   ├── nfl_data.py         # nfl_data_py wrapper
│   │   ├── overthecap.py       # OverTheCap scraper
│   │   ├── fantasypros.py      # FantasyPros market value scraper
│   │   └── beat_reporter_feeds.py  # RSS/news feeds
│   ├── routers/                # FastAPI route handlers
│   │   ├── draft.py
│   │   ├── players.py
│   │   ├── trades.py
│   │   ├── lineup.py
│   │   └── pipeline.py
│   └── websocket/
│       └── manager.py          # WebSocket connection manager
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── store/              # Zustand stores
│   │   ├── components/
│   │   │   ├── draft/          # Draft room components
│   │   │   ├── players/        # Player card components
│   │   │   ├── trades/         # Trade analyzer UI
│   │   │   └── lineup/         # Lineup optimizer UI
│   │   └── pages/
│   └── vite.config.js
└── scripts/
    ├── run_predraft_pipeline.py   # Runs all 6 research agents
    ├── refresh_market_values.py   # Updates FantasyPros data
    └── seed_nfl_data.py           # Initial data ingestion
```

---

## Environment Variables Required

Create `.env.example` with these keys. **Ask the user for values** before running any code that requires them.

```
# Anthropic
ANTHROPIC_API_KEY=

# Yahoo Fantasy API (OAuth 2.0)
YAHOO_CLIENT_ID=
YAHOO_CLIENT_SECRET=
YAHOO_REDIRECT_URI=http://localhost:8000/auth/yahoo/callback
YAHOO_LEAGUE_ID=
YAHOO_REFRESH_TOKEN=    # Populated after first OAuth flow

# Database
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/fantasy_football

# App
SECRET_KEY=             # Random string for session signing
ENVIRONMENT=development # or production

# Optional: RapidAPI key if using any paid NFL data endpoints
RAPIDAPI_KEY=
```

---

## Phase 1: Pre-Draft Pipeline

### Overview

Six research agents run sequentially (Team Systems first, others can parallelize after). Each writes structured output to the PostgreSQL draft bible. The pipeline should be runnable via `python scripts/run_predraft_pipeline.py` and re-runnable at any time to refresh data.

**Run schedule:**
- Once in early June after offseason programs
- Once in late July when training camp opens
- Weekly through August
- Daily the week of the draft
- Morning of the draft (final freshness pass)

---

### Agent 1: Team Systems Agent

**Purpose:** Grade every NFL team as an offensive system. Runs first. Output is inherited by all other agents.

**Inputs:**
- nfl_data_py: play-by-play data for OC scheme tendencies, personnel groupings, pressure rates
- Pro Football Focus grades (scrape free tier or use nfl_data_py proxies): O-line pass protection and run blocking
- Pro Football Reference: historical OC tendencies at previous stops
- OverTheCap: current depth chart and roster

**Output per team (writes to `team_systems` table):**

```json
{
  "team_abbr": "LAC",
  "pass_protection_grade": "B+",
  "run_blocking_grade": "B",
  "qb_name": "Justin Herbert",
  "qb_tier": "solid",
  "qb_experience_years": 5,
  "qb_pressure_performance": "above_avg",
  "qb_cpoe": 2.4,
  "qb_air_yards_per_attempt": 8.2,
  "qb_downfield_aggressiveness": "moderate",
  "rookie_qb_flag": false,
  "compound_risk_flag": false,
  "oc_name": "Greg Roman",
  "oc_scheme": "balanced",
  "oc_run_pass_split_tendency": 0.48,
  "personnel_tendency": "11",
  "red_zone_philosophy": "wr1",
  "system_ceiling": "high",
  "system_grade": "A-",
  "notes": "Herbert entering prime years with stable OC. Strong pass protection enables full route trees."
}
```

**Key logic:**
- Split O-line into pass protection and run blocking separately — they do not always correlate
- `rookie_qb_flag`: true for any first-year starter
- `compound_risk_flag`: true when both `rookie_qb_flag` is true AND pass protection grade is C or below — this flag cascades as a severe penalty to all skill position players on that roster
- Pull OC's tendencies from their last 3 coaching stops, not just current season

---

### Agent 2: Roster Changes Agent

**Purpose:** Track every meaningful offseason transaction and reason through the downstream consequences on player values. This is the most intellectually complex agent — it performs chain-of-reasoning analysis, not just data collection.

**The McConkey/Allen example (canonical test case):**
```
Event: Keenan Allen signs with LAC
→ Agent checks Allen's historical role: slot receiver, high-volume possession target
→ Agent checks Herbert/Allen shared history: 2019-2022, Allen averaged 27% target share
→ Agent checks Ladd McConkey's role: slot receiver, same alignment as Allen
→ Conclusion: Direct role overlap. McConkey ceiling now capped.
→ Output: DISPLACED flag on McConkey pointing at Allen
→ Output: CONTINGENT/BENEFICIARY flag on McConkey — value rises significantly if Allen misses time
```

**Inputs:**
- OverTheCap: all transactions (signings, cuts, trades) with contract AAV
- nfl_data_py: historical target share and snap count data for displacement modeling
- Pro Football Reference: OC history at previous stops for coaching change analysis
- Beat reporter RSS feeds: unofficial depth chart signals

**Dependency flag types:**

```python
class DependencyFlagType(Enum):
    DISPLACED     = "displaced"      # Role directly overlapped by new arrival
    CONTINGENT    = "contingent"     # Value tied to another player's health
    BENEFICIARY   = "beneficiary"    # Value rises if trigger player is absent
    COMMITTEE     = "committee"      # RB sharing backfield, snap share unclear
    SCHEME_FIT    = "scheme_fit"     # Profile mismatches new OC tendency
    COLLEGE_TRUST = "college_trust"  # QB/WR college connection on same NFL roster
```

**QB Trust Model:**
- Maintains a trust score (0-100) for every QB/receiver pairing
- Sources: NFL shared history (primary), college shared history (secondary, ~70% weight)
- College connection: pulled from cfbfastR — years overlapping at same program, target share during shared seasons
- College trust flag is especially important for rookie QBs in Year 1 — they default to college targets under pressure
- Flag format: `COLLEGE_TRUST — QB and WR overlapped at [school] for [N] seasons. Signal: moderate positive for target floor especially in Year 1.`

**Backfield committee detection logic:**
- Two RBs with overlapping usage profiles on same roster → COMMITTEE flag
- Pass-catching specialist added alongside workhorse → mild flag only
- True committee (two similar-profile backs) → strong flag, high variance warning

**Coaching staff changes:**
- New OC: pull scheme tendencies from previous 3 stops, identify which player types benefit/suffer, flag players who thrived under old system but mismatch new scheme
- O-line coach change: update team system grade
- QB coach hire: note if coach has development reputation (mild positive for rookie QBs)

**Output per dependency (writes to `player_dependencies` table):**

```json
{
  "player_id": "uuid",
  "flag_type": "displaced",
  "trigger_player_id": "uuid",
  "trigger_player_name": "Keenan Allen",
  "trigger_condition": "active_and_healthy",
  "effect_on_value": "negative",
  "value_impact_pct": -0.35,
  "confidence": "high",
  "reasoning": "Allen commands 27% historical target share with Herbert. Direct slot role overlap with McConkey.",
  "season_year": 2025
}
```

---

### Agent 3: Player Profiles Agent

**Purpose:** Build a complete individual profile for every draftable player. Inherits team system context. Produces the core valuation fields used throughout the system.

**Position classifications:**

WR roles:
- `wr1_alpha` — 25%+ target share, full route tree
- `slot_specialist` — high volume, PPR-friendly, volume-dependent
- `deep_threat` — lower share, high air yards, boom-or-bust
- `possession_wr2` — consistent floor, low ceiling
- `gadget` — unpredictable usage, high variance flag

RB roles:
- `workhorse` — 15+ carries + pass-catching, three-down back
- `early_down_thumper` — goal line dependent, TD-volatile
- `pass_catching_specialist` — PPR value, committee-vulnerable
- `committee_back` — snap share unclear, flag always applied

**Key metrics to collect (nfl_data_py + nflfastR):**
- Target share % (per season and per game)
- Targets per route run (efficiency-adjusted)
- Air yards share
- Snap percentage and route participation rate
- CPOE (completion percentage over expectation) — for QBs
- Yards after contact (RBs)
- Separation score at snap and at catch point
- Contested catch rate
- Broken tackle rate (RBs)
- Yards after catch

**Clean season baseline:**
- Strip injury-shortened seasons (fewer than 10 games) and anomalous situations (backup QB for 4+ games)
- Document which seasons were excluded and why in `anomalous_seasons_excluded` array
- Project baseline from clean seasons only

**Age/career curve:**
- RBs: peak 24-26, decline flag after 28
- WRs: peak 24-29, acclimation note for Year 1-2
- TEs: peak 26-29 (slow development position)
- Contract year flag: final year of contract → mild upward bias, note it doesn't persist

**Breakout candidate detection:**
- Year 2 or Year 3 spike window (receivers)
- Clear path to increased target share from depth chart departure above them
- New OC whose scheme historically elevates this player type
- Efficiency metrics already above production (talent not yet rewarded)

**Output per player (writes to `players` table — profile subsection):**

```json
{
  "player_id": "uuid",
  "role_classification": "wr1_alpha",
  "target_share_3yr_avg": 0.26,
  "target_share_last_season": 0.29,
  "targets_per_route_run": 0.31,
  "air_yards_share": 0.34,
  "snap_percentage": 0.88,
  "separation_score": "above_avg",
  "yards_after_catch_score": "elite",
  "contested_catch_rate": 0.61,
  "efficiency_signal": "elite",
  "age_curve_position": "ascending",
  "career_trajectory": "ascending",
  "clean_season_baseline": {
    "receptions": 105,
    "yards": 1320,
    "touchdowns": 8,
    "ppr_points": 218
  },
  "anomalous_seasons_excluded": [],
  "breakout_flag": false,
  "breakout_reasoning": null,
  "positional_scarcity_tier": "scarce"
}
```

---

### Agent 4: Injury Risk Agent

**Purpose:** Build a risk-adjusted profile for every player. Not predicting injuries — pricing in variance so auction bid ceilings reflect true risk.

**Injury categories:**

| Category | Examples | Recurrence Risk | Notes |
|----------|----------|----------------|-------|
| `soft_tissue` | Hamstring, groin, calf, hip flexor | HIGH | Most predictive of future issues. Two same-area events in 3 years = pattern flag |
| `ligament` | ACL, MCL, high ankle sprain | MODERATE | ACL: low re-tear risk on same knee, elevated contralateral risk. High ankle: underrated lingering effect |
| `fracture_traumatic` | Collarbone, fibula, hand | LOW | Heals cleanly. Flag for recency only, not long-term risk |
| `fracture_stress` | Stress fractures | MODERATE | Indicates bone density/biomechanical issue. Recurs |
| `concussion` | Any documented concussion | SPECIAL | Count total career concussions. 2+ = compounding modifier. Recency flag if within 12 months |
| `chronic` | Turf toe, plantar fasciitis, back issues, arthritis | ONGOING | Does not reset between seasons. Particularly severe for skill positions |

**Pattern flags:**
```python
RECURRING_SOFT_TISSUE  # 2+ soft tissue injuries to same area within 3 years
CONCUSSION_HISTORY     # 2+ documented concussions
HIGH_MILEAGE           # RB with 600+ career carries
POST_ACL               # Within 18 months of ACL return
CHRONIC_CONDITION      # Any chronic issue present
WORKLOAD_CLIFF         # Coming off 300+ carry season (RBs)
```

**Age risk multiplier:**
- Under 26: 1.0x (baseline)
- 26-28: 1.1x
- 29-30: 1.25x
- 31+: 1.5x

**Risk-adjusted value modifier** (applied to baseline value):
- Low risk: -0.00 to -0.05
- Moderate risk: -0.10 to -0.20
- High risk: -0.20 to -0.35
- Volatile: -0.35 or worse

**Output per player (writes to `player_injury_profiles` table):**

```json
{
  "player_id": "uuid",
  "overall_risk_level": "moderate",
  "risk_adjusted_value_modifier": -0.15,
  "injury_log": [
    {
      "year": 2024,
      "injury_type": "hamstring",
      "category": "soft_tissue",
      "games_missed": 4,
      "early_return": true,
      "performance_impact": "mild"
    }
  ],
  "pattern_flags": ["RECURRING_SOFT_TISSUE"],
  "chronic_conditions": [],
  "career_carry_count": 847,
  "workload_cliff_flag": false,
  "high_mileage_flag": true,
  "post_acl_flag": false,
  "concussion_count": 0,
  "recovery_assessment": "probable",
  "age_risk_multiplier": 1.25,
  "risk_notes": "Hamstring history with early return on most recent — elevated recurrence risk. High mileage RB entering age-29 season."
}
```

---

### Agent 5: Schedule Agent

**Purpose:** Grade each player's schedule across three distinct windows. This is more data-retrieval than reasoning — build current-year defensive grades by adjusting last year's performance for offseason changes.

**Defensive grade construction:**
- Start from last year's defensive performance by position allowed
- Apply adjustments for: FA losses/additions (weighted by position relevance), draft picks (by projected role), coordinator changes (scheme impact)
- Produce separate grades for: vs WR1, vs slot WR, vs TE, vs RB rushing, vs RB receiving

**Three windows (all stored separately):**

1. **Early window (weeks 1-6):** Determines fast start. Weighted more heavily for immediate contributors.
2. **Full season:** Standard quality-of-schedule.
3. **Playoff window (weeks 14-17):** Most underrated metric. Stored as first-class field, not buried in notes.

**Additional factors:**
- Bye week (week number stored)
- Bye conflict detection: flag if player's bye matches other players in user's projected roster
- Weather risk: outdoor stadiums in cold-weather cities, November-December modifier on passing games (BUF, GB, CHI, NE, CLE, PIT)
- Divisional game weeks: mild suppression flag, teams play each division opponent twice
- Vegas implied team totals: where available, most predictive weekly input

**Output per player (writes to `player_schedules` table):**

```json
{
  "player_id": "uuid",
  "season_year": 2025,
  "bye_week": 6,
  "early_window_grade": "favorable",
  "early_window_favorable_weeks": [1, 3, 5],
  "early_window_tough_weeks": [4],
  "early_window_summary": "Three favorable matchups in first five weeks.",
  "full_season_grade": "neutral",
  "playoff_window_grade": "favorable",
  "playoff_weeks": [14, 15, 16, 17],
  "playoff_matchups": ["vs ARI", "vs SEA", "at LV", "vs DAL"],
  "playoff_summary": "Three bottom-10 pass defenses in playoff window.",
  "weather_risk": "low",
  "weather_affected_weeks": [],
  "divisional_game_weeks": [4, 10, 14, 17],
  "schedule_score": 7.2,
  "schedule_notes": "Excellent playoff schedule makes this a premium keeper asset."
}
```

---

### Agent 6: Beat Reporter Agent

**Purpose:** The freshness layer. Aggregates pre-draft news from team beat reporters to catch last-mile signals the other agents may not have — depth chart changes, injury reports, practice limitations, coaching comments on usage.

**Data sources:**
- Team beat reporter RSS feeds (ESPN, NFL.com, The Athletic team pages)
- Official NFL injury report PDFs (released Wednesday-Friday of each week in season, available pre-season)
- Rotowire transaction feed
- Twitter/X API (beat reporter accounts) — if API access available, otherwise scrape

**Signal types to flag:**
- Player reported limited in practice
- Coach evasive about player's status
- Beat reporter noting player favoring a body part
- Depth chart change (official or reported)
- "Camp standout" signals — emerging role players
- Any transaction not yet reflected in OverTheCap

**Output:** Updates the `notes` field and `last_updated` timestamp on player records. Also writes to a `beat_reporter_signals` table with timestamp, source, signal type, and raw text.

This agent runs on a daily schedule the week of the draft and feeds into the Injury Risk agent's `recovery_assessment` field for any recently injured players.

---

## The Draft Bible Schema

The draft bible is the PostgreSQL database populated by the six research agents. Every player gets one master record that links to subsection tables.

### Master player record (`players` table)

```sql
CREATE TABLE players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    yahoo_player_id VARCHAR(50) UNIQUE,
    name VARCHAR(100) NOT NULL,
    team_abbr VARCHAR(5),
    position VARCHAR(5),  -- QB, RB, WR, TE, K, DEF
    age INTEGER,
    contract_year BOOLEAN DEFAULT false,
    
    -- Top-level valuation (computed from subsections)
    tier INTEGER,                    -- 1-5
    baseline_value DECIMAL(5,2),     -- Expected auction cost
    ceiling_value DECIMAL(5,2),      -- Realistic upside price
    floor_value DECIMAL(5,2),        -- Realistic downside price
    risk_adjusted_value DECIMAL(5,2), -- baseline * (1 + risk_modifier) — USE THIS for bid ceiling
    
    -- Market value (what the room expects to pay)
    market_value DECIMAL(5,2),
    market_value_fantasypros DECIMAL(5,2),
    market_value_sleeper DECIMAL(5,2),
    market_value_underdog DECIMAL(5,2),
    market_value_confidence VARCHAR(20), -- high/medium/low
    market_value_updated_at TIMESTAMP,
    
    -- Derived fields
    value_gap DECIMAL(5,2),          -- system_value minus market_value (positive = undervalued)
    value_gap_signal VARCHAR(30),    -- market_overvalues / market_undervalues / aligned
    
    -- Bid strategy
    recommended_bid_ceiling DECIMAL(5,2), -- What the live agent uses
    let_go_threshold DECIMAL(5,2),        -- Price at which to definitely stop bidding
    elite_anchor_weight DECIMAL(3,2),     -- 0.0-1.0, higher for tier 1 players
    
    -- Situation summary
    situation_score VARCHAR(20),     -- strong / moderate / weak / volatile
    positional_scarcity_modifier DECIMAL(3,2),
    breakout_flag BOOLEAN DEFAULT false,
    
    -- Human-readable summary (2-3 sentences, used during live draft)
    notes TEXT,
    
    -- Pipeline metadata
    last_pipeline_run TIMESTAMP,
    data_confidence VARCHAR(20),     -- high / medium / low
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Team systems table (`team_systems`)
See Agent 1 output schema above. One record per NFL team per season.

### Player profile table (`player_profiles`)
See Agent 3 output schema above. One record per player per season.

### Injury profiles table (`player_injury_profiles`)
See Agent 4 output schema above. One record per player, updated across seasons.

### Schedule table (`player_schedules`)
See Agent 5 output schema above. One record per player per season.

### Dependencies table (`player_dependencies`)
See Agent 2 output schema above. Multiple records per player (one per flag).

### Beat reporter signals table (`beat_reporter_signals`)
```sql
CREATE TABLE beat_reporter_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID REFERENCES players(id),
    signal_type VARCHAR(50),         -- practice_limited / depth_chart_change / injury_flag / camp_standout
    source VARCHAR(100),
    raw_text TEXT,
    confidence VARCHAR(20),
    flagged_at TIMESTAMP DEFAULT NOW()
);
```

---

## The Two-Value System

Every player carries two distinct value fields that serve different strategic purposes:

**Market value** — what the room expects to pay. Sourced from FantasyPros consensus, Sleeper implied ADP, Underdog implied ADP. Not about what the player is worth — about predicting room behavior. The anchor that shapes every manager's reference point.

**System value** — what the research pipeline says the player is actually worth. This is the number we believe in.

The gap between them is where the edge lives.

### Bid ceiling calculation

For tier 1 players (elite scarcity):
```
bid_ceiling = (system_value * (1 - elite_anchor_weight)) + (market_value * elite_anchor_weight)
bid_ceiling = bid_ceiling * positional_scarcity_modifier
bid_ceiling = bid_ceiling * (1 + risk_adjusted_modifier)
```

For tier 2-3 players (moderate market weight):
```
bid_ceiling = (system_value * 0.85) + (market_value * 0.15)
bid_ceiling = bid_ceiling * (1 + risk_adjusted_modifier)
```

For tier 4-5 players (system value dominant):
```
bid_ceiling = system_value * (1 + risk_adjusted_modifier)
```

`elite_anchor_weight` defaults: Tier 1 = 0.80, Tier 2 = 0.40, Tier 3 = 0.15, Tier 4-5 = 0.00

`positional_scarcity_modifier`: Tier 1 RB = 1.35, Tier 1 WR = 1.20, Tier 1 QB = 1.10, Tier 2+ = 1.00

### Nomination strategy logic

When it's the user's turn to nominate, the live draft agent should recommend players where:
- Market value is HIGH but system value is LOW (opponent overpays, drains their budget)
- User does NOT want the player
- Logic: nominating CMC when you don't want CMC forces the room to spend $65-70, depleting budgets available for players you do want

---

## Phase 2: Live Draft Agent

### Yahoo Integration

**Official Yahoo Fantasy API** (use for all non-live-draft data):
- OAuth 2.0 authentication
- League data: teams, rosters, scoring settings
- Player universe: all draftable players with Yahoo player IDs
- Post-draft results sync

**⚠️ ASK USER:** Yahoo Developer account setup and OAuth app registration requires human action. Stop and ask the user to:
1. Create a Yahoo Developer account at developer.yahoo.com
2. Register a new app and select Fantasy Sports scope
3. Provide the client ID and client secret for `.env`

**Playwright Draft Room Bridge** (for live draft control):

Yahoo's draft room is a JavaScript web application communicating via WebSocket. The Playwright bridge:
1. Authenticates with Yahoo using stored OAuth tokens
2. Navigates to the draft room URL
3. Intercepts WebSocket frames for real-time draft events
4. Uses MutationObserver as fallback for DOM-based detection
5. Exposes actions: nominate player, place bid, pass nomination

```python
# Architecture — NO POLLING anywhere in this chain
# Yahoo WS frames → Playwright interception → FastAPI WebSocket → React UI
# User action → React → FastAPI WebSocket → Playwright page.evaluate() → Yahoo

class YahooPlaywrightBridge:
    
    async def connect(self, draft_room_url: str):
        # 1. Launch Playwright browser (headless=False for debugging, headless=True for production)
        # 2. Navigate to draft room
        # 3. Set up WebSocket interception (primary)
        # 4. Inject MutationObserver (secondary fallback)
        # 5. Start health check loop (ping every 10s, auto-reconnect on failure)
        pass
    
    async def intercept_websocket(self, page):
        # Listen for websocket connections
        # Parse frame payload for event types:
        #   - nomination: player nominated, clock started
        #   - bid_update: current bid price changed
        #   - draft_pick: pick confirmed, player off board
        #   - clock_warning: X seconds remaining
        # Emit parsed events to FastAPI WebSocket manager
        pass
    
    async def nominate_player(self, yahoo_player_id: str, opening_bid: int):
        # Use page.evaluate() or page.click() to fire nomination
        # Confirm action succeeded, emit confirmation event
        pass
    
    async def place_bid(self, amount: int):
        # Same pattern — evaluate or click
        # Handle timeout gracefully
        pass
    
    async def on_bridge_failure(self):
        # Emit MANUAL_ACTION_REQUIRED event to UI with:
        #   - What action was being attempted
        #   - Exact amount/player
        #   - Urgency level
        # Never crash silently — always alert the user
        pass
```

**Lag elimination requirements:**
- Zero polling anywhere in the event chain
- WebSocket interception fires on frame receipt, not on a timer
- MutationObserver fires on DOM mutation, not on a timer
- FastAPI → React uses WebSocket push, not HTTP polling
- Target round-trip latency: under 100ms for draft event detection

### Live Draft Decision Engine

When a player is nominated:
1. Pull player record from draft bible (single DB query by yahoo_player_id)
2. Check dependency flags against already-drafted players (e.g. if Allen already drafted, activate McConkey's DISPLACED flag)
3. Calculate adjusted bid ceiling given current draft state
4. Check opponent threat scores to determine block value
5. Compare bid ceiling to remaining budget constraints
6. Output recommendation

**Recommendation structure:**
```json
{
  "player_name": "Ladd McConkey",
  "action": "pass",          // buy / bid_to / block / pass
  "bid_ceiling": 14,
  "block_value": 22,
  "budget_allows_block": false,
  "active_flags": ["DISPLACED: Allen already drafted — target share capped"],
  "notes": "Ceiling dropped from $28 to $14 with Allen off the board. Not worth blocking price.",
  "system_value": 28,
  "market_value": 31,
  "adjusted_system_value": 14
}
```

### Opponent Modeling

Track every opponent's roster as it builds. Maintain per-opponent:
```json
{
  "team_name": "Opponent Name",
  "roster": [...],
  "budget_remaining": 45,
  "budget_spent": 155,
  "positional_scores": {
    "QB": 0.2,
    "RB": 0.9,
    "WR": 0.4,
    "TE": 0.3
  },
  "threat_score": 78,      // 0-100, how dangerous this roster is
  "combo_flags": [
    "Elite RB stack: CMC + Taylor — historically dominant"
  ],
  "apparent_strategy": "zero_rb",   // zero_rb / hero_rb / balanced / positional_run
  "likely_targets": ["Travis Kelce", "Justin Jefferson"]
}
```

**Block flag logic:**
- Calculate block_value = what the player is worth to that specific opponent given their roster
- Calculate personal_value = what the player is worth to you
- Flag block when: block_value > personal_value AND budget allows
- Budget check: never recommend a block that would drop remaining budget below minimum viable roster completion threshold
- If opponent budget is low (under $15 remaining), suppress block flags — they can't afford dangerous players anyway

**Combo threat detection:** Named patterns that trigger automatic flags:
- Two tier-1 RBs on same roster: "Elite RB stack — historically dominant"
- Elite RB + elite TE: "Positional scarcity lock — dangerous floor"
- QB + WR1 from same team (stack): "Stack bonus upside — volatile but ceiling is high"

---

## Phase 3: In-Season Management

### Season Roster Store

After the draft completes, the draft bible records for drafted players are promoted to the season roster store with additional fields:

```sql
CREATE TABLE season_roster (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id UUID REFERENCES players(id),
    yahoo_team_id VARCHAR(50),        -- Which team owns them
    acquisition_price DECIMAL(5,2),   -- What was paid at auction
    acquisition_week INTEGER DEFAULT 0,
    
    -- Weekly tracking (JSON array, one entry per week)
    weekly_stats JSONB DEFAULT '[]',
    weekly_snap_counts JSONB DEFAULT '[]',
    weekly_target_share JSONB DEFAULT '[]',
    
    -- Current season valuations (updated weekly by Roster Monitor agent)
    current_trade_value DECIMAL(5,2),
    value_trend VARCHAR(20),          -- rising / falling / stable
    
    -- Flags updated throughout season
    sell_high_flag BOOLEAN DEFAULT false,
    buy_low_flag BOOLEAN DEFAULT false,
    injury_concern_flag BOOLEAN DEFAULT false,
    
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### In-Season Agent: Roster Monitor

Runs weekly (Wednesday, after Monday Night Football stats finalize).

**Tasks:**
- Pull weekly stats from Yahoo API for all rostered players
- Update snap count and target share trends in season roster store
- Detect usage changes (snap count dropping 2+ consecutive weeks = flag)
- Detect injury report practice participation (Limited/DNP on Wednesday)
- Update `current_trade_value` for all players
- Set `sell_high_flag` if player's recent performance exceeds underlying efficiency
- Set `buy_low_flag` if player's recent slump appears matchup-driven

---

### In-Season Agent: Opponent Analyzer

Builds and maintains profiles on every other manager in the league throughout the season.

**Per-opponent profile:**
- Current roster with acquisition prices and weekly scores
- Positional strength scores (updated weekly)
- Roster vulnerabilities (bye conflicts, injury exposure, playoff schedule issues)
- Apparent management style: reactive (overvalues recent performance), analytical, name-brand biased
- Historical trade behavior: what they've accepted and rejected this season
- Current record and playoff positioning (drives urgency)

**Management style detection signals:**
- Reactive: frequently starts players coming off big games regardless of matchup
- Name-brand biased: holds onto big-name players well past their value
- Analytical: trade offers they make show awareness of schedule and usage
- Urgency-driven: 2-3 game losing streak = willing to overpay to shake things up

---

### In-Season Agent: Trade Value Agent

Runs weekly. Calculates current trade value for every player in the league (not just your roster).

**Buy-low signals:**
- Recent slump confirmed as matchup-driven (favorable matchups coming)
- Snap count temporarily reduced due to non-recurring game script
- Player returning from injury (conservative snaps, value will recover)
- Recency bias suppressing perceived value below true projection

**Sell-high signals:**
- TD production on low target share (touchdowns regress toward targets)
- Snap count quietly declining 2+ weeks
- Upcoming brutal schedule that opponent hasn't noticed
- Player overperforming efficiency metrics (can't sustain)

**Valuation asymmetry detection:**
For each opponent: compare your valuation of their players vs what they likely value them at (using their apparent management style). The gap is the trade opportunity.

---

### Trade Proposal Engine

Generates proactive trade suggestions by cross-referencing:
- Your roster surplus positions
- Each opponent's roster weakness (from Opponent Analyzer)
- Trade Value Agent's asymmetry flags
- Opponent's apparent management style (calibrates framing and player selection)
- Acceptance probability model

**Acceptance probability model inputs:**
- Does it address their positional need? (highest weight)
- Does the deal look fair at market value? (managers anchor on perceived fairness)
- Does their management style suggest they'll value what you're offering?
- Their current record and urgency level
- Their remaining playoff schedule (creates urgency if bad)

Output: ranked list of trade proposals with acceptance probability and reasoning for each.

---

### Trade Analyzer

On-demand tool. User submits a trade (either received from opponent or planning to propose).

**Analysis components:**

1. **Fairness analysis** — current system value of both sides, accounting for your roster context (is this position of surplus or need?)

2. **Situation-adjusted value** — timing flags:
   - `SELL_HIGH`: player being offered has inflated perceived value (recent TD spike on low targets)
   - `BUY_LOW_OPPORTUNITY`: player being given up has depressed perceived value (matchup slump)

3. **Acceptance probability** — pulls opponent profile, estimates likelihood they accept as-is

4. **Counter proposal suggestions** — if deal is unfavorable as submitted, find nearest adjustment that flips it to favorable while keeping acceptance probability reasonable

**Output format:**
```json
{
  "verdict": "slightly_unfavorable",
  "fairness_gap": -12,
  "fairness_direction": "giving_more_than_receiving",
  "roster_fit_adjustment": "+4 (receiving at position of need)",
  "timing_flags": [
    "SELL_HIGH on [received player] — 3 TDs in 2 weeks on sub-15% target share",
    "BUY_LOW opportunity on [given player] — slump is matchup-driven, 3 favorable weeks ahead"
  ],
  "acceptance_probability": 0.65,
  "acceptance_reasoning": "Opponent is 3-4, thin at your surplus position, motivated",
  "counter_proposals": [
    {
      "description": "Swap [Player B] for [Player D] from your roster",
      "new_verdict": "favorable",
      "acceptance_probability": 0.58,
      "reasoning": "Player D addresses their WR2 gap directly, costs you bench depth not a starter"
    }
  ]
}
```

---

### Lineup Optimizer

Runs every week (Thursday, after injury reports finalize and lines are set).

**Inputs per player:**
- Matchup grade (from schedule agent framework applied to this week's specific opponent)
- Vegas implied team total for their team (most predictive single input)
- Practice participation (Wednesday/Thursday/Friday reports)
- Recent snap count and usage trend
- Weather (outdoor stadiums, wind speed > 15mph suppresses passing)
- Home/away split if significant for this player
- Opponent analyzer: does the opponent this week have a revenge game, extra motivation?

**Output:** Starting lineup recommendation with confidence level (High/Medium/Low) and key reasoning factors for each decision. Explain the reasoning — don't just output a lineup. The user should be able to override with full context.

---

### Waiver Wire Agent

Runs weekly (Tuesday night/Wednesday morning, immediately after waiver priority processes).

**Identification criteria:**
- Snap count spike in most recent game (new role emerging)
- Depth chart promotion due to injury above them
- Usage pattern change (target share jump, carry spike)
- Beat reporter signal about increased role
- Schedule matchup favorable for next 2-3 weeks

Output: Ranked pickup recommendations with projected value window (how many weeks this is relevant) and confidence.

---

## Build Stages

Work through these stages in order. Complete each stage fully and verify with the user before proceeding to the next. Ask the user when external setup or credentials are needed.

---

### Stage 1: Project Foundation

**Goal:** Working repo, database, and environment. No agents yet.

Tasks:
1. Initialize GitHub repo with the directory structure defined above
2. Set up `pyproject.toml` with uv, all dependencies listed
3. Create `.env.example` with all required env var keys and descriptions
4. **ASK USER** for `ANTHROPIC_API_KEY` and any other keys they have available
5. Set up PostgreSQL locally for development (or ask user to provision Railway Postgres)
6. Implement `backend/database.py` — async SQLAlchemy engine, session factory
7. Implement `backend/config.py` — pydantic settings model reading from `.env`
8. Write all SQLAlchemy models in `backend/models/`
9. Set up Alembic, write initial migration, run it
10. Verify all tables created correctly
11. Write basic FastAPI app in `backend/main.py` with health check endpoint

**Verification:** `GET /health` returns 200. All DB tables exist. Environment loads without errors.

---

### Stage 2: NFL Data Ingestion Layer

**Goal:** Raw NFL data accessible in Python. Foundation all agents read from.

Tasks:
1. Implement `backend/integrations/nfl_data.py` — wrapper around nfl_data_py
   - Functions: `get_pbp_data(season)`, `get_player_stats(season)`, `get_snap_counts(season)`, `get_target_share(season)`, `get_adp_data()`
2. Implement `backend/integrations/overthecap.py` — scraper for roster and transaction data
   - Functions: `get_roster(team_abbr)`, `get_transactions(year)`, `get_contracts()`
3. Implement `backend/integrations/fantasypros.py` — market value scraper using Playwright
   - **ASK USER** if they want to run this now or defer until closer to draft
   - Functions: `get_auction_values(format)`, `get_adp(format)`
4. Write `scripts/seed_nfl_data.py` — pulls and caches last 3 seasons of data to local DB tables
5. Run seed script, verify data looks correct for a sample of known players

**Verification:** Can query target share for a specific player for a specific season. Data matches known stats.

---

### Stage 3: Team Systems Agent

**Goal:** All 32 NFL teams have system grade records in the database.

Tasks:
1. Implement `backend/agents/base_agent.py` — shared utilities:
   - Anthropic client initialization
   - Tool definition helpers
   - Structured output parsing
   - Error handling and retry logic
   - Logging
2. Implement `backend/agents/team_systems.py`
   - Define tools: `get_oline_grades`, `get_qb_metrics`, `get_oc_history`, `get_personnel_tendencies`
   - Agent loop: for each of 32 NFL teams, run analysis and write to `team_systems` table
   - Apply `rookie_qb_flag` and `compound_risk_flag` logic
3. Add pipeline endpoint `POST /pipeline/run-team-systems` for manual triggering
4. Run agent for all 32 teams
5. Spot-check 5-6 teams against known situations

**Verification:** All 32 teams have records. Rookie QB teams are correctly flagged. System grades look reasonable.

---

### Stage 4: Roster Changes Agent

**Goal:** All meaningful offseason transactions analyzed with dependency flags written to DB.

Tasks:
1. Implement `backend/agents/roster_changes.py`
   - Target share displacement model (the McConkey/Allen logic)
   - QB trust model (NFL history + college connection)
   - Backfield committee detection
   - Coaching change impact analysis
   - College connection lookup (cfbfastR data)
2. Implement `backend/integrations/beat_reporter_feeds.py` — RSS feed parser for initial transaction signals
3. Write all dependency flags to `player_dependencies` table
4. **Canonical test:** Verify the McConkey/Allen scenario produces correct DISPLACED and CONTINGENT flags
5. Run for all 32 teams
6. Review dependency flags with user — do they match known situations?

**Verification:** McConkey has DISPLACED flag. At least one college trust flag exists for a real QB/WR pair. Backfield committee flags exist for known committee situations.

---

### Stage 5: Player Profiles Agent

**Goal:** Every draftable player has a complete profile record.

Tasks:
1. Implement `backend/agents/player_profiles.py`
   - Role classification logic
   - Clean season baseline calculation (strip anomalous seasons)
   - Efficiency metric aggregation from nflfastR data
   - Age/career curve assignment
   - Breakout candidate detection
   - Inherits team system grade from Stage 3
2. Generate profiles for all draftable players (top 200 ADP minimum)
3. Compute `situation_score` for each player (composite of system grade + role clarity + dependency flags)
4. Spot-check 10 players across positions — do situation scores and baselines make sense?

**Verification:** Top 200 players have complete profiles. Situation scores distribute reasonably (not everyone is "strong"). Clean season baselines look accurate for known players.

---

### Stage 6: Injury Risk Agent

**Goal:** Every player has a risk profile and risk-adjusted value modifier.

Tasks:
1. Implement `backend/agents/injury_risk.py`
   - Injury categorization logic
   - Pattern flag detection
   - Age risk multiplier application
   - `risk_adjusted_value_modifier` computation
2. Pull injury history from nfl_data_py and Pro Football Reference
3. Write all injury profiles to `player_injury_profiles`
4. Apply modifiers to player `risk_adjusted_value` field in `players` table
5. Spot-check known injury-prone players — do their risk levels look correct?

**Verification:** High-mileage RBs have appropriate risk flags. Known soft-tissue-prone players have RECURRING_SOFT_TISSUE flag. Risk modifiers are applied to `risk_adjusted_value` in players table.

---

### Stage 7: Schedule Agent

**Goal:** Every player has schedule grades across all three windows.

Tasks:
1. Implement `backend/agents/schedule_agent.py`
   - Current-year defensive grade construction (adjust last year's stats for offseason changes)
   - Position-specific grading (vs WR1, vs slot, vs TE, vs RB rushing, vs RB receiving)
   - Three-window analysis (early, full season, playoff)
   - Weather risk flagging
   - Bye week tracking
2. Pull current NFL schedule (nfl_data_py or ESPN API)
3. Write all schedule records to `player_schedules`
4. Verify playoff window grades exist as first-class fields

**Verification:** All players have schedule records. Playoff grades exist. A player on a team with favorable early schedule has `early_window_grade: favorable`. Weather risk flags applied to relevant teams.

---

### Stage 8: Beat Reporter Agent

**Goal:** Pre-draft news ingestion running, draft bible notes updated with latest signals.

Tasks:
1. Implement `backend/agents/beat_reporter.py`
   - RSS feed parsing for major beat reporters
   - Signal extraction and classification
   - Player name entity recognition to link signals to player records
2. Implement APScheduler job to run this agent daily
3. Write signals to `beat_reporter_signals` table
4. Update `notes` and `last_updated` on affected player records
5. Test with a known recent story — verify it gets ingested and linked correctly

**Verification:** Recent beat reporter stories appear in `beat_reporter_signals`. At least one player record `notes` field has been updated from a feed signal.

---

### Stage 9: Draft Bible Valuation Pass

**Goal:** Every player has complete valuation fields computed from all agent outputs.

Tasks:
1. Write `scripts/compute_valuations.py`:
   - Tier assignment (1-5) based on position and projected production
   - `baseline_value`, `ceiling_value`, `floor_value` from profile + system + injury data
   - `risk_adjusted_value` = baseline * (1 + risk_modifier)
   - `elite_anchor_weight` by tier
   - `positional_scarcity_modifier` by position and tier
   - `recommended_bid_ceiling` using the two-value system formula
   - `let_go_threshold` = recommended_bid_ceiling * 1.15
   - `value_gap` and `value_gap_signal` once market values are available
2. **ASK USER** to refresh FantasyPros market values (run `scripts/refresh_market_values.py`)
3. Compute all valuation fields and write to `players` table
4. Review tier distribution and bid ceilings with user for sanity check

**Verification:** Every player in top 200 has all valuation fields populated. Bid ceilings for known elite players look reasonable. Tier 1 players show `elite_anchor_weight` of 0.80.

---

### Stage 10: Yahoo API Integration

**Goal:** League data, rosters, and player universe pulling from Yahoo official API.

**⚠️ ASK USER — Required before this stage:**
1. Do you have a Yahoo Developer account? If not: go to developer.yahoo.com, create one, register a new app with Fantasy Sports scope, note the client ID and client secret
2. Provide `YAHOO_CLIENT_ID` and `YAHOO_CLIENT_SECRET` for `.env`
3. Provide `YAHOO_LEAGUE_ID` (found in your Yahoo league URL)

Tasks:
1. Implement `backend/integrations/yahoo_api.py`
   - OAuth 2.0 flow (authorization URL generation, token exchange, token refresh)
   - Endpoints: `get_league()`, `get_teams()`, `get_players()`, `get_draft_results()`, `get_rosters()`
2. Add auth route `GET /auth/yahoo` (redirect to Yahoo) and `GET /auth/yahoo/callback` (token exchange)
3. **ASK USER** to run the OAuth flow once — they'll need to click through browser to authorize
4. Store refresh token in `.env` as `YAHOO_REFRESH_TOKEN`
5. Match Yahoo player IDs to draft bible player records (write `yahoo_player_id` to `players` table)
6. Pull league settings (scoring format, roster slots, auction budget) and store

**Verification:** Can retrieve league team names. Player IDs matched to draft bible. Scoring settings stored correctly.

---

### Stage 11: Playwright Yahoo Draft Room Bridge

**Goal:** App can receive live draft events from Yahoo and send nominations/bids back.

**⚠️ ASK USER before starting:** What is the URL format for your Yahoo draft room? Ask them to navigate to last year's draft recap or this year's draft lobby and share the URL pattern.

Tasks:
1. Install Playwright: `playwright install chromium`
2. Implement `backend/integrations/yahoo_playwright.py`
   - `connect(draft_room_url)` — launch browser, navigate, authenticate
   - WebSocket frame interception (primary event source)
   - MutationObserver injection (fallback)
   - Event parsing: nomination, bid_update, draft_pick, clock_warning, clock_expired
   - Actions: `nominate_player()`, `place_bid()`, `pass_nomination()`
   - Health check loop with auto-reconnect
   - `on_bridge_failure()` alert emission
3. Implement `backend/websocket/manager.py` — manages WebSocket connections to React frontend
4. Wire: Yahoo events → Playwright bridge → WebSocket manager → React
5. Wire: React actions → FastAPI endpoint → Playwright bridge → Yahoo

**Testing approach:**
- **ASK USER** to set up a practice/mock draft on Yahoo for testing
- Run bridge against mock draft
- Verify nomination detection fires in under 100ms
- Test bid placement under time pressure
- Simulate bridge failure → verify manual action alert fires

**Verification:** Nominations detected instantly (no lag). Bids placed successfully. Bridge failure alert surfaces in UI.

---

### Stage 12: Live Draft Agent

**Goal:** Agent queries draft bible and produces real-time recommendations during auction.

Tasks:
1. Implement `backend/engines/live_draft.py`
   - Draft state tracker (who's been nominated, prices, who owns what)
   - Dependency flag activation (check already-drafted players against each nominee's flags)
   - Bid ceiling calculation with live state adjustment
   - Opponent threat score maintenance (updated after every pick)
   - Combo threat pattern detection
   - Block flag logic (block_value vs personal_value vs budget check)
   - Nomination suggestion logic (nominate players you don't want with high market value)
2. Connect to Playwright bridge events to keep draft state current
3. On each nomination event: run full recommendation pipeline, emit to React via WebSocket

**Output per nomination:**
```json
{
  "player": {...},           // Full player record
  "recommendation": "buy",  // buy / bid_to / block / pass / nominate_to_drain
  "bid_ceiling": 34,
  "block_value": 41,
  "budget_allows_block": true,
  "active_flags": [...],
  "opponent_alerts": [...],  // Any combo threat flags
  "notes": "...",
  "budget_summary": {
    "your_remaining": 87,
    "roster_slots_remaining": 6,
    "minimum_completion_budget": 36,
    "spendable_on_this_player": 51
  }
}
```

**Verification:** Recommendation fires within 2 seconds of nomination event. Dependency flags activate correctly when trigger player already drafted. Block flags appear when opponent builds dangerous roster.

---

### Stage 13: Draft UI (React Frontend)

**Goal:** Full draft room in the app. No need to touch Yahoo's interface during the draft.

**Pages/components needed:**

**Draft room page** (main view during auction):
- Current nomination panel: player name, position, team, clock countdown
- Recommendation card: action badge (BUY/BLOCK/PASS), bid ceiling, key flags, notes
- Bid controls: increment/decrement bid, submit bid, pass button
- Nominate panel: search players, select, set opening bid, submit
- Live draft board: all picks so far (player, team, price)
- Opponent budget tracker: all teams with remaining budget displayed
- Your roster panel: your picks so far with prices
- Alert banner: opponent combo threat flags, block alerts, manual action required alerts

**Pre-draft page:**
- Player list with search/filter by position/tier
- Player card: full draft bible record (system grade, situation score, bid ceiling, flags, notes)
- Market value vs system value comparison
- Pipeline status: when agents last ran, data freshness indicator

**Setup:** React + Vite, Tailwind CSS, Zustand for state, socket.io-client for live updates

**⚠️ ASK USER** for any UI preferences before building (color scheme, layout preferences, dark/light mode default)

**Verification:** Full mock draft completable from app without touching Yahoo tab. Recommendation appears within 2 seconds of nomination. Budget trackers accurate throughout draft.

---

### Stage 14: Season Roster Store + Post-Draft Sync

**Goal:** After draft ends, data flows into in-season tracking.

Tasks:
1. Implement `season_roster` table population from draft results
2. Pull final draft results from Yahoo API after draft completes
3. Match picks to draft bible records
4. Initialize weekly tracking arrays
5. Set up APScheduler weekly jobs for in-season agents

**Verification:** All drafted players appear in `season_roster` with correct acquisition prices.

---

### Stage 15: Roster Monitor Agent

**Goal:** Weekly data refresh keeps season roster store current.

Tasks:
1. Implement `backend/agents/roster_monitor.py`
2. Weekly job: pull stats from Yahoo API, update snap count/target share trends
3. Detect usage drops (2+ consecutive weeks declining snaps → flag)
4. Update `current_trade_value`, `value_trend`, `sell_high_flag`, `buy_low_flag`
5. Pull Wednesday-Friday injury reports from Yahoo API, flag any rostered players listed

**Verification:** After simulated week of data, snap count trends update. Sell/buy flags appear on appropriate players.

---

### Stage 16: Opponent Analyzer Agent

**Goal:** Running profiles on all other managers, updated weekly.

Tasks:
1. Implement `backend/agents/opponent_analyzer.py`
2. Pull all league rosters weekly from Yahoo API
3. Build and maintain opponent profiles in DB
4. Management style detection logic
5. Vulnerability detection (bye conflicts, injury exposure, playoff schedule)
6. Threat score calculation

**Verification:** All opponents have profiles. Threat scores update after each simulated week.

---

### Stage 17: Trade Value Agent

**Goal:** Weekly player valuations with buy-low/sell-high signals.

Tasks:
1. Implement `backend/agents/trade_value.py`
2. Current value calculation using recent performance + schedule + situation
3. Buy-low signal detection (recency bias opportunities)
4. Sell-high signal detection (unsustainable performance)
5. Valuation asymmetry detection per opponent

**Verification:** Buy-low and sell-high flags appear on appropriate players after a week with relevant situations.

---

### Stage 18: Trade Analyzer

**Goal:** On-demand trade analysis tool.

Tasks:
1. Implement `backend/engines/trade_analyzer.py`
2. API endpoint `POST /trades/analyze` — accepts trade (give/receive arrays of player IDs)
3. Fairness analysis with roster context
4. Timing flag detection
5. Acceptance probability model using opponent profile
6. Counter proposal generation
7. React UI: trade input form, analysis results display

**Verification:** Submit a known lopsided trade → verdict is "unfavorable". Submit a balanced trade → "fair" verdict. Counter proposals make intuitive sense.

---

### Stage 19: Trade Proposal Engine

**Goal:** Proactive trade suggestions generated weekly.

Tasks:
1. Implement `backend/engines/trade_proposal.py`
2. Weekly job: cross-reference user's surplus/weakness vs each opponent's inverse
3. Valuation asymmetry targeting
4. Acceptance probability filtering (only surface proposals above 40% acceptance threshold)
5. React UI: trade suggestions list with proposal details and acceptance probability

**Verification:** At least one trade suggestion surfaces per week with a plausible rationale.

---

### Stage 20: Lineup Optimizer

**Goal:** Weekly lineup recommendations with reasoning.

Tasks:
1. Implement `backend/engines/lineup_optimizer.py`
2. Pull Vegas lines and implied team totals (scrape from a free odds site or use nfl_data_py)
3. Pull weather data for outdoor stadium games
4. Score all rostered players for the week
5. Optimize starting lineup within Yahoo roster slot rules
6. API endpoint `GET /lineup/week/{week_number}`
7. React UI: lineup card with start/sit recommendation and key factors per player

**Verification:** Lineup recommendation surfaces. A player with high Vegas implied total scores higher than same-tier player on low-total team.

---

### Stage 21: Waiver Wire Agent

**Goal:** Weekly waiver pickup recommendations.

Tasks:
1. Implement `backend/agents/waiver_wire.py`
2. Pull all available (unrostered) players from Yahoo API
3. Score by snap spike, depth chart change, upcoming schedule
4. Filter to only players with projected value window of 2+ weeks
5. API endpoint `GET /waivers/week/{week_number}`
6. React UI: waiver list with pickup reasoning and projected value window

**Verification:** At least one pickup recommendation per week. A player with snap count spike appears in recommendations.

---

### Stage 22: Pipeline Refresh UI + Admin

**Goal:** User can trigger agent pipeline runs and see data freshness from the app.

Tasks:
1. Admin page in React: pipeline status dashboard
2. Manual trigger buttons for each agent
3. Last run timestamp per agent
4. Data freshness indicators on player cards (warn if data is stale)
5. API endpoints for pipeline triggering and status

---

### Stage 23: Final Integration, Testing, and Deployment

**Goal:** Everything deployed, tested end-to-end, ready for real draft.

Tasks:
1. **ASK USER** to set up Railway account and provision Postgres instance if not already done
2. Set up GitHub Actions workflow for deploy-on-push to Railway
3. Set all production environment variables in Railway dashboard
4. Run full pre-draft pipeline in production
5. **ASK USER** to schedule 2 mock drafts with friends (or use Yahoo practice draft)
6. Run mock drafts through the app — verify:
   - Zero-lag nomination detection
   - Bid ceilings feel reasonable
   - Block flags fire correctly
   - Budget tracker stays accurate
   - No crashes or silent failures
7. Fix any issues found in mock drafts
8. Final pipeline refresh morning of real draft
9. Verify Beat Reporter agent has run and draft bible is current

---

## Key Design Decisions (Reference)

**Why no polling:** Every lag problem in the previous draft app was a polling problem. This system uses event-driven detection everywhere — WebSocket interception, MutationObserver, FastAPI WebSocket push. Polling is never used.

**Why direct Anthropic SDK:** LangChain/CrewAI add abstraction that makes debugging harder. With a well-defined agent spec, raw SDK tool use is cleaner and more transparent.

**Why PostgreSQL over a vector DB:** pgvector gives vector search in the same database as structured data, eliminating a separate infrastructure component. The draft bible is primarily relational — pgvector is additive.

**Why Railway:** Zero DevOps for a solo project with a hard deadline. Managed Postgres, environment variables, deploy on push. Migrate when/if it scales.

**Two-value system rationale:** Market value (what the room expects) and system value (what we think the player is worth) serve different purposes. Market value predicts room behavior. System value determines our ceiling. The gap is the edge. For elite players, market value gets more weight because positional scarcity means overpaying is sometimes correct.

**Playoff schedule as first-class field:** Most fantasy tools bury playoff matchup data in notes or don't surface it at all. This system stores it as a queryable field and the live draft agent uses it explicitly in close decisions.

**College trust signal:** QBs default to receivers they've thrown to extensively under pressure, including college connections. This is particularly relevant for rookie QBs in Year 1. cfbfastR data provides college target share history.

**Dependency flags as structured objects:** Not text notes. Every relationship between players is a structured JSON object with trigger conditions, value impact percentages, and confidence levels. This allows the live draft agent to reason about them programmatically without parsing text under time pressure.

**The McConkey/Allen situation must not happen again:** The Roster Changes agent is specifically designed to catch target share displacement caused by acquisitions. The canonical test at the end of Stage 4 verifies this logic works.

---

## API Cost Efficiency

Every Anthropic API call costs money. The pre-draft pipeline runs across 32 teams and 200+ players — if agents are naively implemented (one API call per player, no caching, uncompressed prompts), a single pipeline run can become very expensive. These rules are **mandatory**, not optional. Build them in from the start — retrofitting cost controls after the fact is painful.

---

### Rule 1: Batch by team, never by individual player

**Wrong approach:** One API call per player = 200+ calls per pipeline run.

**Correct approach:** Batch all players on the same team into a single API call. Pass the team's system grade and all relevant players together, instruct the model to return a JSON array of all player outputs in one response.

```python
# WRONG — 200+ API calls
for player in all_players:
    result = await client.messages.create(
        model="claude-haiku-...",
        messages=[{"role": "user", "content": build_prompt(player)}]
    )

# CORRECT — 32 API calls (one per team)
for team in all_teams:
    team_players = [p for p in all_players if p.team == team.abbr]
    result = await client.messages.create(
        model="claude-haiku-...",
        messages=[{"role": "user", "content": build_team_batch_prompt(team, team_players)}]
    )
    # Parse JSON array from result, write all player records
```

This applies to: Player Profiles agent, Injury Risk agent, Schedule agent.

The Roster Changes agent batches by team too — pass all transactions for a team in one call and reason through all dependency implications together.

---

### Rule 2: Hash-based caching — never re-run unchanged data

Before every API call, compute a hash of the input data. Compare it to the stored hash from the last run. If they match, skip the API call entirely and use the cached result.

```python
import hashlib
import json

async def should_rerun(entity_id: str, input_data: dict, cache_table: str) -> bool:
    current_hash = hashlib.sha256(
        json.dumps(input_data, sort_keys=True).encode()
    ).hexdigest()
    
    stored = await db.fetch_one(
        f"SELECT input_hash FROM {cache_table} WHERE entity_id = :id",
        {"id": entity_id}
    )
    
    if stored and stored["input_hash"] == current_hash:
        return False  # Skip — nothing changed
    return True  # Re-run and update hash

# Store hash alongside every agent output
async def save_with_hash(entity_id: str, output: dict, input_data: dict, table: str):
    input_hash = hashlib.sha256(
        json.dumps(input_data, sort_keys=True).encode()
    ).hexdigest()
    await db.execute(
        f"INSERT INTO {table} (..., input_hash) VALUES (..., :hash) "
        f"ON CONFLICT (entity_id) DO UPDATE SET ..., input_hash = :hash",
        {**output, "hash": input_hash}
    )
```

Add `input_hash VARCHAR(64)` column to every agent output table.

**What triggers a re-run per agent:**
- Team Systems: roster changes, coaching staff changes since last run
- Roster Changes: new OverTheCap transactions since last run
- Player Profiles: team system grade changed, or player's target share data updated
- Injury Risk: new injury log entry for this player
- Schedule: NFL schedule updated, or defensive roster changes on opponent teams
- Beat Reporter: always re-runs (it's the freshness layer, designed to run daily)

During the season, a weekly refresh should re-run roughly 5-15 players and 2-3 teams, not all 200 players.

---

### Rule 3: Model tiering — Haiku for extraction, Sonnet for reasoning

Claude Haiku is significantly cheaper than Claude Sonnet. Many agent tasks do not require Sonnet's reasoning depth. Use the cheapest model that produces correct output for each task type.

**Use `claude-haiku-4-5-20251001` for:**
- Pulling and formatting raw data into structured JSON
- Parsing beat reporter RSS feeds and classifying signal types
- Computing schedule grades from pre-aggregated defensive rankings
- Extracting injury log entries from structured records
- Formatting team batch player data before reasoning pass
- Waiver wire snap count spike detection (pattern matching, not reasoning)
- Lineup optimizer stat aggregation pass

**Use `claude-sonnet-4-6` for:**
- Roster Changes chain-of-reasoning (the McConkey/Allen dependency logic)
- Dependency flag confidence assessment
- Trade analysis and counter proposal generation
- Live draft recommendations
- Opponent management style detection
- Any task requiring multi-step causal reasoning

**Implementation pattern — two-pass for complex agents:**
```python
# Pass 1: Haiku extracts and structures raw data cheaply
raw_structured = await call_haiku(
    prompt=EXTRACTION_PROMPT,
    data=raw_input,
    max_tokens=1000
)

# Pass 2: Sonnet reasons over the pre-structured data
reasoning_output = await call_sonnet(
    prompt=REASONING_PROMPT,
    data=raw_structured,  # Already clean — smaller input
    max_tokens=2000
)
```

This pattern is especially valuable for the Roster Changes agent where you need to extract all transactions cheaply first, then reason through the dependency chains with Sonnet.

---

### Rule 4: JSON-only output, no prose

Every agent prompt must instruct the model to return only a JSON object or array with no preamble, no explanation, no markdown code fences, no closing remarks. Prose output wastes output tokens you're paying for.

**Every agent system prompt must include:**
```
You are a data extraction and analysis agent. 
Respond ONLY with valid JSON matching the schema provided.
Do not include any explanation, preamble, markdown formatting, or text outside the JSON.
Your entire response must be parseable by json.loads().
```

**Output parsing must strip any accidental wrapping:**
```python
def parse_agent_output(raw: str) -> dict:
    # Strip markdown code fences if model adds them despite instructions
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())
```

---

### Rule 5: Pre-aggregate data in Python before API calls

Never pass raw play-by-play data or large datasets directly into a prompt. Aggregate in Python first — computation in Python is free, computation in the model is not.

```python
# WRONG — passes thousands of raw rows into the prompt
raw_pbp = nfl_data.get_pbp(season=2024, team="LAC")
prompt = f"Here is the play-by-play data: {raw_pbp.to_json()}. Calculate target share..."

# CORRECT — aggregate in Python, pass only the summary
stats = nfl_data.get_pbp(season=2024, team="LAC")
aggregated = {
    "total_team_targets": len(stats[stats.pass_attempt == 1]),
    "player_targets": stats.groupby("receiver_player_name")["pass_attempt"].sum().to_dict(),
    "target_share_by_player": (
        stats.groupby("receiver_player_name")["pass_attempt"].sum() /
        len(stats[stats.pass_attempt == 1])
    ).to_dict(),
    "air_yards_by_player": stats.groupby("receiver_player_name")["air_yards"].sum().to_dict(),
    "routes_run_by_player": stats.groupby("receiver_player_name")["route"].count().to_dict(),
}
prompt = f"Given these pre-aggregated stats: {json.dumps(aggregated)}. Evaluate..."
```

The model only needs the summary statistics, not the underlying data it would have to aggregate itself.

---

### Rule 6: Explicit max_tokens on every API call

Every `client.messages.create()` call must have a `max_tokens` parameter calibrated to what that specific call actually needs. Never omit it.

```python
MAX_TOKENS = {
    # Pre-draft pipeline
    "team_system_grade":          500,   # One team
    "player_profile_batch":      3000,   # Full team ~22 players
    "roster_changes_team":       2000,   # All transactions for one team
    "injury_risk_batch":         2000,   # Full team injury profiles
    "schedule_batch":            1500,   # Full team schedule grades
    "beat_reporter_signal":       300,   # One article/signal
    
    # Live draft
    "live_draft_recommendation":  400,   # Single nomination response
    "nomination_suggestion":      200,   # Who to nominate
    
    # In-season
    "trade_analysis":            1500,
    "trade_proposals_weekly":    2000,
    "lineup_recommendation":     1000,
    "waiver_wire_weekly":        1000,
    "opponent_profile_update":    800,
}
```

If an agent ever hits its max_tokens ceiling, log a warning — it means either the ceiling is too low or the prompt is generating unexpectedly verbose output that should be investigated.

---

### Rule 7: Dry run mode on all pipeline scripts

Every pipeline script must support a `--dry-run` flag that:
1. Logs every API call that would be made (model, estimated input tokens, estimated output tokens, estimated cost)
2. Shows which agents would be skipped due to cache hits
3. Prints total estimated cost for the run
4. Does NOT actually call the API

```python
# scripts/run_predraft_pipeline.py
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true", 
                    help="Estimate costs without calling API")
parser.add_argument("--agent", type=str, default="all",
                    help="Run specific agent only: team_systems, roster_changes, etc.")
parser.add_argument("--team", type=str, default=None,
                    help="Run for specific team only (e.g. LAC)")
args = parser.parse_args()

# Pricing constants (update when Anthropic changes pricing)
HAIKU_INPUT_PER_MTK  = 0.80   # per million tokens
HAIKU_OUTPUT_PER_MTK = 4.00
SONNET_INPUT_PER_MTK = 3.00
SONNET_OUTPUT_PER_MTK = 15.00

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if "haiku" in model:
        return (input_tokens * HAIKU_INPUT_PER_MTK + 
                output_tokens * HAIKU_OUTPUT_PER_MTK) / 1_000_000
    return (input_tokens * SONNET_INPUT_PER_MTK + 
            output_tokens * SONNET_OUTPUT_PER_MTK) / 1_000_000
```

**Always run `--dry-run` before the first run of any new agent or pipeline change.**

---

### Rule 8: Cost estimate and confirmation before full pipeline runs

The pipeline script must print a cost estimate and require explicit confirmation before running a full pipeline that will make more than 10 API calls.

```python
async def confirm_pipeline_run(estimated_calls: int, estimated_cost: float):
    print(f"\n{'='*50}")
    print(f"Pipeline run summary:")
    print(f"  API calls:       {estimated_calls}")
    print(f"  Estimated cost:  ${estimated_cost:.4f}")
    print(f"  Cache hits:      {cache_hits} (skipped)")
    print(f"{'='*50}")
    
    if estimated_calls > 10:
        confirm = input("\nProceed? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Cancelled.")
            sys.exit(0)
```

---

### Rule 9: Incremental partial runs

The pipeline must support running individual agents or individual teams without running everything. This is the normal operating mode during the season.

```bash
# Run only the beat reporter agent (daily freshness)
python scripts/run_predraft_pipeline.py --agent beat_reporter

# Refresh one team after a big trade
python scripts/run_predraft_pipeline.py --agent roster_changes --team LAC
python scripts/run_predraft_pipeline.py --agent player_profiles --team LAC

# Full run (only do this before draft or at start of season)
python scripts/run_predraft_pipeline.py --agent all
```

---

### Rule 10: Token usage logging

Log actual token usage for every API call to the database. This builds a cost audit trail and lets you identify which agents are most expensive over time.

```sql
CREATE TABLE api_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(50),
    model VARCHAR(50),
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_cost_usd DECIMAL(8,6),
    cache_hit BOOLEAN DEFAULT false,
    entity_id VARCHAR(100),    -- team abbr or player id being processed
    called_at TIMESTAMP DEFAULT NOW()
);
```

Add a `POST /admin/cost-report` endpoint that summarizes usage by agent, by week, and total season spend. Surface this in the admin UI from Stage 22.

---

### Expected cost profile (reference estimates)

These are rough estimates based on current Anthropic pricing. Actual costs depend on prompt size and output verbosity. Use these as benchmarks — if an agent exceeds these significantly, investigate.

| Agent / Task | Calls per full run | Model | Est. cost per full run |
|---|---|---|---|
| Team Systems (all 32 teams) | 32 | Haiku | ~$0.05 |
| Roster Changes (all 32 teams) | 64 (2-pass) | Haiku + Sonnet | ~$0.40 |
| Player Profiles (32 team batches) | 32 | Haiku + Sonnet | ~$0.35 |
| Injury Risk (32 team batches) | 32 | Haiku | ~$0.08 |
| Schedule (32 team batches) | 32 | Haiku | ~$0.06 |
| Beat Reporter (daily) | 10-20 | Haiku | ~$0.02/day |
| **Full pre-draft pipeline** | ~200 total | Mixed | **~$1.00-1.50** |
| Weekly in-season refresh (partial) | 20-40 | Mixed | ~$0.15-0.30/week |
| Live draft recommendation | 1 per nomination | Sonnet | ~$0.01 each |
| Trade analysis (on demand) | 1 per request | Sonnet | ~$0.03 each |

A full season's API usage (1 full pipeline run + 17 weekly refreshes + draft day + in-season features) should cost well under **$20 total** if these rules are followed correctly.

---

### Add to `backend/agents/base_agent.py`

The base agent class must enforce cost controls for all child agents:

```python
class BaseAgent:
    def __init__(self, model: str, max_tokens: int, dry_run: bool = False):
        self.client = anthropic.AsyncAnthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.dry_run = dry_run
    
    async def call(self, system: str, user: str, input_data: dict) -> dict:
        input_hash = self._hash(input_data)
        
        # Cache check
        cached = await self._get_cached(input_hash)
        if cached:
            await self._log_usage(cache_hit=True)
            return cached
        
        # Dry run — estimate and return
        if self.dry_run:
            estimated_tokens = len(system + user) // 4  # rough estimate
            cost = estimate_cost(self.model, estimated_tokens, self.max_tokens)
            print(f"[DRY RUN] {self.__class__.__name__}: ~{estimated_tokens} input tokens, "
                  f"max {self.max_tokens} output tokens, est. ${cost:.5f}")
            return {}
        
        # Real call
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}]
        )
        
        result = parse_agent_output(response.content[0].text)
        
        # Log and cache
        await self._log_usage(response.usage, cache_hit=False)
        await self._save_cached(input_hash, result)
        
        return result
    
    def _hash(self, data: dict) -> str:
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()
```

---

## Testing and Git Workflow

Every feature must be tested before it is committed to GitHub. This is not optional. The workflow is always: write code → write tests → run tests → fix failures → commit. A feature is not complete until its tests pass. Never commit broken tests. Never skip tests because the code looks correct.

---

### Testing Philosophy

**Unit tests** mock all external dependencies (Anthropic API, PostgreSQL, Yahoo API, Playwright). They run fast, cost nothing, and must pass before every commit. These are the primary test suite.

**Integration tests** hit real infrastructure (real DB, real API calls). They run manually before deployment and before the real draft. They are never run automatically on commit — doing so would defeat the cost efficiency rules and create flaky tests dependent on network state.

**The distinction matters:** if a test calls `anthropic.messages.create()` without a mock, it is an integration test and must be in `tests/integration/`, not `tests/unit/`.

---

### Directory Structure

```
tests/
├── unit/
│   ├── agents/
│   │   ├── test_team_systems.py
│   │   ├── test_roster_changes.py
│   │   ├── test_player_profiles.py
│   │   ├── test_injury_risk.py
│   │   ├── test_schedule.py
│   │   ├── test_beat_reporter.py
│   │   ├── test_roster_monitor.py
│   │   ├── test_opponent_analyzer.py
│   │   ├── test_trade_value.py
│   │   └── test_waiver_wire.py
│   ├── engines/
│   │   ├── test_live_draft.py
│   │   ├── test_trade_analyzer.py
│   │   ├── test_trade_proposal.py
│   │   └── test_lineup_optimizer.py
│   ├── integrations/
│   │   ├── test_yahoo_api.py
│   │   ├── test_yahoo_playwright.py
│   │   └── test_nfl_data.py
│   └── models/
│       └── test_schemas.py
├── integration/
│   ├── test_pipeline_full_run.py
│   ├── test_yahoo_live_draft.py
│   └── test_database_roundtrip.py
├── fixtures/
│   ├── players.json          # Sample player records
│   ├── team_systems.json     # Sample team system grades
│   ├── draft_state.json      # Sample mid-draft state
│   └── yahoo_ws_frames.json  # Sample Yahoo WebSocket payloads
└── conftest.py               # Shared fixtures and mocks
```

---

### Required Test Coverage Per Component

#### `test_roster_changes.py` — The most critical test file

This agent contains the most complex reasoning in the system. Every dependency flag type must have at least one named test.

```python
# REQUIRED named test cases — these must exist by name:

def test_mcconkey_allen_displacement():
    """
    THE canonical test. Allen signs with LAC.
    McConkey must receive DISPLACED flag with negative value impact.
    McConkey must also receive BENEFICIARY flag (value rises if Allen absent).
    """

def test_target_share_displacement_direct_role_overlap():
    """Slot receiver arrives → incumbent slot receiver gets DISPLACED flag."""

def test_target_share_displacement_no_flag_different_role():
    """Deep threat arrives → slot receiver does NOT get DISPLACED flag."""

def test_qb_trust_score_nfl_history():
    """QB and WR with 3+ shared NFL seasons → trust score above 60."""

def test_qb_trust_score_college_history():
    """QB and WR shared college program 2+ seasons → COLLEGE_TRUST flag generated."""

def test_qb_trust_score_no_history():
    """QB and WR with no shared history → trust score below 30."""

def test_backfield_committee_two_similar_profiles():
    """Two workhorse RBs on same roster → COMMITTEE flag on both."""

def test_backfield_committee_complementary_profiles():
    """Workhorse + pass-catching specialist → mild flag only, not strong."""

def test_coaching_change_scheme_mismatch():
    """Possession WR2 on team that hired air-raid OC → SCHEME_FIT flag."""

def test_dependency_flag_value_impact_applied():
    """DISPLACED flag with -0.35 impact → player risk_adjusted_value reduced by 35%."""

def test_high_aav_signing_weighted_higher():
    """$20M AAV signing weighted more than $5M AAV for displacement model."""
```

#### `test_live_draft.py` — Draft day correctness

```python
def test_displaced_flag_activates_when_trigger_drafted():
    """
    McConkey has DISPLACED flag triggered by Allen.
    When Allen is drafted by any team, McConkey's bid ceiling drops.
    """

def test_displaced_flag_inactive_when_trigger_not_drafted():
    """Allen not yet drafted → McConkey's full ceiling applies."""

def test_beneficiary_flag_activates_correctly():
    """Allen drafted → McConkey BENEFICIARY flag does NOT activate (Allen is healthy/playing)."""

def test_block_flag_fires_on_combo_threat():
    """Opponent has CMC. Jonathan Taylor nominated. Block flag must fire."""

def test_block_flag_suppressed_low_opponent_budget():
    """Opponent has $8 remaining. Block flag suppressed — they can't afford it."""

def test_block_flag_suppressed_insufficient_own_budget():
    """User can't afford block without going below minimum completion budget."""

def test_bid_ceiling_tier1_uses_anchor_weight():
    """Tier 1 player: bid ceiling blends system value and market value at 0.80 weight."""

def test_bid_ceiling_tier4_ignores_anchor():
    """Tier 4 player: bid ceiling uses system value only, market value ignored."""

def test_nomination_suggestion_drains_opponent_budget():
    """Nominate players with high market value that user does NOT want."""

def test_budget_summary_accurate_mid_draft():
    """After 5 picks at known prices, remaining budget and spendable amount are correct."""

def test_recommendation_fires_under_2_seconds():
    """End-to-end recommendation must complete within 2000ms (mocked DB and API)."""
```

#### `test_injury_risk.py`

```python
def test_soft_tissue_single_event_moderate_flag():
def test_soft_tissue_two_same_area_three_years_high_flag():
def test_soft_tissue_two_same_area_pattern_flag_set():
def test_acl_recent_post_acl_flag():
def test_fracture_traumatic_low_risk_no_long_term_modifier():
def test_fracture_stress_moderate_risk():
def test_concussion_single_no_compounding():
def test_concussion_two_plus_compounding_modifier():
def test_chronic_turf_toe_does_not_reset():
def test_workload_cliff_300_plus_carries():
def test_high_mileage_600_plus_career_carries():
def test_age_multiplier_under_26_baseline():
def test_age_multiplier_31_plus_elevated():
def test_risk_modifier_applied_to_baseline_value():
```

#### `test_yahoo_playwright.py`

```python
def test_nomination_event_parsed_from_ws_frame():
    """Sample Yahoo WS frame with nomination → correct player ID and clock extracted."""

def test_bid_update_event_parsed():
    """Sample bid update frame → correct price extracted."""

def test_draft_pick_confirmed_event_parsed():
    """Pick confirmed frame → player marked as drafted in state."""

def test_bridge_failure_emits_manual_action_alert():
    """Simulated Playwright exception → MANUAL_ACTION_REQUIRED event emitted."""

def test_health_check_triggers_reconnect():
    """Simulated connection drop → reconnect attempted within 15 seconds."""

def test_no_polling_in_event_chain():
    """
    Inspect bridge code for time.sleep(), asyncio.sleep() in event loops,
    or setInterval equivalents. Any found → test fails.
    """
```

#### `test_trade_analyzer.py`

```python
def test_lopsided_trade_flagged_unfavorable():
def test_balanced_trade_flagged_fair():
def test_sell_high_flag_on_td_spike_low_targets():
def test_buy_low_flag_on_matchup_driven_slump():
def test_acceptance_probability_high_for_needy_opponent():
def test_acceptance_probability_low_for_unnecessary_trade():
def test_counter_proposal_flips_unfavorable_to_favorable():
def test_counter_proposal_maintains_reasonable_acceptance_rate():
```

#### `test_schedule.py`

```python
def test_playoff_grade_is_first_class_field_not_notes():
    """playoff_window_grade must be a queryable column, never only in schedule_notes."""

def test_early_window_weighted_more_for_tier1():
def test_weather_flag_applied_outdoor_cold_city_november():
def test_bye_week_conflict_detected():
def test_defensive_grade_adjusted_for_fa_departure():
```

---

### Mocking Conventions

All unit tests must mock these four external dependencies consistently. Define them in `conftest.py` so every test file can use them:

```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from pathlib import Path

# Load fixture data
FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def mock_anthropic():
    """Mock Anthropic API — returns fixture JSON, never calls real API."""
    with patch("anthropic.AsyncAnthropic") as mock:
        client = AsyncMock()
        mock.return_value = client
        
        # Default response — tests override this per case
        client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"result": "mocked"}')],
            usage=MagicMock(input_tokens=100, output_tokens=50)
        )
        yield client

@pytest.fixture
def mock_db():
    """Mock database session — no real DB connections in unit tests."""
    with patch("backend.database.get_session") as mock:
        session = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session

@pytest.fixture
def mock_playwright():
    """Mock Playwright browser — no real browser in unit tests."""
    with patch("playwright.async_api.async_playwright") as mock:
        browser = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=browser)
        yield browser

@pytest.fixture
def mock_nfl_data():
    """Mock nfl_data_py — returns fixture dataframes."""
    with patch("backend.integrations.nfl_data.NFLDataClient") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client

@pytest.fixture
def sample_player():
    """Standard player record for testing."""
    return json.loads((FIXTURES / "players.json").read_text())[0]

@pytest.fixture
def sample_draft_state():
    """Mid-draft state with some players already picked."""
    return json.loads((FIXTURES / "draft_state.json").read_text())

@pytest.fixture
def yahoo_nomination_frame():
    """Sample Yahoo WebSocket nomination frame payload."""
    return json.loads((FIXTURES / "yahoo_ws_frames.json").read_text())["nomination"]
```

---

### Running Tests

Add these scripts to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests/unit"]
asyncio_mode = "auto"
markers = [
    "unit: fast unit tests, no external dependencies",
    "integration: requires real DB and APIs, run manually",
    "slow: takes more than 5 seconds",
]

[tool.coverage.run]
source = ["backend"]
omit = ["tests/*", "scripts/*", "alembic/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

```bash
# Run unit tests (fast, no cost, run before every commit)
pytest tests/unit/ -v

# Run with coverage report
pytest tests/unit/ --cov=backend --cov-report=term-missing

# Run a specific agent's tests
pytest tests/unit/agents/test_roster_changes.py -v

# Run only the canonical McConkey/Allen test
pytest tests/unit/agents/test_roster_changes.py::test_mcconkey_allen_displacement -v

# Run integration tests (manual only, costs money)
pytest tests/integration/ -v -m integration

# Run everything except slow tests
pytest tests/unit/ -m "not slow"
```

**Minimum coverage requirement: 80% per module.** If coverage drops below 80% on any backend module, the commit is blocked.

---

### Git Workflow

#### Branch strategy

```
main          — production, always deployable, protected
develop       — integration branch, merges to main before deployment
feat/*        — feature branches, one per build stage
fix/*         — bug fix branches
```

Never commit directly to `main`. All work goes through feature branches.

#### Commit message format

Use conventional commits. Every commit message must follow this format:

```
<type>(<scope>): <short description>

[optional body]
[optional footer]
```

**Types:**
- `feat` — new feature or build stage
- `fix` — bug fix
- `test` — adding or updating tests
- `refactor` — code change that neither fixes a bug nor adds a feature
- `chore` — maintenance (deps, config, CI)
- `docs` — documentation only

**Scopes** match the build stage or component:
- `foundation`, `data-ingestion`, `team-systems`, `roster-changes`, `player-profiles`
- `injury-risk`, `schedule`, `beat-reporter`, `valuations`
- `yahoo-api`, `yahoo-playwright`, `live-draft`, `draft-ui`
- `season-store`, `roster-monitor`, `opponent-analyzer`, `trade-value`
- `trade-analyzer`, `trade-proposal`, `lineup-optimizer`, `waiver-wire`
- `pipeline-ui`, `deployment`

**Examples:**
```bash
feat(roster-changes): add target share displacement model

Implements the McConkey/Allen chain-of-reasoning logic.
DISPLACED and CONTINGENT flags generated correctly.
All 11 named test cases passing.

feat(live-draft): add opponent combo threat detection

Fires block flag when opponent builds elite RB stack.
Block suppressed when opponent budget under $15.

fix(yahoo-playwright): handle WS reconnect on connection drop

Health check now triggers reconnect within 15 seconds.
Manual action alert fires immediately on bridge failure.

test(injury-risk): add soft tissue pattern detection tests

All injury category tests passing.
Coverage: 94% on injury_risk.py

chore(deps): update anthropic sdk to latest
```

#### The commit workflow — follow this exactly

```bash
# 1. Create feature branch for the build stage
git checkout -b feat/roster-changes

# 2. Write the feature code

# 3. Write unit tests in tests/unit/

# 4. Run tests — ALL must pass before proceeding
pytest tests/unit/agents/test_roster_changes.py -v

# 5. Run coverage — must be 80%+ on the new module
pytest tests/unit/agents/test_roster_changes.py --cov=backend/agents/roster_changes --cov-report=term-missing

# 6. Run the full unit suite — verify nothing else broke
pytest tests/unit/ -v

# 7. If all green: commit
git add .
git commit -m "feat(roster-changes): add target share displacement model

Implements DISPLACED, CONTINGENT, BENEFICIARY, COMMITTEE,
SCHEME_FIT, and COLLEGE_TRUST dependency flags.
McConkey/Allen canonical test passing.
All 11 named test cases passing. Coverage: 91%."

# 8. Push and open PR to develop
git push origin feat/roster-changes

# NEVER do this:
git add . && git commit -m "wip" && git push   # No
git commit -m "fix stuff"                       # No
git push --force                                # No
```

#### Pre-commit hooks

Set up pre-commit to enforce standards automatically. Add `.pre-commit-config.yaml` to the repo root:

```yaml
repos:
  - repo: local
    hooks:
      - id: run-unit-tests
        name: Unit tests must pass
        entry: pytest tests/unit/ -x -q
        language: system
        pass_filenames: false
        always_run: true

      - id: check-coverage
        name: Coverage must be 80%+
        entry: pytest tests/unit/ --cov=backend --cov-fail-under=80 -q
        language: system
        pass_filenames: false
        always_run: true

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: detect-private-key
      - id: no-commit-to-branch
        args: [--branch, main]
```

Install with:
```bash
pip install pre-commit
pre-commit install
```

After this, running `git commit` automatically runs unit tests, coverage check, linting, and formatting. If any fail, the commit is blocked until they're fixed.

---

### GitHub Actions CI

Create `.github/workflows/ci.yml`. This runs on every push and pull request:

```yaml
name: CI

on:
  push:
    branches: [develop, feat/*, fix/*]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: fantasy_football_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v2

      - name: Install dependencies
        run: uv sync

      - name: Run migrations on test DB
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/fantasy_football_test
        run: uv run alembic upgrade head

      - name: Run unit tests
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/fantasy_football_test
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY_TEST }}
          ENVIRONMENT: test
        run: uv run pytest tests/unit/ -v --cov=backend --cov-report=xml --cov-fail-under=80

      - name: Upload coverage report
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v2
      - run: uv sync
      - run: uv run ruff check backend/ tests/
      - run: uv run ruff format --check backend/ tests/
```

**⚠️ ASK USER** to add `ANTHROPIC_API_KEY_TEST` as a GitHub Actions secret (Settings → Secrets → Actions). This is a separate key from production — set a low spend limit on it in the Anthropic console.

---

### What "stage complete" means

A build stage is not complete until ALL of the following are true:

1. Feature code is written and runs without errors
2. Unit tests are written with named test cases per the requirements above
3. All unit tests pass (`pytest tests/unit/ -v` shows all green)
4. Coverage is 80%+ on all new modules
5. Full unit suite still passes (nothing regressed)
6. Code is committed with a properly formatted commit message
7. Branch is pushed to GitHub
8. CI pipeline passes on GitHub Actions

Only then confirm completion with the user and move to the next stage.

---

### Test fixtures to create at Stage 1

Create these fixture files immediately during Stage 1 (Foundation). They are used throughout all later stages.

**`tests/fixtures/players.json`** — 5 sample player records covering different positions, tiers, and flag combinations

**`tests/fixtures/team_systems.json`** — 3 sample team system records: one strong (elite QB, good line), one weak (rookie QB, poor line with compound flag), one average

**`tests/fixtures/draft_state.json`** — Mid-draft state: 8 players already drafted at known prices, 3 different opponents with varying budgets, one opponent with a tier-1 RB already building toward a combo threat

**`tests/fixtures/yahoo_ws_frames.json`** — Sample Yahoo WebSocket payloads for: nomination event, bid update event, draft pick confirmed event, clock warning event. These should be captured from a real Yahoo draft room during Stage 11 testing and committed to fixtures.

**⚠️ ASK USER** when creating `yahoo_ws_frames.json` — the actual Yahoo WS frame format can only be captured by opening a real Yahoo draft room in browser dev tools and recording the WebSocket traffic. Ask the user to do this and share the payloads.

---

## Important Reminders for Claude Code

2. **Complete each stage fully before moving to the next.** Verify with the user at the end of each stage.

3. **Never commit `.env` to the repository.** It is gitignored. Only `.env.example` goes in the repo.

4. **The draft is on Yahoo, not Sleeper.** All platform integration code targets Yahoo Fantasy Sports.

5. **Auction draft format.** Not snake draft. All draft logic assumes auction mechanics (nominations, bids, budgets).

6. **Zero polling anywhere in the live draft chain.** Event-driven only. If you find yourself writing `time.sleep()` or `setInterval()` in a draft event context, stop and redesign.

7. **The Playwright bridge must degrade gracefully.** If it fails mid-draft, emit a `MANUAL_ACTION_REQUIRED` event to the UI immediately. Never crash silently.

8. **All agents write to the draft bible before the live draft agent reads from it.** The live agent does not do research — it queries results.

9. **The playoff schedule grade is a first-class field, not a note.** Store it in `playoff_window_grade` column, not in `schedule_notes`.

10. **Test the McConkey/Allen scenario explicitly at the end of Stage 4.** It is the canonical test case for the Roster Changes agent.

11. **Never write a bare API call.** Every `client.messages.create()` call must go through `BaseAgent.call()` which enforces caching, logging, dry run mode, and max_tokens. No agent bypasses the base class.

12. **Batch by team, never by player.** If you find yourself looping over individual players and calling the API inside that loop, stop and restructure to batch the whole team in one call.

13. **Always run `--dry-run` before running any agent for the first time.** Verify the cost estimate looks reasonable before making real API calls.

14. **Model selection is mandatory.** Every agent must explicitly declare which model it uses (Haiku or Sonnet) based on whether the task is data extraction or reasoning. Default is Haiku. Only upgrade to Sonnet when the task genuinely requires multi-step causal reasoning.

15. **Pre-aggregate all data in Python before building prompts.** Never pass raw dataframes, CSV content, or play-by-play rows into a prompt. Aggregate first in Python, pass only the summary statistics.

16. **The `api_usage_log` table must be populated on every API call.** This is the cost audit trail. If a call is made without logging usage, it is a bug.
17. **A stage is not complete until all unit tests pass, coverage is 80%+, and the commit is pushed to GitHub.** Writing the code is not enough. Tests must be written and green before confirming stage completion with the user.

18. **Never commit directly to `main`.** All work goes on feature branches (`feat/<stage-name>`). PRs merge to `develop`. `develop` merges to `main` before deployment only.

19. **Every commit message must follow conventional commit format.** `feat(scope): description` not `update stuff` or `wip`. See the Git Workflow section for the full format and scope list.

20. **Unit tests mock all external dependencies.** A unit test that calls the real Anthropic API, real database, or real Yahoo API is an integration test and belongs in `tests/integration/`, not `tests/unit/`. Integration tests are never run automatically on commit.

21. **Pre-commit hooks must be installed at Stage 1 and must never be bypassed.** `git commit --no-verify` is never acceptable. If tests are failing, fix them — do not skip the hook.

22. **Create all test fixtures at Stage 1.** The fixture files in `tests/fixtures/` are used by tests across all later stages. Build them at the start, not on demand. For `yahoo_ws_frames.json`, ask the user to capture real WebSocket payloads from Yahoo's draft room dev tools.