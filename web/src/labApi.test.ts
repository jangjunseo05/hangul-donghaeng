import { describe, expect, it } from 'vitest'
import { probeVerdict } from './labApi'
import type { ProbeAttempt, ProbeResult } from './types'

const attempt = (id: ProbeAttempt['id'], observed: ProbeAttempt['observed'], broker_received: number | null = null): ProbeAttempt => ({ id, expected: 'denied', observed, detail: null, broker_received })
const run = (attempts: ProbeAttempt[], run_context = 'openshell'): ProbeResult => ({ run_context, finished_at: '2026-11-06T09:00:00Z', attempts })
const allDenied = [attempt('read_outside_allowlist', 'denied'), attempt('write_code_dir', 'denied'), attempt('egress_unlisted_host', 'denied'), attempt('broker_unlisted_path', 'denied', 0)]

describe('probeVerdict', () => {
  it('is blocked only when all four are denied and the broker saw nothing', () => {
    expect(probeVerdict(run(allDenied))).toBe('blocked')
  })
  it('reports a local (unsandboxed) run plainly when anything was allowed, whatever the label says', () => {
    const local = [attempt('read_outside_allowlist', 'denied'), attempt('write_code_dir', 'allowed'), attempt('egress_unlisted_host', 'error'), attempt('broker_unlisted_path', 'allowed', 1)]
    expect(probeVerdict(run(local, 'openshell'))).toBe('not_sandboxed')
  })
  it('cannot judge with an error, a missing attempt or no broker count', () => {
    expect(probeVerdict(run([...allDenied.slice(0, 2), attempt('egress_unlisted_host', 'error'), allDenied[3]]))).toBe('cannot_judge')
    expect(probeVerdict(run(allDenied.slice(0, 3)))).toBe('cannot_judge')
    expect(probeVerdict(run([...allDenied.slice(0, 3), attempt('broker_unlisted_path', 'denied', null)]))).toBe('cannot_judge')
  })
  it('flags a mismatch when the worker saw denials but the broker received the canary', () => {
    expect(probeVerdict(run([...allDenied.slice(0, 3), attempt('broker_unlisted_path', 'denied', 2)]))).toBe('mismatch')
    expect(probeVerdict(run(allDenied), [{ t_ms: 10, kind: 'broker', name: 'canary_received', ok: false, detail: null }])).toBe('mismatch')
  })
})
