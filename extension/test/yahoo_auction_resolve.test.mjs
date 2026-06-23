import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { parseHTML } from 'linkedom'

import {
  auctionGateDecision,
  isNameShape,
  resolveAuctionState,
  shouldAuctionActivate,
} from '../src/content_scripts/yahoo_auction_resolve.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FIX = join(__dirname, 'fixtures', 'auction')

// Parse a captured Yahoo outerHTML fixture into a document (+ React root).
function docFor(name) {
  const { document } = parseHTML(readFileSync(join(FIX, name), 'utf-8'))
  return document
}
function rootFor(name) {
  return docFor(name).querySelector('#main-0-DraftClientBootstrap-Proxy')
}

// ---------------------------------------------------------------------------
// Activation gate — pure decision (no DOM). Root + live signal + cross-poller
// veto + draft-complete negative override.
// ---------------------------------------------------------------------------
const GATE = {
  hasRoot: true,
  hasLiveTimer: false,
  teamCardCount: 0,
  draftComplete: false,
  snakeMarkers: false,
}

test('gate: ACTIVE with root + a live timer', () => {
  assert.equal(auctionGateDecision({ ...GATE, hasLiveTimer: true }), true)
})

test('gate: ACTIVE with root + >=1 .ys-team card (lobby, no timer yet)', () => {
  assert.equal(auctionGateDecision({ ...GATE, teamCardCount: 12 }), true)
})

test('gate: INERT without the React root (even with a timer + cards)', () => {
  assert.equal(
    auctionGateDecision({ ...GATE, hasRoot: false, hasLiveTimer: true, teamCardCount: 12 }),
    false
  )
})

test('gate: INERT when draft-complete (negative override)', () => {
  assert.equal(
    auctionGateDecision({ ...GATE, teamCardCount: 12, draftComplete: true }),
    false
  )
})

test('gate: INERT when snake markers present (cross-poller veto)', () => {
  assert.equal(
    auctionGateDecision({ ...GATE, hasLiveTimer: true, teamCardCount: 12, snakeMarkers: true }),
    false
  )
})

test('gate: INERT with the root but no live signal (root only)', () => {
  assert.equal(auctionGateDecision(GATE), false)
})

// ---------------------------------------------------------------------------
// Name-shape gate (deterministic, no DOM) — keeps flicker/garbage from firing a
// nomination (which on-change diffing would otherwise spam as new nominations).
// ---------------------------------------------------------------------------
test('isNameShape: accepts a >=2-token capitalized name', () => {
  assert.equal(isNameShape('Bijan Robinson'), true)
  assert.equal(isNameShape('A. Jeanty'), true)
})

test('isNameShape: rejects money / number / roster / clock / label / single token', () => {
  for (const t of ['$45', '12', '1/15', '00:19', 'You', 'Current Bid', 'Saquon', ''])
    assert.equal(isNameShape(t), false, `should reject: ${JSON.stringify(t)}`)
})

// ---------------------------------------------------------------------------
// Fixture-backed resolver tests — REAL captured Yahoo outerHTML (the regression
// net; re-runnable after each Yahoo deploy). Do NOT hand-mock the markup.
// Remaining states are SKIPPED until those captures land.
// ---------------------------------------------------------------------------

// nomination.html — a real mid-nomination capture: T. McMillan (id 41793) on the
// block, $1 bid by Team 3, clock 00:19, 4 nominations until our turn, our team
// (data-id 4) is "You" with $200 / 0-15. All fields resolve off stable anchors
// (ys-player[data-id] name, structural offer-panel bid/bidder, .ys-team teams).
test('nomination: resolves name/bid/clock/bidder/teams off stable anchors', () => {
  const doc = docFor('nomination.html')
  const root = doc.querySelector('#main-0-DraftClientBootstrap-Proxy')
  const warns = []
  const st = resolveAuctionState(root, { warn: (f, l) => warns.push(`${f}:${l}`) })

  // gate active
  assert.equal(shouldAuctionActivate(doc), true)
  // nominee — id-anchored (Amendment B)
  assert.equal(st.playerName, 'T. McMillan')
  assert.equal(st.playerId, '41793')
  assert.equal(st.posTeam, 'WR · Car')
  // bid + high bidder (structural, cross-checked to the stable team data-id)
  assert.equal(st.currentBid, 1)
  assert.equal(st.currentBidder, 'Team 3')
  assert.equal(st.currentBidderTeamId, '3')
  // clock
  assert.equal(st.clock, '00:19')
  // viewer countdown (full-match anchor, not the catch-all blob's "194")
  assert.equal(st.picksUntilYourTurn, 4)
  // every field off its PRIMARY anchor — no _ys_ fallback, no warns
  assert.deepEqual(st.health, {
    clock: 'primary', name: 'primary', bid: 'primary',
    bidder: 'primary', teams: 'primary', turn: 'primary',
  })
  assert.deepEqual(warns, [])
})

test('nomination: teams + your-team self-id (You span + data-id, NOT a degradation)', () => {
  const root = rootFor('nomination.html')
  const st = resolveAuctionState(root, { warn: () => {} })
  assert.equal(Object.keys(st.teams).length, 12)
  assert.equal(st.yourTeamId, '4') // the "You" card
  // your own card: keyed "You", full budget, 0/15, data-id 4
  assert.deepEqual(st.teams['You'], {
    budget: 200, slotsUsed: 0, totalSlots: 15, dataId: '4',
  })
  // an opponent card carries budget/roster/data-id
  assert.equal(st.teams['Team 3'].dataId, '3')
})

test(
  'lobby: gate ACTIVE (root + .ys-team), NO nominee; teams + self-id',
  { skip: 'awaiting a TRUE empty-lobby capture (the prior file was mid-nomination)' },
  () => {}
)
test(
  'your-turn: picks_until_your_turn === 0 (your-turn-now wording)',
  { skip: 'awaiting test/fixtures/auction/your-turn.html' },
  () => {}
)
test(
  'post-pick: draft_pick via team-delta, attributed to the last-known nomination',
  { skip: 'awaiting test/fixtures/auction/post-pick.html' },
  () => {}
)
test(
  'draft-complete: gate INERT via the negative-override marker',
  { skip: 'awaiting test/fixtures/auction/draft-complete.html (if it shares the root)' },
  () => {}
)
test(
  'degradation: breaking a STRUCTURE/TEXT anchor falls to _ys_ + reports fallback/missing (LOUD)',
  // NOTE: the primary anchors are text/structure/kebab — NOT _ys_ hashes — so
  // mutating the hashes alone does NOT degrade (that's the desired property,
  // verified by nomination.html resolving all-primary with the hashes present).
  // This test must instead break a STRUCTURAL anchor (e.g. strip .ys-team or the
  // nominee's "Proj $" text) and assert the _ys_ fallback fires loudly. Holding
  // until we lock the exact fallback selectors against a 2nd-deploy capture.
  { skip: 'design against a real post-deploy capture (hash-mutation alone is a no-op by design)' },
  () => {}
)
