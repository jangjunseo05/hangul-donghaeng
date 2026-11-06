import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import resultStory from '../../../shared/examples/result.story.json' with { type: 'json' }

// U4: automatic companion shows its latest observation as a one-line caption over the viewfinder.
// Contract-shaped mock API + synthetic camera; not a live broker.
const SHOTS = process.env.HD_SHOTS_DIR
test.use({ deviceScaleFactor: 2 })

async function syntheticCamera(page: Page) {
  // Same synthetic camera as camera-culture.spec.ts (solid canvas stream, visible page).
  await page.addInitScript(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => {
      const canvas = document.createElement('canvas')
      canvas.width = 640; canvas.height = 480
      const context = canvas.getContext('2d')!
      context.fillStyle = '#6f875d'; context.fillRect(0, 0, 640, 480)
      const stream = canvas.captureStream(10)
      setInterval(() => { context.fillStyle = '#6f875d'; context.fillRect(0, 0, 640, 480) }, 100)
      return stream
    } })
  })
}

async function mockApi(page: Page, options: { holdObserve?: boolean } = {}) {
  let release = false
  const requests: { interaction_mode?: string }[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/sessions') return route.fulfill({ json: { session_id: 's-live' } })
    if (path === '/api/health') return route.fulfill({ json: { status: 'ok', worker_connected: true, model_configured: true, sandbox_verified: false, sandbox_evidence: { scope: 'stored_deployment_evidence', runtime: 'OpenShell 0.1.2', worker: 'hangul-worker-12', captured_at: '2026-10-07T06:56:03.227157+00:00', policy_hash: '55f944108939719c8089e13bdf68de06e004ef80ca3bf24a0ec878b6bebedaca', policy_loaded: true, boundary_verdict: 'PASS', boundary_sandbox: 'hangul-matrix-01', boundary_checks_passed: 11, boundary_checks_total: 11 }, catalog_count: 3, version: 'caption-fixture' } })
    if (path === '/api/catalog') return route.fulfill({ json: { catalog_count: 0, scope_label: 'fixture', catalog_version: 'fixture', places: [] } })
    if (path === '/api/tts') return route.fulfill({ status: 503, json: { error_code: 'TTS_UNAVAILABLE' } })
    if (path === '/api/photos') return route.fulfill({ json: { photo_id: 'p-' + Date.now(), width: 640, height: 480, purpose: 'observe' } })
    if (path === '/api/requests' && route.request().method() === 'POST') {
      requests.push(route.request().postDataJSON())
      return route.fulfill({ status: 202, json: { request_id: 'r-live', status: 'queued', poll_url: '/api/requests/r-live' } })
    }
    if (path.startsWith('/api/requests/')) {
      const trace = [
        { t_ms: 0, kind: 'broker', name: 'request_accepted', ok: true, detail: 'photo normalized, EXIF removed' },
        { t_ms: 180, kind: 'sandbox', name: 'job_claimed', ok: true, detail: null },
        { t_ms: 220, kind: 'stage', name: 'observing', ok: true, detail: null },
        ...(release ? [{ t_ms: 3900, kind: 'tool', name: 'landmark_candidates', ok: true, detail: '1 candidates' }, { t_ms: 4100, kind: 'stage', name: 'writing', ok: true, detail: null }, { t_ms: 6400, kind: 'check', name: 'grounding_check', ok: true, detail: '1 sources · 0 conflicts' }, { t_ms: 6500, kind: 'broker', name: 'result_saved', ok: true, detail: null }] : []),
      ]
      if (!release || (options.holdObserve && requests.at(-1)?.interaction_mode === 'observe')) return route.fulfill({ json: { request_id: 'r-live', status: 'running', stage: 'observing', trace, result: null, error_code: null } })
      const result = { ...resultStory, request_id: 'r-live', session_id: 's-live', dataset_mode: 'real_place', status: 'ready', places: [],
        speech_text: 'This is Gwanghwamun, the main gate of Gyeongbokgung Palace. Look for the haechi statues guarding it.',
        next_question: 'Would you like to hear about the guard ceremony?',
        scene: { ...resultStory.scene, observed_place_name: 'Gwanghwamun', place_candidates: [], confirmed_place_id: null } }
      return route.fulfill({ json: { request_id: 'r-live', status: 'completed', stage: null, trace, result, error_code: null } })
    }
    return route.fulfill({ status: 404, json: { detail: 'Not Found' } })
  })
  return { requests, release: () => { release = true } }
}

async function ribbon(page: Page) {
  await page.evaluate(() => {
    const still = document.createElement('style')
    still.textContent = '*,*:before,*:after{transition:none!important;animation:none!important}'
    document.head.appendChild(still)
    const tag = document.createElement('div')
    tag.textContent = 'MOCK DATA · UI draft'
    tag.setAttribute('popover', 'manual')
    tag.setAttribute('style', 'position:fixed;inset:58px 8px auto auto;margin:0;border:0;padding:3px 10px;border-radius:999px;background:#b5452f;color:#fff;font:700 10px/1.4 system-ui;pointer-events:none')
    document.body.appendChild(tag)
    ;(tag as HTMLElement & { showPopover(): void }).showPopover()
  })
}

test('U4: automatic observation streams into a one-line caption; tapping it opens the answer', async ({ page }, info) => {
  await syntheticCamera(page)
  const api = await mockApi(page)
  await page.goto('/')
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.getByRole('button', { name: 'Start camera', exact: true }).click()
  await expect.poll(() => page.locator('video').evaluate((video: HTMLVideoElement) => video.videoWidth > 0 && video.readyState >= 2)).toBe(true)
  // Positive control: with the camera live and nothing pending, the stage chip is shown.
  await expect(page.locator('.stage-status')).toBeVisible()
  await page.clock.install()
  await page.getByRole('checkbox', { name: 'Automatic companion' }).check()
  for (let step = 0; step < 20 && api.requests.length === 0; step++) { await page.clock.runFor(1000); await page.waitForTimeout(40) }
  expect(api.requests[0]?.interaction_mode).toBe('observe')

  // Watching: the caption carries the live phase and the sheet stays down over the camera.
  const caption = page.locator('.live-caption')
  await expect(caption).toHaveClass(/is-working/)
  await expect(caption).toContainText('Looking at your photo')
  await expect(page.locator('.answer-sheet')).toHaveClass(/is-collapsed/)
  if (SHOTS) { await ribbon(page); await page.screenshot({ path: `${SHOTS}/${info.project.name}-u4-watching.png` }) }

  // A proposal opens the sheet as before.
  api.release()
  for (let step = 0; step < 10; step++) { await page.clock.runFor(1000); await page.waitForTimeout(40) }
  await expect(page.locator('.answer-sheet')).toHaveClass(/is-open/)
  await expect(page.locator('.result-panel')).toContainText('Gwanghwamun')

  // Collapsing it leaves the answer as a caption with its latency; a tap brings the details back.
  await page.locator('.answer-sheet .sheet-grab').click()
  await expect(caption).toContainText('Gwanghwamun — This is Gwanghwamun, the main gate of Gyeongbokgung Palace.')
  await expect(caption.locator('.live-ms')).toHaveText('6.5s')
  // Waiting for the user's answer: one paused message (the notice), and a neutral caption dot.
  await expect(page.locator('.automatic-notice')).toContainText('Paused so you can answer')
  await expect(page.locator('.stage-status')).toHaveCount(0)
  await expect(caption).toHaveClass(/is-paused/)
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${info.project.name}-u4-caption.png` })
  await caption.click()
  await expect(page.locator('.answer-sheet')).toHaveClass(/is-open/)
  await expect(caption).toHaveCount(0)
})

test('U4: an automatic observation never collapses an answer the user asked for', async ({ page }) => {
  await syntheticCamera(page)
  const api = await mockApi(page, { holdObserve: true })
  api.release()
  await page.goto('/')
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.getByRole('button', { name: 'Start camera', exact: true }).click()
  await expect.poll(() => page.locator('video').evaluate((video: HTMLVideoElement) => video.videoWidth > 0 && video.readyState >= 2)).toBe(true)
  await page.clock.install()
  await page.getByRole('checkbox', { name: 'Automatic companion' }).check()
  await page.locator('#question').fill('What is this gate?')
  await page.locator('.ask-button').click()
  for (let step = 0; step < 6; step++) { await page.clock.runFor(1000); await page.waitForTimeout(40) }
  await expect(page.locator('.answer-sheet')).toHaveClass(/is-open/)
  const asked = api.requests.length
  for (let step = 0; step < 40 && api.requests.length === asked; step++) { await page.clock.runFor(1000); await page.waitForTimeout(40) }
  expect(api.requests.at(-1)?.interaction_mode).toBe('observe')
  await page.clock.runFor(2000); await page.waitForTimeout(100)
  // The observation is still running (held by the mock): the asked answer stays open.
  await expect(page.locator('.answer-sheet')).toHaveClass(/is-open/)
})
