import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import FlagBadge from '../components/shared/FlagBadge'

describe('FlagBadge', () => {
  it('renders DISPLACED with red styling', () => {
    const { container } = render(<FlagBadge flagType="DISPLACED" />)
    const badge = container.querySelector('span')
    expect(badge).toHaveTextContent('Displaced')
    expect(badge.className).toContain('text-red-400')
  })

  it('renders BENEFICIARY with green styling', () => {
    const { container } = render(<FlagBadge flagType="BENEFICIARY" />)
    const badge = container.querySelector('span')
    expect(badge).toHaveTextContent('Beneficiary')
    expect(badge.className).toContain('text-emerald-400')
  })

  it('renders BREAKOUT with yellow styling', () => {
    const { container } = render(<FlagBadge flagType="BREAKOUT" />)
    const badge = container.querySelector('span')
    expect(badge).toHaveTextContent('Breakout')
    expect(badge.className).toContain('text-yellow-400')
  })

  it('renders WORKLOAD_CLIFF with orange styling', () => {
    const { container } = render(<FlagBadge flagType="WORKLOAD_CLIFF" />)
    const badge = container.querySelector('span')
    expect(badge).toHaveTextContent('Workload Cliff')
    expect(badge.className).toContain('text-orange-400')
  })

  it('renders COLLEGE_TRUST with indigo styling', () => {
    const { container } = render(<FlagBadge flagType="COLLEGE_TRUST" />)
    const badge = container.querySelector('span')
    expect(badge).toHaveTextContent('College Trust')
    expect(badge.className).toContain('text-indigo-400')
  })

  it('falls back to gray for unknown flag types', () => {
    const { container } = render(<FlagBadge flagType="UNKNOWN_FLAG" />)
    const badge = container.querySelector('span')
    expect(badge).toHaveTextContent('UNKNOWN_FLAG')
    expect(badge.className).toContain('text-slate-400')
  })

  it('renders compact size when compact prop is true', () => {
    const { container } = render(<FlagBadge flagType="DISPLACED" compact />)
    const badge = container.querySelector('span')
    expect(badge.className).toContain('text-[10px]')
  })
})
