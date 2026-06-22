/**
 * SnakePanel status line — derives from continuous snake state (current pick +
 * countdown the extension pushes), with graceful fallbacks.
 *
 * The snake-reversal math now lives in the extension/Yahoo DOM (authoritative);
 * these tests assert the panel RENDERS the supplied countdown correctly at the
 * round-boundary edge cases — back-to-back (1 pick) and the long wait across a
 * reversal (slot 1 in a 12-team league waits 2N-1 = 23) — and that "Waiting for
 * the draft..." appears ONLY when there's genuinely no current pick.
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { useDraftStore } from '../stores/draft'
import SnakePanel from '../components/draft/SnakePanel'

function setSnake(state) {
  useDraftStore.setState({
    isYourTurn: false,
    currentRound: null,
    currentPick: null,
    picksUntilYourTurn: null,
    ...state,
  })
}

beforeEach(() => setSnake({}))

describe('SnakePanel status line', () => {
  it('shows "Waiting for the draft..." ONLY when there is no current pick (pre-draft)', () => {
    setSnake({ currentPick: null, picksUntilYourTurn: null })
    render(<SnakePanel />)
    expect(screen.getByText('Waiting for the draft...')).toBeInTheDocument()
  })

  it('shows "Draft in progress" when underway but no countdown (graceful, never "waiting")', () => {
    setSnake({ currentPick: 84, currentRound: 7, picksUntilYourTurn: null })
    render(<SnakePanel />)
    expect(screen.getByText('Draft in progress')).toBeInTheDocument()
    expect(screen.queryByText('Waiting for the draft...')).not.toBeInTheDocument()
    expect(screen.getByText('Round 7, Pick 84')).toBeInTheDocument()
  })

  it('renders a continuous countdown mid-draft', () => {
    setSnake({ currentPick: 84, currentRound: 7, picksUntilYourTurn: 9 })
    render(<SnakePanel />)
    expect(screen.getByText("You're up in 9 picks")).toBeInTheDocument()
    expect(screen.queryByText('Waiting for the draft...')).not.toBeInTheDocument()
  })

  it('renders the back-to-back boundary correctly (1 pick, singular)', () => {
    // slot N picks at N then N+1 across the round reversal → up in 1.
    setSnake({ currentPick: 13, currentRound: 2, picksUntilYourTurn: 1 })
    render(<SnakePanel />)
    expect(screen.getByText("You're up in 1 pick")).toBeInTheDocument()
  })

  it('renders the long wait across a reversal (slot 1 waits 2N-1 = 23 in a 12-team)', () => {
    setSnake({ currentPick: 2, currentRound: 1, picksUntilYourTurn: 23 })
    render(<SnakePanel />)
    expect(screen.getByText("You're up in 23 picks")).toBeInTheDocument()
  })

  it('shows YOUR TURN when on the clock', () => {
    setSnake({ isYourTurn: true, currentPick: 93, currentRound: 8, picksUntilYourTurn: 0 })
    render(<SnakePanel />)
    expect(screen.getByText('YOUR TURN')).toBeInTheDocument()
  })
})
