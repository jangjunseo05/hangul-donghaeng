import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import fixture from '../fixtures/guide-result.json' with { type: 'json' }

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0QAAAABJRU5ErkJggg==', 'base64')
type DeferredGps = { fireGps: () => void; failGps: () => void }
async function setup(page: Page) {
  const requests: Record<string, unknown>[] = []
  let releaseNew = false
  await page.addInitScript(() => {
    let success: PositionCallback
    let failure: PositionErrorCallback | null | undefined
    const deferred = window as unknown as DeferredGps
    Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
      getCurrentPosition(onSuccess: PositionCallback, onFailure?: PositionErrorCallback | null) { success = onSuccess; failure = onFailure },
    } })
    deferred.fireGps = () => success({ coords: { latitude: 35.1, longitude: 129.1, accuracy: 5 }, timestamp: Date.now() } as GeolocationPosition)
    deferred.failGps = () => failure?.({ code: 1, message: 'test permission denied' } as GeolocationPositionError)
  })
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let body: unknown
    if (path === '/api/sessions') body = { session_id: fixture.session_id }
    else if (path === '/api/health') body = { status: 'ok', worker_connected: false, model_configured: false, sandbox_verified: false, catalog_count: 1, version: 'gps-test-fixture' }
    else if (path === '/api/photos') body = { photo_id: 'fixture-photo', width: 1, height: 1 }
    else if (path === '/api/requests') {
      requests.push(route.request().postDataJSON())
      body = { request_id: 'gps-fixture-' + requests.length, status: 'queued', poll_url: '/api/requests/gps-fixture-' + requests.length }
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(body) }); return
    } else if (path.startsWith('/api/requests/')) {
      const id = path.split('/').pop()!
      const index = Number(id.split('-').pop()) - 1
      const request = requests[index]
      const waiting = index === 1 && !releaseNew
      const mode = request.dataset_mode
      const result = { ...fixture, request_id: id, dataset_mode: mode, places: mode === 'fictional_task' ? [] : fixture.places, speech_text: index === 0 ? 'Development fixture: original real-place answer.' : mode === 'fictional_task' ? 'Development fixture: current fictional answer.' : 'Development fixture: current real-place answer.' }
      body = { request_id: id, status: waiting ? 'running' : 'completed', result: waiting ? null : result, error_code: null }
    } else { await route.abort(); return }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto('/')
  await page.locator('input[type=file]').first().setInputFiles({ name: 'fixture-food.png', mimeType: 'image/png', buffer: png })
  await page.getByRole('button', { name: 'Seochon demo', exact: true }).click()
  await page.getByRole('textbox', { name: /Ask your little local guide/ }).fill('Initial fixture question')
  await page.getByRole('button', { name: 'Explore with me' }).click()
  await expect(page.locator('.answer-text')).toContainText('original real-place')
  await page.getByRole('button', { name: 'Use my location', exact: true }).click()
  return { requests, release: () => { releaseNew = true } }
}
async function fireGps(page: Page, error = false) {
  await page.evaluate(error => { const gps = window as unknown as DeferredGps; if (error) gps.failGps(); else gps.fireGps() }, error)
  await page.waitForTimeout(300)
}
test('delayed GPS cannot replace a new fictional request using an old real-place closure', async ({ page }) => {
  const state = await setup(page)
  await page.getByRole('button', { name: 'Connection', exact: true }).click()
  await page.getByRole('button', { name: 'Try the fictional practice itinerary' }).click()
  await page.getByRole('textbox', { name: /Ask your little local guide/ }).fill('Current fictional fixture question')
  await page.getByRole('button', { name: 'Explore with me' }).click()
  await expect.poll(() => state.requests.length).toBe(2)
  await fireGps(page)
  expect(state.requests.map(request => request.dataset_mode)).toEqual(['real_place', 'fictional_task'])
  state.release()
  await expect(page.locator('.answer-text')).toContainText('current fictional answer')
  await expect(page.locator('.place-list')).toHaveCount(0)
  await expect(page.locator('.practice-banner')).toBeVisible()
})
test('a new real-place question invalidates an older GPS success', async ({ page }) => {
  const state = await setup(page)
  await page.getByRole('textbox', { name: /Ask your little local guide/ }).fill('New real-place fixture question')
  await page.getByRole('button', { name: 'Keep exploring' }).click()
  await expect.poll(() => state.requests.length).toBe(2)
  await fireGps(page)
  expect(state.requests).toHaveLength(2)
  state.release()
  await expect(page.locator('.answer-text')).toContainText('current real-place answer')
  await expect(page.locator('.map-caption')).toContainText('Demo starting point')
  await expect(page.getByRole('button', { name: 'Use my location', exact: true })).toBeEnabled()
})
for (const action of ['replace', 'remove'] as const) {
  test('photo ' + action + ' invalidates a delayed GPS success', async ({ page }) => {
    const state = await setup(page)
    if (action === 'replace') await page.locator('input[type=file]').first().setInputFiles({ name: 'replacement-fixture.png', mimeType: 'image/png', buffer: png })
    else await page.getByRole('button', { name: 'Remove photo', exact: true }).click()
    await fireGps(page)
    expect(state.requests).toHaveLength(1)
    await expect(page.locator('.map-caption')).toContainText('Demo starting point')
    await expect(page.getByRole('button', { name: 'Use my location', exact: true })).toBeEnabled()
  })
}
test('an obsolete GPS failure cannot add an error after switching modes', async ({ page }) => {
  await setup(page)
  await page.getByRole('button', { name: 'Connection', exact: true }).click()
  await page.getByRole('button', { name: 'Try the fictional practice itinerary' }).click()
  await fireGps(page, true)
  await page.getByRole('button', { name: 'Back to explore', exact: true }).click()
  await expect(page.getByText('Location permission was unavailable. Tap the map or choose the Seochon demo point.')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Use my location', exact: true })).toBeEnabled()
})
test('a current GPS callback still updates location and submits the intended request', async ({ page }) => {
  const state = await setup(page)
  await fireGps(page)
  await expect.poll(() => state.requests.length).toBe(2)
  expect(state.requests[1]).toMatchObject({ dataset_mode: 'real_place', location: { lat: 35.1, lng: 129.1, origin: 'gps' } })
  state.release()
  await expect(page.locator('.answer-text')).toContainText('current real-place answer')
  await expect(page.locator('.map-caption')).toContainText('your location')
})

