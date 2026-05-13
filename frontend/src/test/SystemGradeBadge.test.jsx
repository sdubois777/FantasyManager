import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import SystemGradeBadge from '../components/shared/SystemGradeBadge'

describe('SystemGradeBadge', () => {
  it('renders A+ grade with green coloring', () => {
    const { container } = render(<SystemGradeBadge grade="A+" />)
    const badge = container.querySelector('span')
    expect(badge).toHaveTextContent('A+')
    expect(badge.className).toContain('text-emerald-400')
  })

  it('renders F grade with red coloring', () => {
    const { container } = render(<SystemGradeBadge grade="F" />)
    const badge = container.querySelector('span')
    expect(badge).toHaveTextContent('F')
    expect(badge.className).toContain('text-red-400')
  })

  it('renders B grade with teal coloring', () => {
    const { container } = render(<SystemGradeBadge grade="B" />)
    const badge = container.querySelector('span')
    expect(badge.className).toContain('text-teal-400')
  })

  it('returns null when no grade provided', () => {
    const { container } = render(<SystemGradeBadge grade={null} />)
    expect(container.innerHTML).toBe('')
  })
})
