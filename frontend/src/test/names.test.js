import { describe, it, expect } from 'vitest'
import { normalizeName } from '../utils/names'

describe('normalizeName', () => {
  it('strips hyphens', () => {
    // Hyphen becomes a space so a hyphenated draftboard name matches the
    // space-separated DOM name — the canonical Amon-Ra case.
    expect(normalizeName('Amon-Ra St. Brown')).toBe(normalizeName('Amon Ra St. Brown'))
    expect(normalizeName('Amon-Ra St. Brown')).toBe('amon ra st brown')
  })

  it('strips apostrophes', () => {
    expect(normalizeName("Ja'Marr Chase")).toBe('jamarr chase')
  })

  it('strips periods', () => {
    expect(normalizeName('A.J. Brown')).toBe('aj brown')
  })

  it('case insensitive', () => {
    expect(normalizeName('JOSH allen')).toBe('josh allen')
  })

  it('trims whitespace', () => {
    expect(normalizeName('  Josh   Allen  ')).toBe('josh allen')
  })

  it('handles null/undefined safely', () => {
    expect(normalizeName(null)).toBe('')
    expect(normalizeName(undefined)).toBe('')
  })
})
