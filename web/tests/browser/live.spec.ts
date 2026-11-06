import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'

// Live broker E2E (decision 3, M3): no API mocks. Needs the broker on 127.0.0.1:8000 behind Vite's /api proxy.
//   HD_LIVE_BROKER=1  tabs, cards, routes, TTS fallback (no model call; nearby may make one OSM lookup via the broker)
//   HD_LIVE_MODEL=1   additionally one real ask request to see the job stage (uses the GPU model)
test.skip(process.env.HD_LIVE_BROKER !== '1', 'Live broker test: set HD_LIVE_BROKER=1 with the broker running on 127.0.0.1:8000')
test.describe.configure({ mode: 'serial' })
test.beforeEach(() => { test.setTimeout(60000) })

// One browser context (one session cookie) for the whole file: the broker rate-limits new sessions
// (429 SESSION_RATE_LIMIT), so a fresh context per test would exhaust it.
let context: BrowserContext
let shared: Page
test.beforeAll(async ({ browser }, testInfo) => {
  context = await browser.newContext({ baseURL: 'http://127.0.0.1:5173', viewport: testInfo.project.use.viewport ?? { width: 390, height: 844 } })
  await context.addInitScript(() => {
    // Records when a server-voice clip (blob: URL) starts playing, to measure the first-sentence delay.
    const audioLog: number[] = []
    ;(window as unknown as { audioLog: number[] }).audioLog = audioLog
    const play = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function () { if (this.src.startsWith('blob:')) audioLog.push(performance.now()); return play.call(this) }
    const spoken: string[] = []
    ;(window as unknown as { spoken: string[] }).spoken = spoken
    ;(window as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class { text: string; lang = ''; voice: unknown = null; rate = 1; pitch = 1; volume = 1; onend: ((event: Event) => void) | null = null; onerror: unknown = null; constructor(text: string) { this.text = text } }
    Object.defineProperty(window, 'speechSynthesis', { value: { getVoices: () => [{ name: 'Samantha', lang: 'en-US' }], cancel: () => {}, speak: (utterance: SpeechSynthesisUtterance) => { spoken.push(utterance.text); setTimeout(() => utterance.onend?.(new Event('end') as SpeechSynthesisEvent), 10) } } })
  })
  shared = await context.newPage()
})
test.afterAll(async () => { await context?.close() })

async function open(page: Page) {
  const errors: string[] = []
  page.removeAllListeners('pageerror')
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.locator('.connection-dot.online')).toBeVisible({ timeout: 15000 })
  return errors
}

test('live: landmarks list comes from the server (no fixture label), with attribution or a visible error', async ({}, testInfo) => {
  const page = shared
  const errors = await open(page)
  const seen: { status: number; places: number; error_code: string | null; ms: number }[] = []
  const started = Date.now()
  page.on('response', async response => { if (response.url().includes('/api/nearby?tab=landmark')) { try { const body = await response.json(); seen.push({ status: response.status(), places: body.places?.length ?? 0, error_code: body.error_code ?? null, ms: Date.now() - started }) } catch { /* ignore */ } } })
  await page.getByRole('tab', { name: 'Landmarks' }).click()
  // The external map search may be slow or fail; either a list or a visible error is acceptable, a fixture is not.
  await expect(page.locator('.sheet-list li, .screen-sheet [role=alert]').first()).toBeVisible({ timeout: 45000 })
  await testInfo.attach('nearby-landmark', { body: JSON.stringify(seen), contentType: 'application/json' })
  await expect(page.locator('.fixture-note')).toHaveCount(0)
  if (seen[0] && !seen[0].error_code) await expect(page.locator('.attribution-line')).toBeVisible()
  expect(errors).toEqual([])
})

test('live: a landmark card renders blocks with source links', async ({}, testInfo) => {
  const page = shared
  await open(page)
  await page.getByRole('tab', { name: 'Landmarks' }).click()
  const withCard = page.locator('.sheet-list button').filter({ hasText: /story|이야기/ }).first()
  await expect(withCard).toBeVisible({ timeout: 45000 })
  const card = page.waitForResponse(response => response.url().includes('/api/landmarks/'), { timeout: 15000 })
  await withCard.click()
  const response = await card
  expect(response.status()).toBe(200)
  const body = await response.json()
  await testInfo.attach('card', { body: JSON.stringify({ place_id: body.place_id, verification: body.verification, sources: (body.sources ?? []).length }), contentType: 'application/json' })
  await expect(page.locator('.story-card')).toContainText(body.blocks.what_it_is.text)
  await expect(page.locator('.fixture-tag')).toHaveCount(0)
  if ((body.sources ?? []).length) await expect(page.locator('.story-card .source-line a').first()).toBeVisible()
})

test('live: routes show both templates, ui_note and the dated Bukchon note', async ({}) => {
  const page = shared
  await open(page)
  const routes = page.waitForResponse(response => response.url().includes('/api/routes'), { timeout: 15000 })
  await page.getByRole('tab', { name: 'Routes' }).click()
  const response = await routes
  const body = await response.json()
  expect(response.status(), JSON.stringify(body)).toBe(200)
  await expect(page.locator('.fixture-note')).toHaveCount(0)
  await expect(page.locator('.route-note')).toContainText(body.routes[0].ui_note)
  const bukchon = body.routes.find((route: { visit_note?: unknown }) => route.visit_note)
  if (bukchon) {
    await page.getByRole('tab', { name: bukchon.title }).click()
    await expect(page.locator('.restriction-note')).toContainText(bukchon.visit_note.text)
  }
})

test('live: server TTS is tried first and the browser voice takes over when it is unavailable', async ({}, testInfo) => {
  const page = shared
  await page.goto('about:blank')
  await open(page)
  await page.getByRole('tab', { name: 'Routes' }).click()
  await page.locator('.stop-name:not([disabled])').first().click()
  await expect(page.locator('.story-card')).toBeVisible({ timeout: 15000 })
  const tts = page.waitForResponse(response => response.url().endsWith('/api/tts'), { timeout: 30000 })
  const clickedAt = await page.evaluate(() => performance.now())
  await page.getByRole('button', { name: 'Listen to the story', exact: true }).click()
  const status = (await tts).status()
  await testInfo.attach('tts-status', { body: String(status), contentType: 'text/plain' })
  if (status === 200) {
    // Real server voice: the first sentence must start from a server clip, not the browser voice.
    await expect.poll(() => page.evaluate(() => (window as unknown as { audioLog: number[] }).audioLog.length), { timeout: 30000 }).toBeGreaterThan(0)
    const firstPlay = await page.evaluate(() => (window as unknown as { audioLog: number[] }).audioLog[0])
    await testInfo.attach('tts-first-sentence-ms', { body: String(Math.round(firstPlay - clickedAt)), contentType: 'text/plain' })
    await testInfo.attach('tts-voice', { body: String((await tts).headers()['x-tts-voice'] ?? ''), contentType: 'text/plain' })
    await page.waitForTimeout(4000)
    const clips = await page.evaluate(() => (window as unknown as { audioLog: number[] }).audioLog.length)
    const spoken = await page.evaluate(() => (window as unknown as { spoken: string[] }).spoken.length)
    await testInfo.attach('tts-clips-browser', { body: JSON.stringify({ server_clips_in_4s: clips, browser_voice_sentences: spoken }), contentType: 'application/json' })
    await page.getByRole('button', { name: 'Stop listening to the story', exact: true }).click()
    return
  }
  await expect.poll(() => page.evaluate(() => (window as unknown as { spoken: string[] }).spoken.length)).toBeGreaterThan(0)
})

test('live model: a real ask shows job stages, then the answer is read by the server voice', async ({}, testInfo) => {
  test.skip(process.env.HD_LIVE_MODEL !== '1', 'Real model request: set HD_LIVE_MODEL=1 (uses the GPU model)')
  test.setTimeout(120000)
  const page = shared
  await open(page)
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).check()
  await page.locator('.start-chip').click()
  await page.getByRole('button', { name: 'Seochon demo', exact: true }).click()
  const stages: { stage: string; ms: number }[] = []
  let started = 0
  page.on('response', async response => { if (/\/api\/requests\/[^/]+$/.test(new URL(response.url()).pathname)) { try { const job = await response.json(); if (job.stage && stages.at(-1)?.stage !== job.stage) stages.push({ stage: job.stage, ms: Date.now() - started }) } catch { /* ignore */ } } })
  await page.evaluate(() => { (window as unknown as { audioLog: number[] }).audioLog.length = 0 })
  // A real photo (data/samples/heritage-demo.jpg, licensed Commons thumbnail of Gwanghwamun) so the app sends the request.
  await page.locator('input[type=file]').first().setInputFiles(fileURLToPath(new URL('../../../data/samples/heritage-demo.jpg', import.meta.url)))
  await page.locator('#question').fill('What is this place?')
  started = Date.now()
  await page.locator('.ask-button').click()
  await expect(page.locator('.reasoning.is-live')).toBeVisible({ timeout: 10000 })
  await expect(page.locator('.result-panel:not(.is-stale), .error-panel').first()).toBeVisible({ timeout: 90000 })
  const answeredAt = Date.now() - started
  const answeredPerf = await page.evaluate(() => performance.now())
  const ok = await page.locator('.result-panel:not(.is-stale)').count() > 0
  let firstSentenceMs: number | null = null
  if (ok) {
    await expect.poll(() => page.evaluate(() => (window as unknown as { audioLog: number[] }).audioLog.length), { timeout: 30000 }).toBeGreaterThan(0).catch(() => {})
    const first = await page.evaluate(() => (window as unknown as { audioLog: number[] }).audioLog[0] ?? null)
    if (first !== null) firstSentenceMs = Math.max(0, Math.round(first - answeredPerf))
  }
  await testInfo.attach('model-run', { body: JSON.stringify({ ok, stages, answered_ms: answeredAt, first_sentence_after_answer_ms: firstSentenceMs, browser_voice_sentences: await page.evaluate(() => (window as unknown as { spoken: string[] }).spoken.length), answer: ok ? (await page.locator('.answer-text').innerText()).slice(0, 200) : await page.locator('.error-panel').innerText() }), contentType: 'application/json' })
  expect(ok).toBe(true)
})
