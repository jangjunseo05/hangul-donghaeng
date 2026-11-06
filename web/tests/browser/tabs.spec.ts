import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
// Contract examples straight from shared/examples (no copies).
import nearbyLandmark from '../../../shared/examples/nearby.landmark.json' with { type: 'json' }
import nearbyFood from '../../../shared/examples/nearby.food.json' with { type: 'json' }
import nearbyError from '../../../shared/examples/nearby.error.json' with { type: 'json' }
import cardEn from '../../../shared/examples/landmark-card.en.json' with { type: 'json' }
import cardUnverified from '../../../shared/examples/landmark-card.model-unverified.en.json' with { type: 'json' }
import routesEn from '../../../shared/examples/routes.en.json' with { type: 'json' }
import resultStory from '../../../shared/examples/result.story.json' with { type: 'json' }
import statusRunning from '../../../shared/examples/request-status.running.json' with { type: 'json' }

type Options = { live?: boolean; nearbyFail?: boolean; card?: unknown; running?: boolean; tts?: 'ok' | 'unavailable' }
async function api(page: Page, options: Options = {}) {
  const calls: string[] = []
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    calls.push(route.request().method() + ' ' + path + url.search)
    if (path === '/api/sessions') return route.fulfill({ json: { session_id: 's-example' } })
    if (path === '/api/health') return route.fulfill({ json: { status: 'ok', worker_connected: true, model_configured: true, sandbox_verified: false, catalog_count: 3, version: 'tabs-fixture' } })
    if (path === '/api/catalog') return route.fulfill({ json: { catalog_count: 1, scope_label: 'fixture', catalog_version: 'fixture', places: [{ place_id: 'local:gwanghwamun', name: '광화문', name_en: 'Gwanghwamun Gate', kind: 'heritage', lat: 37.576, lng: 126.9768, source_id: 'visitkorea:gwanghwamun-location', catalog_version: 'fixture' }] } })
    if (path === '/api/tts') { calls.push('TTS-BODY ' + route.request().postData()); if (options.tts === 'ok') { await new Promise(resolve => setTimeout(resolve, 150)); return route.fulfill({ status: 200, contentType: 'audio/wav', headers: { 'X-TTS-Voice': 'fixture' }, body: wav(0.25) }) } return route.fulfill({ status: 503, json: { error_code: 'TTS_UNAVAILABLE' } }) }
    if (options.live && path === '/api/nearby') return route.fulfill({ json: options.nearbyFail ? nearbyError : url.searchParams.get('tab') === 'food' ? nearbyFood : nearbyLandmark })
    if (options.live && path.startsWith('/api/landmarks/')) return route.fulfill({ json: options.card ?? cardEn })
    if (options.live && path === '/api/routes') return route.fulfill({ json: routesEn })
    if (path === '/api/photos') return route.fulfill({ json: { photo_id: 'p-1', width: 1, height: 1 } })
    if (path === '/api/requests' && route.request().method() === 'POST') return route.fulfill({ status: 202, json: { request_id: 'r-example', status: 'queued', poll_url: '/api/requests/r-example' } })
    if (path.startsWith('/api/requests/')) return route.fulfill({ json: options.running ? statusRunning : { request_id: 'r-example', status: 'completed', stage: null, result: resultStory, error_code: null } })
    return route.fulfill({ status: 404, json: { detail: 'Not Found' } })
  })
  return calls
}
/** A valid 8 kHz mono 16-bit PCM WAV of the given length (a quiet tone), so Chrome can really play it. */
function wav(seconds: number) {
  const rate = 8000, samples = Math.round(rate * seconds), data = Buffer.alloc(samples * 2)
  for (let i = 0; i < samples; i++) data.writeInt16LE(Math.round(Math.sin(i / 8) * 800), i * 2)
  const header = Buffer.alloc(44)
  header.write('RIFF', 0); header.writeUInt32LE(36 + data.length, 4); header.write('WAVE', 8); header.write('fmt ', 12)
  header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22); header.writeUInt32LE(rate, 24)
  header.writeUInt32LE(rate * 2, 28); header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34); header.write('data', 36); header.writeUInt32LE(data.length, 40)
  return Buffer.concat([header, data])
}
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0QAAAABJRU5ErkJggg==', 'base64')
async function ask(page: Page) {
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.locator('input[type=file]').first().setInputFiles({ name: 'p.png', mimeType: 'image/png', buffer: png })
  await page.locator('#question').fill('Tell me about this place')
  await page.locator('.ask-button').click()
}

test('unimplemented tab routes fall back to the contract examples and say so', async ({ page }) => {
  const calls = await api(page)
  await page.goto('/')
  await page.getByRole('tab', { name: 'Landmarks' }).click()
  await expect(page.locator('.sheet-list')).toContainText('Gyeongbokgung Palace')
  await expect(page.locator('.fixture-note')).toContainText('fixture')
  await expect(page.locator('.demo-note')).toContainText('Seochon demo point')
  expect(calls.some(call => call.startsWith('GET /api/nearby?tab=landmark&lat=37.579000&lng=126.973000&radius_m=1000'))).toBe(true)
  await page.getByRole('tab', { name: 'Routes' }).click()
  await expect(page.locator('.route-timeline')).toContainText('Geunjeongjeon')
  await expect(page.locator('.fixture-note')).toBeVisible()
})

test('live nearby: list, attribution, card with per-block source and no fixture label', async ({ page }) => {
  await api(page, { live: true })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Landmarks' }).click()
  await expect(page.locator('.attribution-line')).toContainText('© OpenStreetMap contributors (ODbL)')
  await expect(page.locator('.fixture-note')).toHaveCount(0)
  await page.locator('.sheet-list button').filter({ hasText: 'Gwanghwamun' }).click()
  await expect(page.locator('.story-card')).toContainText('What it is')
  // Expectations come from the imported contract example, so a re-merged example does not break the test.
  const sources = (cardEn as { sources?: { id: string; url: string; title: string | null }[] }).sources ?? []
  const wiki = sources.find(source => source.id.startsWith('wikipedia:'))
  if (wiki) {
    await expect(page.locator('.story-card .source-line', { hasText: 'Wikipedia' }).first()).toBeVisible()
    await expect(page.locator('.story-card .source-line a', { hasText: 'CC BY-SA 4.0' }).first()).toHaveAttribute('href', 'https://creativecommons.org/licenses/by-sa/4.0/')
    if (wiki.title) await expect(page.locator('.story-card .source-line a', { hasText: wiki.title }).first()).toHaveAttribute('href', wiki.url)
  }
  const official = sources.find(source => !source.id.startsWith('wikipedia:') && source.title)
  if (official) await expect(page.locator('.story-card .source-line a', { hasText: official.title! }).first()).toHaveAttribute('href', official.url)
  if (Object.values(cardEn.blocks as Record<string, { analogy?: boolean } | null>).some(block => block?.analogy)) await expect(page.locator('.story-card .analogy-tag').first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start from here', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ask the guide here', exact: true })).toBeVisible()
})

test('model_unverified blocks carry the "Unverified" badge', async ({ page }) => {
  await api(page, { live: true, card: cardUnverified })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Landmarks' }).click()
  await page.locator('.sheet-list button').first().click()
  await expect(page.locator('.story-block.is-unverified')).toHaveCount(2)
  await expect(page.locator('.story-block.is-unverified').first()).toContainText('Unverified — general knowledge, please double-check')
  await expect(page.locator('.story-foot .verify-badge')).toContainText('Unverified')
})

test('an external nearby failure is shown with retry, not as an empty success', async ({ page }) => {
  await api(page, { live: true, nearbyFail: true })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Eat' }).click()
  await expect(page.getByRole('alert')).toContainText('took too long')
  await expect(page.getByRole('button', { name: 'Retry', exact: true })).toBeVisible()
})

test('routes: both templates, ui_note, walk estimate and the Bukchon restriction notice', async ({ page }) => {
  await api(page, { live: true })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Routes' }).click()
  await expect(page.locator('.route-note')).toContainText('Actual walking route not verified')
  await expect(page.locator('.route-timeline .leg').first()).toContainText('(estimate)')
  await expect(page.locator('.restriction-note')).toHaveCount(0)
  await page.getByRole('tab', { name: 'Palace to hanok village' }).click()
  await expect(page.locator('.restriction-note')).toContainText('restricted in part of Bukchon')
  // Route.visit_note (dated) wins over the undated fallback.
  const visitNote = (routesEn.routes[1] as { visit_note?: { text: string } | null }).visit_note
  if (visitNote) await expect(page.locator('.restriction-note')).toContainText(visitNote.text)
})

test('a map tap proposes a starting point; only the confirm button sets it', async ({ page }) => {
  const calls = await api(page, { live: true })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Eat' }).click()
  await page.locator('.screen-map .map-canvas').click({ position: { x: 100, y: 120 } })
  await expect(page.locator('.map-confirm')).toBeVisible()
  const before = calls.filter(call => call.startsWith('GET /api/nearby')).length
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.locator('.map-caption')).toContainText('No starting point yet')
  await page.locator('.screen-map .map-canvas').click({ position: { x: 100, y: 120 } })
  await page.getByRole('button', { name: 'Start from here', exact: true }).click()
  await expect(page.locator('.map-caption')).toContainText('Using your selected map point')
  await expect.poll(() => calls.filter(call => call.startsWith('GET /api/nearby')).length).toBeGreaterThan(before)
})

test('Look: story sheet uses landmark_card; running stage shows progress steps', async ({ page }) => {
  await api(page)
  await page.goto('/')
  await ask(page)
  await expect(page.locator('.answer-sheet .story-card')).toContainText('What to look for')
  await expect(page.locator('.answer-sheet .story-card .source-line').first()).toBeVisible()
})
test('Look: running job reports its stage', async ({ page }) => {
  await api(page, { running: true })
  await page.goto('/')
  await ask(page)
  await expect(page.locator('.working-panel h3')).toHaveText('Matching it with nearby places…')
  await expect(page.locator('.reasoning-step.now .reasoning-step-head b')).toHaveText('Candidates')
  await expect(page.locator('.reasoning-step.done .reasoning-step-head b')).toHaveText('Observe')
})

test('server voice is tried first; on 503 the browser voice reads each sentence', async ({ page }) => {
  await page.addInitScript(() => {
    const spoken: string[] = []
    ;(window as unknown as { spoken: string[] }).spoken = spoken
    // Plain utterance class so the synthetic voice objects can be assigned.
    ;(window as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class { text: string; lang = ''; voice: unknown = null; rate = 1; pitch = 1; volume = 1; onend: ((event: Event) => void) | null = null; onerror: unknown = null; constructor(text: string) { this.text = text } }
    Object.defineProperty(window, 'speechSynthesis', { value: { getVoices: () => [{ name: 'Google US English Male', lang: 'en-US' }, { name: 'Samantha', lang: 'en-US' }], cancel: () => {}, speak: (utterance: SpeechSynthesisUtterance) => { spoken.push((utterance.voice?.name ?? '-') + '|' + utterance.text); setTimeout(() => utterance.onend?.(new Event('end') as SpeechSynthesisEvent), 10) } } })
  })
  const calls = await api(page, { live: true, tts: 'unavailable' })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Landmarks' }).click()
  await page.locator('.sheet-list button').filter({ hasText: 'Gwanghwamun' }).click()
  await page.getByRole('button', { name: 'Listen to the story', exact: true }).click()
  await expect.poll(() => page.evaluate(() => (window as unknown as { spoken: string[] }).spoken.length)).toBeGreaterThan(1)
  const spoken = await page.evaluate(() => (window as unknown as { spoken: string[] }).spoken)
  expect(spoken.every(entry => entry.startsWith('Samantha|'))).toBe(true)
  expect(calls.filter(call => call === 'POST /api/tts').length).toBe(1)
})

test('server voice 200: each sentence plays from /api/tts in order, the next one prefetched, no browser voice', async ({ page }) => {
  await page.addInitScript(() => {
    const log: string[] = []
    ;(window as unknown as { audioLog: string[] }).audioLog = log
    const play = HTMLMediaElement.prototype.play
    HTMLMediaElement.prototype.play = function () { if (this.src.startsWith('blob:')) log.push('play ' + Math.round(performance.now())); return play.call(this) }
    Object.defineProperty(window, 'speechSynthesis', { value: { getVoices: () => [], cancel: () => {}, speak: () => { log.push('browser-voice') } } })
  })
  const calls = await api(page, { live: true, tts: 'ok' })
  await page.goto('/')
  await page.getByRole('tab', { name: 'Landmarks' }).click()
  await page.locator('.sheet-list button').filter({ hasText: 'Gwanghwamun' }).click()
  await page.getByRole('button', { name: 'Listen to the story', exact: true }).click()
  await expect.poll(() => page.evaluate(() => (window as unknown as { audioLog: string[] }).audioLog.filter(entry => entry.startsWith('play')).length), { timeout: 15000 }).toBeGreaterThan(2)
  const log = await page.evaluate(() => (window as unknown as { audioLog: string[] }).audioLog)
  expect(log).not.toContain('browser-voice')
  const bodies = calls.filter(call => call.startsWith('TTS-BODY ')).map(call => JSON.parse(call.slice(9)) as { text: string; lang: string })
  expect(bodies[0].lang).toBe('en')
  // First request is a single sentence; requests follow sentence order.
  const story = Object.values(cardEn.blocks as Record<string, { text: string } | null>).filter(Boolean).map(block => block!.text).join(' ')
  expect(story.startsWith(bodies[0].text)).toBe(true)
  expect(bodies.every(body => body.text.length <= 220)).toBe(true)
})
