import { describe, expect, it } from 'vitest'
import { freshness } from './freshness'

describe('freshness', () => {
  const at = '2026-11-06T09:00:00Z'
  it('grades by months before the answer', () => {
    expect(freshness('2026-09-15', at)).toEqual({ level: 'fresh', months: 1 })
    expect(freshness('2025-11', at)).toEqual({ level: 'aging', months: 12 })
    expect(freshness('2019', at)).toEqual({ level: 'stale', months: 94 })
  })
  it('is unknown without a readable date', () => {
    expect(freshness(null, at).level).toBe('unknown')
    expect(freshness('n/a', at).level).toBe('unknown')
  })
})
