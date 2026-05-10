import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ValueComparisonBar from '../components/shared/ValueComparisonBar'

describe('ValueComparisonBar', () => {
  it('shows "Overvalued" when market > system by 5+', () => {
    render(<ValueComparisonBar systemValue={14} marketValue={31} />)
    expect(screen.getByText('Overvalued')).toBeInTheDocument()
  })

  it('shows "Undervalued" when system > market by 5+', () => {
    render(<ValueComparisonBar systemValue={45} marketValue={30} />)
    expect(screen.getByText('Undervalued')).toBeInTheDocument()
  })

  it('shows "Aligned" when within $3', () => {
    render(<ValueComparisonBar systemValue={30} marketValue={32} />)
    expect(screen.getByText('Aligned')).toBeInTheDocument()
  })

  it('returns null when values are missing', () => {
    const { container } = render(<ValueComparisonBar systemValue={null} marketValue={30} />)
    expect(container.innerHTML).toBe('')
  })
})
