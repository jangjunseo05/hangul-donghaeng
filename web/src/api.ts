import type { Catalog, GuideRequest, GuideResult, Health, Job } from './types'

export class ApiError extends Error {
  constructor(public code: string, public status = 0) { super(code); this.name = 'ApiError' }
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const parent = init.signal
  const abort = () => controller.abort()
  if (parent?.aborted) controller.abort()
  parent?.addEventListener('abort', abort, { once: true })
  const timeout = window.setTimeout(abort, 20000)
  try {
    const response = await fetch(path, { ...init, credentials: 'include', signal: controller.signal, headers: { Accept: 'application/json', ...init.headers } })
    let payload: unknown
    try { payload = await response.json() } catch { throw new ApiError('INVALID_RESPONSE', response.status) }
    if (!response.ok) {
      const code = payload && typeof payload === 'object' && 'error_code' in payload && typeof payload.error_code === 'string' ? payload.error_code : 'SERVER_ERROR'
      throw new ApiError(code, response.status)
    }
    return payload as T
  } catch (error) {
    if (parent?.aborted) throw new DOMException('Aborted', 'AbortError')
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted) throw new ApiError('TIMEOUT')
    throw new ApiError('OFFLINE')
  } finally { clearTimeout(timeout); parent?.removeEventListener('abort', abort) }
}
const jsonPost = (body: unknown, signal?: AbortSignal): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })
export const api = {
  session: (signal?: AbortSignal) => request<{ session_id: string }>('/api/sessions', jsonPost({}, signal)),
  health: () => request<Health>('/api/health'),
  catalog: () => request<Catalog>('/api/catalog'),
  upload: (file: File, signal?: AbortSignal) => { const form = new FormData(); form.append('file', file); return request<{ photo_id: string; width: number; height: number }>('/api/photos', { method: 'POST', body: form, signal }) },
  submit: (body: GuideRequest, signal?: AbortSignal) => request<{ request_id: string; status: 'queued'; poll_url: string }>('/api/requests', jsonPost(body, signal)),
  job: (id: string, signal?: AbortSignal) => request<Job>('/api/requests/' + encodeURIComponent(id), { signal }),
}
export function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return }
    const done = () => { signal.removeEventListener('abort', abort); resolve() }
    const timer = setTimeout(done, ms)
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(new DOMException('Aborted', 'AbortError')) }
    signal.addEventListener('abort', abort, { once: true })
  })
}
export async function waitForResult(id: string, session: string, signal: AbortSignal, onStatus: (status: Job['status']) => void): Promise<GuideResult> {
  const deadline = Date.now() + 70000
  while (!signal.aborted && Date.now() < deadline) {
    const job = await api.job(id, signal)
    if (job.request_id !== id) throw new ApiError('INVALID_RESPONSE')
    if (!['queued', 'running', 'completed', 'failed', 'superseded'].includes(job.status)) throw new ApiError('INVALID_RESPONSE')
    onStatus(job.status)
    if (job.status === 'superseded') throw new ApiError('SUPERSEDED')
    if (job.status === 'failed') throw new ApiError(job.error_code || 'JOB_FAILED')
    if (job.status === 'completed') {
      const r = job.result
      if (!r || r.request_id !== id || r.session_id !== session || r.schema_version !== 1 || !r.scene || !Array.isArray(r.places) || !Array.isArray(r.menus) || !Array.isArray(r.evidence) || !Array.isArray(r.unknowns) || !Array.isArray(r.claims) || !Array.isArray(r.itinerary) || !Array.isArray(r.conflicts) || typeof r.speech_text !== 'string') throw new ApiError('INVALID_RESPONSE')
      return r
    }
    await pause(900, signal)
  }
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
  throw new ApiError('TIMEOUT')
}
export function safeSourceUrl(source: string): string | undefined {
  try { const url = new URL(source); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined } catch { return undefined }
}
