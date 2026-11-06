import { ApiError, getJson, pause } from './api'
import type { Language, ProbeJob, ProbeResult, ReviewInputs, ReviewJob, ReviewResult, TraceEvent } from './types'

// F2 source review and F3 sandbox probe (shared/api-contract.md "Source review mode", "Sandbox probe").
const post = <T>(path: string, body: unknown, signal?: AbortSignal) => fetch(path, { method: 'POST', credentials: 'include', signal, headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body) })
  .then(async response => {
    let payload: unknown = null
    try { payload = await response.json() } catch { throw new ApiError('INVALID_RESPONSE', response.status) }
    if (!response.ok) throw new ApiError(payload && typeof payload === 'object' && 'error_code' in payload && typeof payload.error_code === 'string' ? payload.error_code : 'SERVER_ERROR', response.status)
    return payload as T
  }, error => { if (signal?.aborted) throw error; throw new ApiError('OFFLINE') })

export const labApi = {
  reviewInputs: (signal?: AbortSignal) => getJson<ReviewInputs>('/api/reviews/inputs', signal),
  submitReview: (body: { session_id: string; question: string; condition: string | null; response_language: Language }, signal?: AbortSignal) => post<{ request_id: string; poll_url: string }>('/api/reviews', body, signal),
  submitProbe: (session_id: string, signal?: AbortSignal) => post<{ request_id: string; poll_url: string }>('/api/sandbox-probe', { session_id }, signal),
}

type AnyJob = ReviewJob | ProbeJob
/** Polls a review/probe job until it is terminal, reporting status and trace on every poll. */
export async function pollJob<J extends AnyJob>(path: string, id: string, signal: AbortSignal, onUpdate: (job: J) => void, valid: (result: NonNullable<J['result']>) => boolean, timeoutMs = 90000): Promise<NonNullable<J['result']>> {
  const deadline = Date.now() + timeoutMs
  while (!signal.aborted && Date.now() < deadline) {
    const job = await getJson<J>(path + encodeURIComponent(id), signal)
    if (job.request_id !== id || !['queued', 'running', 'completed', 'failed', 'superseded'].includes(job.status)) throw new ApiError('INVALID_RESPONSE')
    onUpdate(job)
    if (job.status === 'superseded') throw new ApiError('SUPERSEDED')
    if (job.status === 'failed') throw new ApiError(job.error_code || 'JOB_FAILED')
    if (job.status === 'completed') { const result = job.result as NonNullable<J['result']> | null; if (!result || !valid(result)) throw new ApiError('INVALID_RESPONSE'); return result }
    await pause(900, signal)
  }
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
  throw new ApiError('TIMEOUT')
}

export const PROBE_IDS = ['read_outside_allowlist', 'write_code_dir', 'egress_unlisted_host', 'broker_unlisted_path'] as const
export type ProbeVerdict = 'blocked' | 'not_sandboxed' | 'cannot_judge' | 'mismatch'
/**
 * Contract interpretation, in order: any `allowed` → not sandboxed (shown plainly); any `error` or a missing
 * attempt → cannot judge; all denied but the broker saw the canary → evidence mismatch; otherwise blocked.
 * `run_context` is a label only and never decides the verdict.
 */
export function probeVerdict(result: ProbeResult, trace: TraceEvent[] = []): ProbeVerdict {
  const attempts = PROBE_IDS.map(id => result.attempts.find(attempt => attempt.id === id))
  if (attempts.some(attempt => attempt?.observed === 'allowed')) return 'not_sandboxed'
  if (attempts.some(attempt => !attempt || attempt.observed !== 'denied')) return 'cannot_judge'
  const canary = attempts[3]!.broker_received
  if (canary === null) return 'cannot_judge'
  if (canary > 0 || trace.some(event => event.name === 'canary_received')) return 'mismatch'
  return 'blocked'
}

export const isProbeResult = (value: ProbeResult) => typeof value.run_context === 'string' && Array.isArray(value.attempts) && value.attempts.every(attempt => attempt && typeof attempt.id === 'string' && typeof attempt.observed === 'string')
export const isReviewResult = (value: ReviewResult) => typeof value.input_label === 'string' && typeof value.verified_input === 'boolean' && [value.sources, value.claims, value.conflicts, value.unknowns].every(Array.isArray)
  && value.sources.every(source => source && typeof source.path === 'string' && typeof source.sha256 === 'string') && value.claims.every(claim => Array.isArray(claim.quotes) && Array.isArray(claim.source_ids)) && value.conflicts.every(conflict => Array.isArray(conflict.quotes) && Array.isArray(conflict.source_ids))
