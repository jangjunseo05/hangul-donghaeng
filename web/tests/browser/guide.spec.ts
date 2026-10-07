import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import fixture from '../fixtures/guide-result.json' with { type: 'json' }
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0QAAAABJRU5ErkJggg==', 'base64')
async function fixtureApi(page: Page, delayFirst = false) {
  let count = 0
  const requests: Record<string, unknown>[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let body: unknown
    if (path === '/api/health') body = { status: 'ok', worker_connected: false, model_configured: false, sandbox_verified: false, catalog_count: 1, version: 'test-fixture' }
    else if (path === '/api/sessions') body = { session_id: fixture.session_id }
    else if (path === '/api/photos') body = { photo_id: 'fixture-photo', width: 1, height: 1 }
    else if (path === '/api/requests' && route.request().method() === 'POST') {
      requests.push(route.request().postDataJSON())
      count++
      body = { request_id: 'fixture-request-' + count, status: 'queued', poll_url: '/api/requests/fixture-request-' + count }
      await route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify(body) }); return
    } else if (path.startsWith('/api/requests/')) {
      const id = path.split('/').pop()!
      if (delayFirst && id === 'fixture-request-1') await new Promise(resolve => setTimeout(resolve, 1200))
      body = { request_id: id, status: 'completed', result: { ...fixture, request_id: id, speech_text: id === 'fixture-request-2' ? 'Development fixture: NEW answer only.' : fixture.speech_text }, error_code: null }
    } else { await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error_code: 'FIXTURE_NOT_FOUND' }) }); return }
    try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }) } catch { /* aborted obsolete test request */ }
  })
  return requests
}
async function choosePhoto(page: Page) {
  await page.locator('input[type=file]').first().setInputFiles({ name: 'development-fixture.png', mimeType: 'image/png', buffer: png })
}
test('actual local service proxy, mobile layout, and capability observation', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'What caught your eye?' })).toBeVisible()
  await expect(page.locator('.leaflet-control-attribution')).toContainText('OpenStreetMap')
  await page.getByRole('button', { name: 'Seochon demo', exact: true }).click()
  await expect(page.locator('.map-caption')).toContainText('Demo starting point')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Connection', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.locator('.health-list')).toContainText('Service reachable')
  const health = await page.request.get('/api/health')
  expect(health.ok()).toBe(true)
  const healthData = await health.json()
  expect(healthData.status).toBe('ok')
  const capabilities = await page.evaluate(() => ({ speechRecognition: Boolean((window as unknown as Record<string, unknown>).SpeechRecognition || (window as unknown as Record<string, unknown>).webkitSpeechRecognition), speechSynthesis: 'speechSynthesis' in window, secureContext: window.isSecureContext }))
  await testInfo.attach('actual-browser-capabilities', { body: JSON.stringify({ ...capabilities, health: healthData }), contentType: 'application/json' })
  await page.getByRole('button', { name: 'Close status' }).click()
  await page.screenshot({ path: 'tests/artifacts/' + testInfo.project.name + '-actual-ui.png', fullPage: true })
  expect(errors).toEqual([])
})
test('named fixture: upload, scoped request, evidence, sentence and download', async ({ page }) => {
  const requests = await fixtureApi(page)
  await page.goto('/')
  await choosePhoto(page)
  await page.getByRole('button', { name: 'Seochon demo', exact: true }).click()
  await page.getByRole('textbox', { name: /Ask your little local guide/ }).fill('Fixture question about this food')
  await page.getByRole('button', { name: 'Explore with me' }).click()
  await expect(page.locator('.answer-text')).toContainText('Development fixture')
  expect(requests[0]).toMatchObject({ photo_id: 'fixture-photo', dataset_mode: 'real_place', location: { origin: 'selected', lat: 37.579, lng: 126.973 }, radius_m: 1000 })
  await expect(page.locator('.korean-card')).toContainText('고기 육수')
  await page.getByText('Sources & what we considered', { exact: false }).click()
  await expect(page.locator('.evidence-item')).toContainText('Example')
  await expect(page.getByRole('link', { name: 'JSON', exact: true })).toHaveAttribute('href', '/api/results/fixture-request-1/download?format=json')
})
test('named fixture: new question supersedes the delayed old result', async ({ page }) => {
  const requests = await fixtureApi(page, true)
  await page.goto('/')
  await choosePhoto(page)
  await page.getByRole('textbox', { name: /Ask your little local guide/ }).fill('First fixture question')
  await page.getByRole('button', { name: 'Explore with me' }).click()
  await expect.poll(() => requests.length).toBe(1)
  await page.getByRole('textbox', { name: /Ask your little local guide/ }).fill('Second fixture question')
  await page.getByRole('button', { name: 'Ask a new question' }).click()
  await expect(page.locator('.answer-text')).toHaveText('Development fixture: NEW answer only.')
  await page.waitForTimeout(1300)
  await expect(page.locator('.answer-text')).toHaveText('Development fixture: NEW answer only.')
})
test('unsupported speech, invalid photo, Korean toggle and tile failure have visible states', async ({ page }) => {
  await fixtureApi(page)
  await page.addInitScript(() => { Object.defineProperty(window, 'SpeechRecognition', { value: undefined }); Object.defineProperty(window, 'webkitSpeechRecognition', { value: undefined }) })
  await page.route('https://tile.openstreetmap.org/**', route => route.abort())
  await page.goto('/')
  await page.getByRole('button', { name: 'Ask by voice' }).click()
  await expect(page.getByText('Voice input is unavailable in this browser. Please type your question.')).toBeVisible()
  await page.locator('input[type=file]').first().setInputFiles({ name: 'invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('invalid') })
  await expect(page.getByText('Choose a JPG or PNG photo smaller than 8 MB.')).toBeVisible()
  await expect(page.locator('.map-error')).toContainText('could not load')
  await page.getByRole('button', { name: '한글', exact: true }).click()
  await expect(page.getByRole('heading', { name: '어떤 음식이 눈에 들어왔나요?' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'ko')
})
test('server outage stays an error rather than a synthetic answer', async ({ page }) => {
  await page.route('**/api/**', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error_code: 'UNAVAILABLE' }) }))
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Reconnect', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Explore with me' })).toBeDisabled()
  await expect(page.locator('.result-panel')).toHaveCount(0)
})
