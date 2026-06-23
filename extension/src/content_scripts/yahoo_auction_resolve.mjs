/**
 * Yahoo AUCTION draft resolver — React-client DOM (2026 replatform).
 *
 * Yahoo rebuilt the auction room as a React app rooted at
 * `#main-0-DraftClientBootstrap-Proxy` with NO semantic ids/classes on live
 * data. Two class families:
 *   - `ys-*` KEBAB classes (e.g. `.ys-team`, `.ys-player`) are hand-authored
 *     and semantic — OK as structural anchors.
 *   - `_ys_*` HASH classes are build-generated and ROTATE every Yahoo deploy —
 *     NEVER a primary key; only a fallback layered behind a text/structure check,
 *     and using one fires LOUD degradation telemetry (console.warn +
 *     selector_health) so the next rotation alarms instead of silently stalling.
 *
 * This module is DOM-structural (takes an Element root) but free of network
 * side effects, so it is unit-testable by parsing captured Yahoo outerHTML with
 * linkedom (see test/fixtures/auction/). Pure event-diffing helpers
 * (detectWinner, secondsFromClock) are reused from yahoo_draft_parse.mjs.
 *
 * STATUS: scaffold. The gate + .ys-team team parsing are verifiable against the
 * lobby capture. The nomination/name/bid/clock/bidder field tuning is HELD until
 * a real mid-nomination capture lands — those resolvers are wired to the agreed
 * strategy but must NOT be trusted/tuned against a single snapshot.
 */
import { detectWinner, secondsFromClock } from './yahoo_draft_parse.mjs'

export const AUCTION_ROOT_SELECTOR = '#main-0-DraftClientBootstrap-Proxy'

// Locale-configurable expected label for the user's own team card (Amendment A).
export const EXPECTED_YOU_LABEL = 'You'

// How far up from the clock span the nomination card may be (Amendment 1: cap
// the ascent so the LCA can't balloon toward the whole board).
const CARD_MAX_ASCENT = 6

const MONEY_RE = /^\$\d+/
const CLOCK_RE = /^\d{2}:\d{2}$/
const ROSTER_RE = /^\d+\/\d+$/
const TURN_RE = /(\d+)\s+nominations?\s+until your turn/i
// "your turn now" wording — TBD from the your-turn capture; permissive stub.
const YOUR_TURN_NOW_RE = /your turn to nominate|nominate a player|you'?re up( to nominate)?/i

// Known non-name labels that must never be read as a player name.
const KNOWN_LABELS = new Set([
  'You', 'Current Bid', 'Sold', 'Nominate', 'Bid', 'Pass', 'Queue',
  'Add to Queue', 'Your Turn', 'Board', 'Players', 'Results', 'Standings',
])

// ---------------------------------------------------------------------------
// Small DOM helpers (kept tiny so linkedom covers them)
// ---------------------------------------------------------------------------
const txt = (el) => (el && el.textContent ? el.textContent.trim() : '')
const spansIn = (el) => (el ? Array.from(el.querySelectorAll('span')) : [])
const notInDialog = (el) => !!el && !el.closest('[role="dialog"]')

export function auctionRoot(doc) {
  return doc ? doc.querySelector(AUCTION_ROOT_SELECTOR) : null
}

/** The live countdown span: MM:SS text, NOT inside a dialog/modal subtree. */
export function findLiveTimer(root) {
  if (!root) return null
  return spansIn(root).find((s) => CLOCK_RE.test(txt(s)) && notInDialog(s)) || null
}

/**
 * Negative gate: a post-draft summary/results-review state can share the React
 * root WITH .ys-team cards but no live auction. STUB — the exact marker is TBD
 * from the draft-complete capture; returns false (never blocks) until then.
 * When the capture lands, anchor this on the draft-complete text/structure.
 */
export function isDraftComplete(_root) {
  // TODO(capture: draft-complete.html): detect the draft-complete marker and
  // return true so the poller does NOT activate on a finished-draft summary.
  return false
}

// ---------------------------------------------------------------------------
// Activation gate (pure decision + DOM wrapper)
// ---------------------------------------------------------------------------

/**
 * Pure gate decision (unit-testable without a DOM). Active iff the React root is
 * present, the draft isn't complete, snake markers are absent (cross-poller
 * veto), and there's a live signal (a live timer OR at least one team card).
 */
export function auctionGateDecision({
  hasRoot,
  hasLiveTimer,
  teamCardCount,
  draftComplete,
  snakeMarkers,
}) {
  if (!hasRoot) return false
  if (draftComplete) return false
  if (snakeMarkers) return false // auction no-ops if snake markers present
  return !!hasLiveTimer || (teamCardCount || 0) >= 1
}

/** DOM wrapper: compute the gate inputs from a document/root and decide. */
export function shouldAuctionActivate(doc, { snakeMarkers = false } = {}) {
  const root = auctionRoot(doc)
  return auctionGateDecision({
    hasRoot: !!root,
    hasLiveTimer: root ? !!findLiveTimer(root) : false,
    teamCardCount: root ? root.querySelectorAll('.ys-team').length : 0,
    draftComplete: root ? isDraftComplete(root) : false,
    snakeMarkers,
  })
}

// ---------------------------------------------------------------------------
// Selector health (loud degradation telemetry)
// ---------------------------------------------------------------------------
function freshHealth() {
  // 'na' = not applicable this tick (e.g. no active nomination → no clock yet),
  // 'primary' = resolved off a stable anchor, 'fallback' = off a _ys_ hash,
  // 'missing' = anchor present but nothing matched.
  return { clock: 'na', name: 'na', bid: 'na', bidder: 'na', teams: 'na', turn: 'na' }
}

// ---------------------------------------------------------------------------
// Field resolvers (strategy wired; field tuning pending live nomination capture)
// ---------------------------------------------------------------------------
export function isNameShape(text) {
  const t = (text || '').trim()
  if (!t || t.length > 40) return false
  if (MONEY_RE.test(t) || CLOCK_RE.test(t) || ROSTER_RE.test(t)) return false
  if (/^\d/.test(t)) return false
  if (KNOWN_LABELS.has(t)) return false
  if (!/[A-Z]/.test(t)) return false
  return t.split(/\s+/).length >= 2 // >=2 tokens (Amendment 1)
}

/** Teams + your-team self-id. Verifiable against the lobby capture (Amendment A). */
export function resolveTeams(root, health, warn) {
  const cards = root ? Array.from(root.querySelectorAll('.ys-team')) : []
  if (cards.length === 0) {
    health.teams = 'missing'
    return { teams: {}, yourTeamId: null }
  }
  const teams = {}
  let yourTeamId = null
  let sawName = true
  for (const card of cards) {
    const dataId = card.getAttribute('data-id')
    const spans = spansIn(card)
    const budgetSpan = spans.find((s) => MONEY_RE.test(txt(s)))
    const rosterSpan = spans.find((s) => ROSTER_RE.test(txt(s)))
    const isYou = spans.some((s) => txt(s) === EXPECTED_YOU_LABEL)
    const nameSpan = spans.find((s) => {
      const t = txt(s)
      return t && t !== EXPECTED_YOU_LABEL && !MONEY_RE.test(t) && !ROSTER_RE.test(t)
    })
    const name = nameSpan ? txt(nameSpan) : dataId ? `Team ${dataId}` : null
    if (!nameSpan) sawName = false
    const budget = budgetSpan ? parseInt(txt(budgetSpan).replace(/[^\d]/g, ''), 10) : null
    let slotsUsed = null
    let totalSlots = null
    const rm = rosterSpan ? txt(rosterSpan).match(ROSTER_RE) : null
    if (rm) {
      const parts = txt(rosterSpan).split('/')
      slotsUsed = parseInt(parts[0], 10)
      totalSlots = parseInt(parts[1], 10)
    }
    if (name != null) {
      teams[name] = { budget, slotsUsed, totalSlots, dataId } // data-id = stable key
    }
    if (isYou && dataId != null) yourTeamId = dataId // PRIMARY self-id (Amendment A)
  }
  // Self-id fallback: _ys_1659jmf behind the You/data-id checks (loud).
  if (yourTeamId == null) {
    const fb = root.querySelector('.ys-team span._ys_1659jmf')
    const card = fb ? fb.closest('.ys-team') : null
    if (card) {
      yourTeamId = card.getAttribute('data-id')
      warn('team_self_id', 'fallback')
    }
  }
  health.teams = sawName ? 'primary' : 'fallback'
  return { teams, yourTeamId }
}

/** Smallest capped container holding the clock + a money span + a name candidate. */
export function resolveNominationCard(root) {
  const clock = findLiveTimer(root)
  if (!clock) return null // no live countdown → no active nomination
  let el = clock.parentElement
  let depth = 0
  while (el && depth < CARD_MAX_ASCENT) {
    const hasMoney = spansIn(el).some((s) => MONEY_RE.test(txt(s)))
    const hasPlayerId = !!el.querySelector('[class~="ys-player"][data-id], .ys-player[data-id]')
    const hasName = spansIn(el).some((s) => isNameShape(txt(s)))
    if (hasMoney && (hasPlayerId || hasName)) return el
    el = el.parentElement
    depth += 1
  }
  return null // cap hit without a valid card → treat as between-nominations
}

/** Player ID (Amendment B PRIMARY) — stable across deploys. */
export function resolvePlayerId(card) {
  const el = card
    ? card.querySelector('[class~="ys-player"][data-id], .ys-player[data-id]')
    : null
  return el ? el.getAttribute('data-id') : null
}

/**
 * Player name. Primary = the ys-player[data-id] row's name (Amendment B);
 * fallback = name-shape span in document order; last resort = the _ys_ name
 * span. Sets health.name and warns on any fallback.
 */
export function resolvePlayerName(card, playerId, health, warn) {
  if (!card) {
    health.name = 'na'
    return null
  }
  // Primary: name within the ys-player[data-id] subtree (id-anchored).
  if (playerId) {
    const row = card.querySelector(
      `[class~="ys-player"][data-id="${playerId}"], .ys-player[data-id="${playerId}"]`
    )
    const idName = row ? spansIn(row).map(txt).find(isNameShape) : null
    if (idName) {
      health.name = 'primary'
      return idName
    }
  }
  // Fallback: first name-shape span in document order within the card.
  const shapeName = spansIn(card).map(txt).find(isNameShape)
  if (shapeName) {
    health.name = 'fallback'
    warn('name', playerId ? 'shape(no-id-name)' : 'shape')
    return shapeName
  }
  // Last resort: the rotating _ys_ name span, behind the shape gate.
  const fb = card.querySelector('span._ys_1i9qkex')
  if (fb && isNameShape(txt(fb))) {
    health.name = 'fallback'
    warn('name', 'hash')
    return txt(fb)
  }
  health.name = 'missing'
  warn('name', 'missing')
  return null
}

/** Current bid: the money span INSIDE the nomination card (not a .ys-team budget). */
export function resolveBid(card, health, warn) {
  if (!card) {
    health.bid = 'na'
    return null
  }
  const moneySpan = spansIn(card).find(
    (s) => MONEY_RE.test(txt(s)) && !s.closest('.ys-team')
  )
  if (moneySpan) {
    health.bid = 'primary'
    return parseInt(txt(moneySpan).replace(/[^\d]/g, ''), 10)
  }
  const fb = card.querySelector('span._ys_uurq5p')
  if (fb && MONEY_RE.test(txt(fb))) {
    health.bid = 'fallback'
    warn('bid', 'hash')
    return parseInt(txt(fb).replace(/[^\d]/g, ''), 10)
  }
  health.bid = 'missing'
  warn('bid', 'missing')
  return null
}

/**
 * Current high-bidder team (Amendment 5). Resilient: the text in the card that
 * MATCHES a known .ys-team name (cross-checked). _ys_aug67i is the fallback.
 */
export function resolveBidder(card, teams, health, warn) {
  if (!card) {
    health.bidder = 'na'
    return null
  }
  const knownNames = new Set(Object.keys(teams || {}))
  const hit = spansIn(card)
    .map(txt)
    .find((t) => knownNames.has(t))
  if (hit) {
    health.bidder = 'primary'
    return hit
  }
  const fb = card.querySelector('span._ys_aug67i')
  if (fb && knownNames.has(txt(fb))) {
    health.bidder = 'fallback'
    warn('bidder', 'hash')
    return txt(fb)
  }
  health.bidder = teams && Object.keys(teams).length ? 'missing' : 'na'
  return null // bidder is best-effort; absence is not fatal
}

/** "N nominations until your turn" → viewer countdown (heartbeat-only data). */
export function resolveTurn(root, health) {
  const texts = spansIn(root).map(txt)
  for (const t of texts) {
    const m = t.match(TURN_RE)
    if (m) {
      health.turn = 'primary'
      return parseInt(m[1], 10)
    }
  }
  if (texts.some((t) => YOUR_TURN_NOW_RE.test(t))) {
    health.turn = 'primary'
    return 0 // your turn now
  }
  health.turn = 'na'
  return null
}

// ---------------------------------------------------------------------------
// Top-level resolver
// ---------------------------------------------------------------------------
/**
 * Resolve the full auction board state from the React root. `warn(field, level)`
 * is the loud-degradation hook (the content script throttles + feeds telemetry).
 */
export function resolveAuctionState(root, { warn = () => {} } = {}) {
  const health = freshHealth()
  const { teams, yourTeamId } = resolveTeams(root, health, warn)
  const card = resolveNominationCard(root)
  const playerId = resolvePlayerId(card)
  const playerName = resolvePlayerName(card, playerId, health, warn)
  const currentBid = resolveBid(card, health, warn)
  const currentBidder = resolveBidder(card, teams, health, warn)
  const clock = card ? resolveClock(card, root, health, warn) : ((health.clock = 'na'), null)
  const picksUntilYourTurn = resolveTurn(root, health)
  return {
    playerName,
    playerId,
    posTeam: null, // TODO(capture: nomination.html): extract POS·TEAM if present
    currentBid,
    currentBidder,
    clock,
    teams,
    yourTeamId,
    picksUntilYourTurn,
    health,
  }
}

/** Clock within the nomination card (primary) → root → _ys_ fallback. */
export function resolveClock(card, root, health, warn) {
  const inCard = card ? spansIn(card).find((s) => CLOCK_RE.test(txt(s)) && notInDialog(s)) : null
  const prim = inCard || findLiveTimer(root)
  if (prim) {
    health.clock = 'primary'
    return txt(prim)
  }
  const fb = (card || root).querySelector('span._ys_12k0qlu')
  if (fb && CLOCK_RE.test(txt(fb)) && notInDialog(fb)) {
    health.clock = 'fallback'
    warn('clock', 'hash')
    return txt(fb)
  }
  health.clock = 'missing'
  warn('clock', 'missing')
  return null
}

// ---------------------------------------------------------------------------
// Event diffing — emit ON CHANGE; nomination 1-tick debounced; draft_pick is
// team-delta driven (Amendment 4); bid_update carries current_bidder
// (Amendment 5); heartbeat carries selector_health + countdown (Answer 3).
// ---------------------------------------------------------------------------
export function initAuctionMemory() {
  return {
    lastPlayerKey: null,
    pendingPlayerKey: null,
    lastPlayerName: null,
    lastBid: null,
    lastBidder: null,
    lastClock: null,
    nominationTeams: {}, // snapshot at nomination time → baseline for sale delta
    prevTeams: {}, // last seen teams → teams_update change detection
    soldKeys: [], // dedupe draft_pick per player key
    lastHealth: null,
    lastPicksUntil: null,
  }
}

export function detectAuctionEvents(prev, curr) {
  const events = []
  const next = { ...prev, soldKeys: prev.soldKeys.slice() }
  const key = curr.playerId || curr.playerName // nomination identity

  // SALE (delta-driven, dedupe) — attribute to the LAST-known nomination so a
  // back-to-back nomination on the same tick still records the prior sale.
  if (prev.lastPlayerKey && !next.soldKeys.includes(prev.lastPlayerKey)) {
    const winner = detectWinner(curr.teams, prev.nominationTeams || {}, prev.lastBid)
    if (winner) {
      events.push({
        type: 'draft_pick',
        platform: 'yahoo',
        payload: {
          player_name: prev.lastPlayerName,
          player_id: prev.lastPlayerKey,
          final_price: prev.lastBid,
          winner,
          teams_snapshot: curr.teams,
        },
      })
      next.soldKeys.push(prev.lastPlayerKey)
      next.lastPlayerKey = null // cleared so the next nomination can stage
      next.pendingPlayerKey = null
    }
  }

  // NOMINATION (1-tick confirmation debounce — Amendment 1).
  if (curr.playerName && key !== next.lastPlayerKey) {
    if (key === prev.pendingPlayerKey) {
      events.push({
        type: 'nomination',
        platform: 'yahoo',
        payload: {
          player_name: curr.playerName,
          player_id: curr.playerId,
          pos_team: curr.posTeam,
          opening_bid: curr.currentBid,
          clock: curr.clock,
        },
      })
      next.lastPlayerKey = key
      next.lastPlayerName = curr.playerName
      next.lastBid = curr.currentBid
      next.lastBidder = curr.currentBidder
      next.lastClock = curr.clock
      next.nominationTeams = { ...curr.teams }
      next.pendingPlayerKey = null
    } else {
      next.pendingPlayerKey = key // stage; confirm next tick
    }
  } else if (curr.playerName && key === next.lastPlayerKey) {
    next.pendingPlayerKey = null
  }

  // BID UPDATE (same player; amount OR high-bidder changed — Amendment 5).
  if (
    curr.playerName &&
    key === next.lastPlayerKey &&
    (curr.currentBid !== next.lastBid || curr.currentBidder !== next.lastBidder)
  ) {
    events.push({
      type: 'bid_update',
      platform: 'yahoo',
      payload: {
        player_name: curr.playerName,
        current_bid: curr.currentBid,
        current_bidder: curr.currentBidder,
        clock: curr.clock,
      },
    })
    next.lastBid = curr.currentBid
    next.lastBidder = curr.currentBidder
  }

  // CLOCK (same player; 5s cadence to keep the UI ticking without spam).
  if (curr.playerName && curr.clock !== next.lastClock) {
    next.lastClock = curr.clock
    const secs = secondsFromClock(curr.clock)
    if (secs !== null && secs % 5 === 0) {
      events.push({
        type: 'clock',
        platform: 'yahoo',
        payload: { player_name: curr.playerName, clock: curr.clock, seconds_remaining: secs },
      })
    }
  }

  // TEAMS UPDATE (budgets/rosters changed) — carries data-ids + your_team_id.
  if (JSON.stringify(curr.teams) !== JSON.stringify(prev.prevTeams)) {
    events.push({
      type: 'teams_update',
      platform: 'yahoo',
      payload: { teams: curr.teams, your_team_id: curr.yourTeamId },
    })
    next.prevTeams = { ...curr.teams }
  }

  // HEARTBEAT — selector_health + viewer countdown. Emitted on health OR
  // countdown change (NOT every tick). NOTE: confirm whether you want strictly
  // health-change-only; countdown-change is included so "N until your turn"
  // stays fresh as your turn nears (Answer 3).
  const healthStr = JSON.stringify(curr.health)
  if (healthStr !== prev.lastHealth || curr.picksUntilYourTurn !== prev.lastPicksUntil) {
    events.push({
      type: 'heartbeat',
      platform: 'yahoo',
      payload: {
        selector_health: curr.health,
        picks_until_your_turn: curr.picksUntilYourTurn,
      },
    })
    next.lastHealth = healthStr
    next.lastPicksUntil = curr.picksUntilYourTurn
  }

  return { events, next }
}
