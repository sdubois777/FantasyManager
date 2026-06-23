import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

import {
  auctionGateDecision,
  isNameShape,
} from '../src/content_scripts/yahoo_auction_resolve.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const FIX = join(__dirname, 'fixtures', 'auction')

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
// Fixture-backed resolver tests — SKIPPED stubs until REAL captures land.
//
// Drop captured Yahoo outerHTML into test/fixtures/auction/<state>.html and
// un-skip. Do NOT hand-mock the markup — the regression net must be real Yahoo
// DOM, re-runnable after their next deploy. linkedom (dev-dep) parses fixtures:
//   import { parseHTML } from 'linkedom'
//   const { document } = parseHTML(loadFixture('lobby.html'))
// Field tuning (name/bid/clock/bidder) stays HELD until a mid-nomination capture.
// ---------------------------------------------------------------------------
// eslint-disable-next-line no-unused-vars
function loadFixture(name) {
  return readFileSync(join(FIX, name), 'utf-8')
}

test(
  'lobby: gate ACTIVE (root + .ys-team), no nomination; teams + your-team self-id (You/data-id)',
  { skip: 'awaiting test/fixtures/auction/lobby.html' },
  () => {}
)
test(
  'nomination: name via ys-player[data-id] (primary), current bid, clock, current_bidder',
  { skip: 'awaiting test/fixtures/auction/nomination.html' },
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
  'degradation: mutated _ys_ hashes fall back via text/structure and report fallback/missing (LOUD, not silent)',
  { skip: 'awaiting test/fixtures/auction/nomination.html (+ a hash-mutated variant)' },
  () => {}
)
