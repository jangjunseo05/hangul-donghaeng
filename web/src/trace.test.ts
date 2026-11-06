import { describe, expect, it } from 'vitest'
import { blockedCount, phaseRows, reachedPhase } from './trace'
import type { TraceEvent } from './types'

const ev = (t_ms: number, kind: TraceEvent['kind'], name: string, ok = true, detail: string | null = null): TraceEvent => ({ t_ms, kind, name, ok, detail })
const trace: TraceEvent[] = [
  ev(0, 'broker', 'request_accepted'),
  ev(300, 'sandbox', 'job_claimed'),
  ev(400, 'stage', 'observing'),
  ev(5400, 'stage', 'matching'),
  ev(5600, 'tool', 'osm_live_search', true, '3 results'),
  ev(6100, 'tool', 'wikipedia', false, 'SEARCH_LIMIT'),
  ev(6200, 'stage', 'writing'),
  ev(12200, 'check', 'grounding_check', true, '2 sources · 1 conflicts'),
  ev(12500, 'broker', 'result_saved'),
]

describe('phaseRows', () => {
  it('splits the broker total across phases by time to the next event', () => {
    const rows = phaseRows(trace)
    expect(rows.map(row => [row.phase, row.ms])).toEqual([['observe', 5400], ['candidates', 200], ['tools', 600], ['judge', 300], ['answer', 6000]])
    expect(rows.reduce((sum, row) => sum + row.ms, 0)).toBe(12500)
  })
  it('counts rejected calls per phase and orders out-of-order events by time', () => {
    const rows = phaseRows([trace[1], trace[0], trace[5]])
    expect(rows[0].events.map(event => event.name)).toEqual(['request_accepted', 'job_claimed'])
    expect(rows[2].blocked).toBe(1)
    expect(blockedCount(trace)).toBe(1)
  })
  it('gives the last event the live elapsed time while running', () => {
    expect(phaseRows(trace.slice(0, 3), 2400)[0].ms).toBe(2400)
  })
})

describe('reachedPhase', () => {
  it('uses the trace, falling back to the worker stage', () => {
    expect(reachedPhase(trace.slice(0, 5), null)).toBe(2)
    expect(reachedPhase([], 'matching')).toBe(1)
    expect(reachedPhase([], null)).toBe(-1)
  })
})
