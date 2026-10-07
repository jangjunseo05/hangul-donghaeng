import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, safeSourceUrl, waitForResult } from './api'
import fixture from '../tests/fixtures/guide-result.json'
const respond = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
beforeEach(() => { vi.stubGlobal('window', { setTimeout, clearTimeout }); vi.stubGlobal('fetch', vi.fn()) })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
describe('cookie API and stale-result boundaries', () => {
  it('sends same-origin credentials and JSON to create the session', async () => {
    vi.mocked(fetch).mockResolvedValue(respond({ session_id: 'test-session' }))
    await expect(api.session()).resolves.toEqual({ session_id: 'test-session' })
    expect(fetch).toHaveBeenCalledWith('/api/sessions', expect.objectContaining({ credentials: 'include', method: 'POST', body: '{}' }))
  })
  it('rejects a completed result for a different request', async () => {
    vi.mocked(fetch).mockResolvedValue(respond({ request_id: fixture.request_id, status: 'completed', result: { ...fixture, request_id: 'old-request' }, error_code: null }))
    await expect(waitForResult(fixture.request_id, fixture.session_id, new AbortController().signal, () => {})).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
  it('rejects a completed result from a different session', async () => {
    vi.mocked(fetch).mockResolvedValue(respond({ request_id: fixture.request_id, status: 'completed', result: { ...fixture, session_id: 'other-session' }, error_code: null }))
    await expect(waitForResult(fixture.request_id, fixture.session_id, new AbortController().signal, () => {})).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
  it('accepts the matching result and encodes the request ID into a fixed local route', async () => {
    vi.mocked(fetch).mockResolvedValue(respond({ request_id: fixture.request_id, status: 'completed', result: fixture, error_code: null }))
    await expect(waitForResult(fixture.request_id, fixture.session_id, new AbortController().signal, () => {})).resolves.toMatchObject({ request_id: fixture.request_id })
    expect(fetch).toHaveBeenCalledWith('/api/requests/' + fixture.request_id, expect.anything())
  })
  it('stops polling an obsolete question when aborted', async () => {
    const controller = new AbortController()
    vi.mocked(fetch).mockResolvedValue(respond({ request_id: 'pending', status: 'running', result: null, error_code: null }))
    const pending = waitForResult('pending', 'session', controller.signal, () => controller.abort())
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('preserves authentication status without reflecting server detail', async () => {
    vi.mocked(fetch).mockResolvedValue(respond({ error_code: 'SESSION_EXPIRED', detail: 'do-not-reflect-upstream-detail' }, 401))
    await expect(api.session()).rejects.toMatchObject({ code: 'SESSION_EXPIRED', status: 401 })
    try { await api.session() } catch (error) { expect(error).toBeInstanceOf(ApiError); expect(String(error)).not.toContain('do-not-reflect') }
  })
  it('does not turn source text into executable or credential-bearing links', () => {
    expect(safeSourceUrl('javascript:alert(1)')).toBeUndefined()
    expect(safeSourceUrl('https://name:secret@example.com/path')).toBeUndefined()
    expect(safeSourceUrl('/hackathon/input/sample.md')).toBeUndefined()
    expect(safeSourceUrl('https://example.com/source')).toBe('https://example.com/source')
  })
})
