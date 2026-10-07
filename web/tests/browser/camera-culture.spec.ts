import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import fixture from '../fixtures/guide-result.json' with { type: 'json' }

// Synthetic camera and named API fixtures only. Never reaches the live GPU broker.
test.use({ launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] } })
const palace = { place_id: 'fixture-palace', name: '경복궁', name_en: 'Development Gyeongbokgung', kind: 'heritage', lat: 37.5759, lng: 126.9769, source_id: 'fixture-source', catalog_version: 'fixture-v2' }
const gate = { ...palace, place_id: 'fixture-gate', name: '광화문', name_en: 'Development Gwanghwamun', lat: 37.5760 }
const restaurant = { ...palace, place_id: 'fixture-restaurant', name: 'Development restaurant', name_en: 'Development restaurant', kind: 'restaurant', lat: 37.579, lng: 126.973 }
type Probe = { calls: MediaStreamConstraints[]; streams: MediaStream[]; resolve?: () => void; hidden: boolean; stops: string[] }

async function cameraProbe(page: Page, options: { deny?: string; delayed?: boolean; unsupported?: boolean } = {}) {
  await page.addInitScript(options => {
    const probe: Probe = { calls: [], streams: [], hidden: false, stops: [] }
    ;(window as unknown as { cameraProbe: Probe }).cameraProbe = probe
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => probe.hidden ? 'hidden' : 'visible' })
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: options.unsupported ? undefined : async (constraints: MediaStreamConstraints) => {
      probe.calls.push(constraints)
      if (options.deny) throw new DOMException('Synthetic camera failure', options.deny)
      const canvas = document.createElement('canvas')
      canvas.width = 640; canvas.height = 480
      const context = canvas.getContext('2d')!
      context.fillStyle = '#6f875d'; context.fillRect(0, 0, 640, 480)
      const stream = canvas.captureStream(10)
      const draw = setInterval(() => { context.fillStyle = '#6f875d'; context.fillRect(0, 0, 640, 480) }, 100)
      stream.getTracks().forEach(track => { const stop = track.stop.bind(track); track.stop = () => { clearInterval(draw); probe.stops.push(new Error('Synthetic track stop').stack || ''); stop() } })
      probe.streams.push(stream)
      if (options.delayed) await new Promise<void>(resolve => { probe.resolve = resolve })
      return stream
    } })
  }, options)
}
async function fixtureApi(page: Page, options: { pending?: boolean; confirmation?: boolean; photoLimit?: boolean; busy?: boolean } = {}) {
  const requests: Record<string, unknown>[] = []
  let uploads = 0
  let released = false
  await page.route('**/api/**', async route => {
    const pathname = new URL(route.request().url()).pathname
    let body: unknown
    if (pathname === '/api/sessions') body = { session_id: fixture.session_id }
    else if (pathname === '/api/health') body = { status: 'ok', worker_connected: true, model_configured: true, sandbox_verified: false, catalog_count: 3, version: 'development-camera-fixture' }
    else if (pathname === '/api/catalog') body = { catalog_count: 3, scope_label: 'Development fixture collection', catalog_version: 'fixture-v2', places: [palace, gate, restaurant] }
    else if (pathname === '/api/photos') {
      uploads += 1
      if (options.photoLimit) { await route.fulfill({ status: 429, json: { error_code: 'PHOTO_LIMIT' } }); return }
      body = { photo_id: `fixture-photo-${uploads}`, width: 640, height: 480 }
    } else if (pathname === '/api/requests' && route.request().method() === 'POST') {
      requests.push(route.request().postDataJSON())
      if (options.busy) { await route.fulfill({ status: 409, json: { error_code: 'JOB_BUSY' } }); return }
      await route.fulfill({ status: 202, json: { request_id: `camera-fixture-${requests.length}`, status: 'queued', poll_url: `/api/requests/camera-fixture-${requests.length}` } }); return
    } else if (pathname.startsWith('/api/requests/')) {
      const id = pathname.split('/').pop()!
      const index = Number(id.split('-').pop()) - 1
      const request = requests[index]
      if (options.pending && index === 0 && !released) body = { request_id: id, status: 'running', result: null, error_code: null }
      else {
        const needsConfirmation = options.confirmation && !request.confirmed_place_id
        const result = {
          ...fixture, request_id: id, status: needsConfirmation ? 'need_confirmation' : 'ready',
          speech_text: request.interaction_mode === 'observe' ? 'Development camera fixture: a cultural suggestion.' : 'Development camera fixture: manual answer.',
          scene: { ...fixture.scene, confirmed_food_id: null, confirmed_shop_id: request.confirmed_shop_id ?? null, confirmed_place_id: request.confirmed_place_id ?? null, food_candidates: [], place_candidates: needsConfirmation ? [{ id: palace.place_id, name_ko: palace.name, name_en: palace.name_en }] : [] },
          places: [palace, gate, restaurant].map(place => { const { name_en: _name, ...fields } = place; return { ...fields, distance_m: 14 } }),
        }
        body = { request_id: id, status: 'completed', result, error_code: null }
      }
    } else { await route.fulfill({ status: 404, json: { error_code: 'DEVELOPMENT_FIXTURE_ONLY' } }); return }
    await route.fulfill({ json: body })
  })
  return { requests, uploads: () => uploads, release: () => { released = true } }
}
async function startCamera(page: Page) {
  await page.goto('/')
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.getByRole('button', { name: 'Start camera', exact: true }).click()
  await expect(page.locator('video')).toBeVisible()
  await expect.poll(() => page.locator('video').evaluate((video: HTMLVideoElement) => video.videoWidth > 0 && video.readyState >= 2)).toBe(true)
}

async function speechProbe(page: Page) {
  await page.addInitScript(() => {
    const spoken: string[] = []
    ;(window as unknown as { spoken: string[] }).spoken = spoken
    Object.defineProperty(window, 'speechSynthesis', { value: { getVoices: () => [], cancel: () => {}, speak: (utterance: SpeechSynthesisUtterance) => { spoken.push(utterance.text); utterance.onend?.(new Event('end') as SpeechSynthesisEvent) } } })
  })
}

test('camera requires a click, captures without sending, and stops every track', async ({ page }) => {
  await cameraProbe(page)
  const api = await fixtureApi(page)
  await page.goto('/')
  expect(await page.evaluate(() => (window as unknown as { cameraProbe: Probe }).cameraProbe.calls.length)).toBe(0)
  await page.getByRole('button', { name: 'Start camera', exact: true }).click()
  await expect.poll(() => page.locator('video').evaluate((video: HTMLVideoElement) => video.videoWidth > 0)).toBe(true).catch(async error => {
    console.log(await page.evaluate(() => { const probe = (window as unknown as { cameraProbe: Probe }).cameraProbe; const video = document.querySelector('video')!; return { stops: probe.stops, streams: probe.streams.map(stream => stream.getTracks().map(track => track.readyState)), ready: video.readyState, src: Boolean(video.srcObject), text: document.querySelector('.camera-panel')?.textContent } }))
    throw error
  })
  expect(await page.evaluate(() => (window as unknown as { cameraProbe: Probe }).cameraProbe.calls)).toEqual([{ video: { facingMode: { ideal: 'environment' } }, audio: false }])
  await page.getByRole('button', { name: 'Capture a photo', exact: true }).click()
  await expect(page.locator('.photo-preview img')).toBeVisible()
  expect(api.uploads()).toBe(0)
  expect(api.requests).toHaveLength(0)
  await page.getByRole('button', { name: 'Stop camera', exact: true }).click()
  expect(await page.evaluate(() => (window as unknown as { cameraProbe: Probe }).cameraProbe.streams.every(stream => stream.getTracks().every(track => track.readyState === 'ended')))).toBe(true)
})

for (const [scenario, options, message] of [
  ['permission denied', { deny: 'NotAllowedError' }, 'Camera permission was not granted'],
  ['device busy', { deny: 'NotReadableError' }, 'The camera could not start'],
  ['unsupported', { unsupported: true }, 'Camera preview is unavailable'],
] as const) test(`${scenario}: photo fallback stays usable`, async ({ page }) => {
  await cameraProbe(page, options)
  const api = await fixtureApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Start camera', exact: true }).click()
  await expect(page.locator('.camera-panel')).toContainText(message)
  await expect(page.getByRole('button', { name: 'Choose a photo', exact: true })).toBeEnabled()
  expect(api.requests).toHaveLength(0)
})

test('late camera permission is released after cancellation', async ({ page }) => {
  await cameraProbe(page, { delayed: true }); await fixtureApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Start camera', exact: true }).click()
  await expect.poll(() => page.evaluate(() => Boolean((window as unknown as { cameraProbe: Probe }).cameraProbe.resolve))).toBe(true)
  await page.getByRole('button', { name: 'Cancel camera request', exact: true }).click()
  await page.evaluate(() => (window as unknown as { cameraProbe: Probe }).cameraProbe.resolve!())
  await expect.poll(() => page.evaluate(() => (window as unknown as { cameraProbe: Probe }).cameraProbe.streams.every(stream => stream.getTracks().every(track => track.readyState === 'ended')))).toBe(true)
  await expect(page.locator('video')).toBeHidden()
})

test('one automatic request stays in flight; manual question wins', async ({ page }) => {
  await cameraProbe(page)
  const api = await fixtureApi(page, { pending: true })
  await startCamera(page)
  await page.clock.install()
  await page.getByRole('checkbox', { name: 'Automatic companion' }).check()
  await page.clock.runFor(19999)
  expect(api.requests).toHaveLength(0)
  await page.clock.runFor(1)
  await expect.poll(() => api.requests.length).toBe(1)
  expect(api.requests[0].interaction_mode).toBe('observe')
  await page.clock.runFor(40000)
  expect(api.requests).toHaveLength(1)
  await page.locator('#question').fill('Manual question about Korean history')
  await page.locator('.ask-button').click()
  await expect.poll(() => api.requests.length).toBe(2)
  expect(api.requests[1]).toMatchObject({ interaction_mode: 'ask', question: 'Manual question about Korean history' })
  api.release()
  await expect(page.locator('.result-panel:not(.is-stale) .answer-text')).toContainText('manual answer')
  await page.clock.runFor(19000)
  expect(api.requests).toHaveLength(2)
})

test('hidden page stops camera and auto; returning does not silently restart', async ({ page }) => {
  await cameraProbe(page); const api = await fixtureApi(page)
  await startCamera(page); await page.clock.install()
  await page.getByRole('checkbox', { name: 'Automatic companion' }).check()
  await page.evaluate(() => { (window as unknown as { cameraProbe: Probe }).cameraProbe.hidden = true; document.dispatchEvent(new Event('visibilitychange')) })
  await expect(page.getByRole('button', { name: 'Start camera', exact: true })).toBeVisible()
  await page.evaluate(() => { (window as unknown as { cameraProbe: Probe }).cameraProbe.hidden = false; document.dispatchEvent(new Event('visibilitychange')) })
  await page.clock.runFor(60000)
  expect(api.requests).toHaveLength(0)
  expect(await page.evaluate(() => (window as unknown as { cameraProbe: Probe }).cameraProbe.streams.every(stream => stream.getTracks().every(track => track.readyState === 'ended')))).toBe(true)
})

test('camera ending invalidates an in-flight observation and prevents late TTS', async ({ page }) => {
  await cameraProbe(page); await speechProbe(page)
  const api = await fixtureApi(page, { pending: true })
  await startCamera(page)
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).check()
  await page.clock.install()
  await page.getByRole('checkbox', { name: 'Automatic companion' }).check()
  await page.clock.runFor(20000)
  await expect.poll(() => api.requests.length).toBe(1)
  await page.evaluate(() => (window as unknown as { cameraProbe: Probe }).cameraProbe.streams[0].getVideoTracks()[0].dispatchEvent(new Event('ended')))
  await expect(page.getByRole('button', { name: 'Start camera', exact: true })).toBeVisible()
  api.release()
  await page.clock.runFor(60000)
  await expect(page.locator('.result-panel')).toHaveCount(0)
  expect(await page.evaluate(() => (window as unknown as { spoken: string[] }).spoken)).toEqual([])
  expect(api.requests).toHaveLength(1)
})

test('turning read-aloud off while a manual answer waits prevents stale TTS', async ({ page }) => {
  await speechProbe(page)
  const api = await fixtureApi(page, { pending: true })
  await page.goto('/')
  await page.locator('#place-anchor').selectOption(palace.place_id)
  await page.locator('#question').fill('Tell me the cultural context')
  await page.locator('.ask-button').click()
  await expect.poll(() => api.requests.length).toBe(1)
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  api.release()
  await expect(page.locator('.result-panel:not(.is-stale)')).toBeVisible()
  expect(await page.evaluate(() => (window as unknown as { spoken: string[] }).spoken)).toEqual([])
})

test('repeated automatic proposal remains visible and is only spoken once', async ({ page }) => {
  await cameraProbe(page); await speechProbe(page)
  const api = await fixtureApi(page)
  await startCamera(page)
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).check()
  await page.clock.install()
  await page.getByRole('checkbox', { name: 'Automatic companion' }).check()
  await page.clock.runFor(20000)
  await expect(page.locator('.result-panel:not(.is-stale)')).toBeVisible()
  await page.clock.runFor(20000)
  await expect.poll(() => api.requests.length).toBe(2)
  await expect(page.locator('.result-panel:not(.is-stale)')).toBeVisible()
  expect(await page.evaluate(() => (window as unknown as { spoken: string[] }).spoken.length)).toBe(1)
})

test('uncertain cultural identity requires explicit confirmation with catalog coordinates', async ({ page }) => {
  const api = await fixtureApi(page, { confirmation: true })
  await page.goto('/')
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.locator('input[type=file]').first().setInputFiles({ name: 'development-fixture.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0QAAAABJRU5ErkJggg==', 'base64') })
  await page.locator('#question').fill('What cultural place is visible?')
  await page.locator('.ask-button').click()
  await expect(page.locator('.place-confirmation')).toBeVisible()
  expect(api.requests[0].confirmed_place_id).toBeNull()
  await page.locator('.place-confirmation button').click()
  await expect.poll(() => api.requests.length).toBe(2)
  expect(api.requests[1]).toMatchObject({ confirmed_place_id: palace.place_id, confirmed_shop_id: null, location: { lat: palace.lat, lng: palace.lng, origin: 'selected' } })
})

for (const condition of ['confirmation', 'photoLimit', 'busy'] as const) test(`automatic mode stops on ${condition}`, async ({ page }) => {
  await cameraProbe(page); const api = await fixtureApi(page, { [condition]: true })
  await startCamera(page); await page.clock.install()
  await page.getByRole('checkbox', { name: 'Automatic companion' }).check()
  await page.clock.runFor(20000)
  await expect(page.getByRole('checkbox', { name: 'Automatic companion' })).not.toBeChecked()
  const count = api.requests.length
  await page.clock.runFor(60000)
  expect(api.requests).toHaveLength(count)
  await expect(page.locator('.automatic-notice')).toBeVisible()
})

test('place confirmation uses catalog coordinates; culture and meals stay distinct', async ({ page }, testInfo) => {
  const api = await fixtureApi(page, { confirmation: true })
  await page.goto('/')
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.locator('#place-anchor').selectOption(palace.place_id)
  await expect(page.locator('.anchor-picker')).toContainText('main gate of Gyeongbokgung')
  await page.locator('#question').fill('Describe this cultural place')
  await page.locator('.ask-button').click()
  await expect(page.locator('.result-panel:not(.is-stale)')).toBeVisible()
  expect(api.requests[0]).toMatchObject({ confirmed_place_id: palace.place_id, confirmed_shop_id: null, interaction_mode: 'ask', location: { lat: palace.lat, lng: palace.lng, origin: 'selected' }, photo_id: null })
  await expect(page.locator('.place-list')).toContainText('History & culture')
  await expect(page.locator('.place-list')).toContainText('Restaurant')
  await expect(page.locator('.place-list')).toContainText('광화문')
  await page.getByRole('button', { name: 'Find a meal nearby', exact: true }).click()
  await expect.poll(() => api.requests.length).toBe(2)
  expect(api.requests[1]).toMatchObject({ confirmed_place_id: palace.place_id, confirmed_shop_id: null })
  await expect(page.locator('.result-panel:not(.is-stale)')).toBeVisible()
  await page.locator('.place-card').filter({ hasText: 'Development restaurant' }).click()
  await expect.poll(() => api.requests.length).toBe(3)
  expect(api.requests[2]).toMatchObject({ confirmed_place_id: restaurant.place_id, confirmed_shop_id: restaurant.place_id, location: { lat: restaurant.lat, lng: restaurant.lng, origin: 'selected' } })
  await expect(page.locator('.result-panel:not(.is-stale)')).toBeVisible()
  await page.getByRole('button', { name: 'Explore nearby history', exact: true }).click()
  await expect.poll(() => api.requests.length).toBe(4)
  expect(String(api.requests[3].question)).toContain('cultural or historical')
  await expect(page.locator('.result-panel:not(.is-stale)')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.screenshot({ path: `tests/artifacts/${testInfo.project.name}-culture-camera-fixture.png`, fullPage: true })
})
