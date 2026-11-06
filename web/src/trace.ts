import type { JobStage } from './contract'
import type { TraceEvent } from './types'

/** Display phases of the broker trace (shared/api-contract.md "Agent trace"), in reading order. */
export type TracePhase = 'observe' | 'candidates' | 'tools' | 'judge' | 'answer'
export const PHASES: TracePhase[] = ['observe', 'candidates', 'tools', 'judge', 'answer']

const PHASE_OF: Record<string, TracePhase> = {
  request_accepted: 'observe', job_claimed: 'observe', observing: 'observe',
  matching: 'candidates', landmark_candidates: 'candidates',
  catalog_search: 'tools', osm_live_search: 'tools', wikipedia: 'tools',
  grounding_check: 'judge',
  writing: 'answer', result_saved: 'answer', worker_failed: 'answer', trace_truncated: 'answer',
}
export function phaseOf(event: TraceEvent): TracePhase {
  return PHASE_OF[event.name] ?? (event.kind === 'tool' ? 'tools' : event.kind === 'check' ? 'judge' : 'observe')
}

/** A tool call or grounding check the broker rejected (worker failure and truncation are not blocks). */
export const isBlocked = (event: TraceEvent) => !event.ok && (event.kind === 'tool' || event.kind === 'check')

export type TimedEvent = TraceEvent & { ms: number }
export type PhaseRow = { phase: TracePhase; events: TimedEvent[]; ms: number; blocked: number }

/**
 * Groups events by phase. Each event lasts until the next event in time, so phase durations
 * partition the broker-observed total (the last event, or the running one, gets `now - t_ms` while live).
 */
export function phaseRows(events: TraceEvent[], liveMs: number | null = null): PhaseRow[] {
  const ordered = events.map((event, index) => ({ event, index })).sort((a, b) => a.event.t_ms - b.event.t_ms || a.index - b.index).map(item => item.event)
  const timed: TimedEvent[] = ordered.map((event, index) => {
    const next = ordered[index + 1]
    const ms = next ? next.t_ms - event.t_ms : liveMs !== null ? Math.max(0, liveMs - event.t_ms) : 0
    return { ...event, ms }
  })
  return PHASES.map(phase => {
    const rows = timed.filter(event => phaseOf(event) === phase)
    return { phase, events: rows, ms: rows.reduce((sum, event) => sum + event.ms, 0), blocked: rows.filter(isBlocked).length }
  })
}

/** Furthest phase reached: from the trace when present, otherwise from the worker-reported stage. */
export function reachedPhase(events: TraceEvent[], stage: JobStage | null): number {
  const fromTrace = events.reduce((max, event) => Math.max(max, PHASES.indexOf(phaseOf(event))), -1)
  const fromStage = stage === 'observing' ? 0 : stage === 'matching' ? 1 : stage === 'writing' ? 4 : -1
  return Math.max(fromTrace, fromStage)
}

export const totalMs = (events: TraceEvent[]) => events.reduce((max, event) => Math.max(max, event.t_ms), 0)
export const blockedCount = (events: TraceEvent[]) => events.filter(isBlocked).length
export const formatSeconds = (ms: number) => (ms / 1000).toFixed(ms < 10000 ? 1 : 0) + 's'
