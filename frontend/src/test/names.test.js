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

  // --- generational suffixes (BUG 4) ---

  it('strips Jr suffix', () => {
    expect(normalizeName('Michael Pittman Jr.')).toBe('michael pittman')
    expect(normalizeName('Michael Pittman Jr')).toBe('michael pittman')
  })

  it('strips Sr suffix', () => {
    expect(normalizeName('Garrett Wilson Sr.')).toBe('garrett wilson')
  })

  it('strips III suffix', () => {
    expect(normalizeName('Kenneth Walker III')).toBe('kenneth walker')
  })

  it('strips IV suffix', () => {
    expect(normalizeName('Some Player IV')).toBe('some player')
  })

  it('James Cook III -> james cook', () => {
    expect(normalizeName('James Cook III')).toBe('james cook')
    // The DOM may drop the suffix entirely — both must collapse to the same key.
    expect(normalizeName('James Cook III')).toBe(normalizeName('James Cook'))
  })

  it('Travis Etienne Jr -> travis etienne', () => {
    expect(normalizeName('Travis Etienne Jr.')).toBe('travis etienne')
    expect(normalizeName('Travis Etienne Jr.')).toBe(normalizeName('Travis Etienne'))
  })

  it("strips apostrophe in Le'Veon Bell", () => {
    expect(normalizeName("Le'Veon Bell")).toBe('leveon bell')
  })
})
