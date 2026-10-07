// Standalone live QA. Not discovered by the fixture-based Playwright test suite.
// Run only after root GO; the default preparation path opens no browser/network.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, expect } from '@playwright/test'

const repo = fileURLToPath(new URL('../../../', import.meta.url))
const args = process.argv.slice(2)
function option(name, fallback) {
  const index = args.indexOf(name)
  if (index < 0) return fallback
  assert(args[index + 1] && !args[index + 1].startsWith('--'), `${name} needs a value`)
  return args[index + 1]
}
const baseURL = option('--base-url', 'http://127.0.0.1:5173')
const goReference = option('--root-go', '')
const primaryOnly = args.includes('--primary-only')
const maxInferenceRequests = primaryOnly ? 3 : 5
const photoPath = path.join(repo, 'data/samples/heritage-demo.jpg')
const manifest = JSON.parse(await readFile(path.join(repo, 'data/samples/heritage-license.json'), 'utf8'))
const expectedPlaceId = option('--place-id', 'local:gwanghwamun')
const localCatalog = JSON.parse(await readFile(path.join(repo, 'data/catalog.json'), 'utf8'))
assert(localCatalog.places.some(place => place.place_id === expectedPlaceId && place.kind === 'heritage'), 'Expected cultural place must be in the preserved catalog')
const photoSHA = createHash('sha256').update(await readFile(photoPath)).digest('hex')
assert.equal(manifest.license, 'CC0-1.0')
assert.equal(photoSHA, manifest.sha256, 'CC0 sample bytes must match the preserved manifest')

const selectors = {
  photo: 'input[type="file"]:not([capture])',
  question: '#question',
  submit: '.ask-button',
  confirmation: '.place-confirmation button',
  anchor: '#place-anchor',
  place: '.place-list .place-card',
  current: '.result-panel:not(.is-stale)',
  map: '.map-canvas',
  menus: '.menus-grid .menu-card',
  culture: '.culture-card',
  korean: '.korean-card p[lang="ko"]',
  sources: 'details.sources',
  html: '.download-link[href$="format=html"]',
  json: '.download-link[href$="format=json"]',
}
if (!goReference) {
  console.log(JSON.stringify({
    status: 'PREPARED_WAITING_FOR_ROOT_GO', baseURL, photo_sha256: photoSHA, expected_place_id: expectedPlaceId, catalog_version: localCatalog.catalog_version, selectors,
    sequence: primaryOnly
      ? ['CC0 cultural photo; no assumed location', 'explicit user cultural-place confirmation or catalog selection', 'nearby meal suggestion', 'actual HTML + JSON downloads / desktop + mobile screenshots']
      : ['CC0 cultural photo; no assumed location', 'confirm an actual returned candidate, or explicitly select the known catalog place when absent; record these separately', 'nearby meal / restaurant selection / menu', 'restaurant-to-history follow-up', 'HTML + JSON downloads / desktop + mobile screenshots'],
    inference_requests: 0,
    journey_scope: primaryOnly ? 'PRIMARY_ONLY' : 'FULL',
    max_inference_requests_after_go: maxInferenceRequests,
    backup_video: 'Silent actual UI recording into .runtime/qa-ui-real/<run>/raw-video; context closes on success or failure to flush it.',
    prerequisite: 'Root confirms the current worker deployment/readiness and an idle queue, then issues GO. A command flag does not establish that approval.',
  }, null, 2))
  process.exit(0)
}

const runDirectory = path.join(repo, '.runtime/qa-ui-real', new Date().toISOString().replace(/[:.]/g, '-'))
await mkdir(runDirectory, { recursive: true })
const report = {
  status: 'RUNNING', started_at: new Date().toISOString(), root_go_reference: goReference,
  base_url: baseURL, photo_sha256: photoSHA, source_revision: manifest.source_revision,
  journey_scope: primaryOnly ? 'PRIMARY_ONLY' : 'FULL',
  photo_scope: manifest.capture_context,
  expected_place_id: expectedPlaceId,
  inference_steps: [], ui_errors: [], checks: {}, downloads: {}, screenshots: {},
  timeline: [],
  video: { directory: 'raw-video', silent: true, flushed: false, scope: 'Actual browser UI with the explicitly identified archive-photo upload; not on-site camera footage, audio evidence or automatic frame execution.' },
  voice: 'Actual Android Korean and English speech input: both PASS by the latest user report. Android TTS remains unverified; earlier audible TTS was separately user-reported without establishing this Android check. This headless journey does not retest physical audio or automatic frame analysis.',
  camera: 'Android rear-camera preview and a captured photo remaining after camera stop: PASS by user report. This journey uploads the preserved archive sample, not a camera capture.',
  mobile: 'Same live result resized to390px; layout inspection only, no extra inference or physical voice test.',
  limits: ['UI and actual broker results only; OpenShell policy/deny and deployed worker revision require separate runtime evidence.'],
}
if (primaryOnly) report.limits.push('Primary demo only: restaurant-menu and reverse history steps are not run. The previous failed full journey is preserved separately; this run does not establish that those failures are fixed.')
let browser
let context
let page
let failure
const accepted = []
const terminal = new Map()
const apiErrors = []
const pending = new Set()
let health
let catalog
let uploadCount = 0
let uploadedPhotoId

async function until(predicate, description, timeout = 70000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    assert.equal(apiErrors.length, 0, `Observed API failure: ${apiErrors.join(', ')}`)
    const value = predicate()
    if (value) return value
    if (page && await page.locator('.error-panel').isVisible()) throw new Error(`Visible UI error during ${description}`)
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  throw new Error(`Timed out: ${description}; no automatic retry was sent`)
}

async function liveStep(label, action, expectedAnchor = null) {
  assert(accepted.length < maxInferenceRequests, `Maximum ${maxInferenceRequests} sequential inference requests for this journey`)
  const before = accepted.length
  const started = Date.now()
  await action()
  await until(() => accepted.length > before, `${label}: accepted request`, 25000)
  assert.equal(accepted.length, before + 1, 'One UI action must create only one request')
  const request = accepted[before]
  const step = { label, request_id: request.id, status: 'WAITING', action_started_at: new Date(started).toISOString(), accepted_at: new Date(request.acceptedAt).toISOString(), accepted_after_ms: request.acceptedAt - started }
  report.inference_steps.push(step)
  assert.equal(request.body.dataset_mode, 'real_place')
  assert.equal(request.body.interaction_mode, 'ask', 'This journey uses deliberate UI questions, not automatic observation')
  if (expectedAnchor) {
    assert.equal(request.body.location?.origin, 'selected')
    assert.equal(request.body.location?.lat, expectedAnchor.lat)
    assert.equal(request.body.location?.lng, expectedAnchor.lng)
    assert.equal(request.body.confirmed_place_id, expectedAnchor.place_id)
    assert.equal(request.body.confirmed_shop_id, expectedAnchor.kind === 'restaurant' ? expectedAnchor.place_id : null)
  } else {
    assert.equal(request.body.location, null, 'Photo identity must not become assumed GPS')
    assert.equal(request.body.confirmed_place_id, null)
    assert.equal(request.body.confirmed_shop_id, null)
  }
  assert.equal(request.body.photo_id, uploadedPhotoId, 'Every step must retain the actual uploaded photo')
  const job = await until(() => terminal.get(request.id), `${label}: terminal response`, Math.max(1, 70000 - (Date.now() - request.acceptedAt))).catch(error => {
    step.status = 'WAIT_FAILED'
    step.finished_at = new Date().toISOString()
    step.elapsed_ms = Date.now() - started
    throw error
  })
  step.status = job.status
  step.terminal_observed_at = new Date().toISOString()
  step.elapsed_ms = Date.now() - started
  assert.equal(job.status, 'completed', `${label}: ${job.error_code || job.status}`)
  assert(job.result && job.result.status !== 'failed', `${label}: invalid or failed result`)
  assert.equal(job.result.request_id, request.id)
  assert.equal(job.result.dataset_mode, 'real_place')
  await expect(page.locator(selectors.current)).toBeVisible()
  await expect(page.locator(selectors.json)).toHaveAttribute('href', `/api/results/${encodeURIComponent(request.id)}/download?format=json`)
  assert.equal(accepted.length, before + 1, 'No background request should supersede this result')
  step.ui_ready_at = new Date().toISOString()
  step.finished_at = step.ui_ready_at
  step.elapsed_ms = Date.now() - started
  return job.result
}

async function screenshotLayouts() {
  for (const [name, viewport] of Object.entries({ desktop: { width: 1440, height: 1000 }, mobile: { width: 390, height: 844 } })) {
    await page.setViewportSize(viewport)
    await page.locator('header').scrollIntoViewIfNeeded()
    await page.evaluate(() => document.fonts.ready)
    await page.waitForTimeout(400)
    report.checks[`${name}_overflow`] = await page.evaluate(() => ({
      viewport: innerWidth, document: document.documentElement.scrollWidth,
      pass: document.documentElement.scrollWidth <= innerWidth + 1,
    }))
    const file = `${name}${failure ? '-failed' : ''}.png`
    await page.screenshot({ path: path.join(runDirectory, file), fullPage: true })
    report.screenshots[name] = file
    report.timeline.push({ event: `${name}_screenshot`, at: new Date().toISOString(), viewport })
  }
}

try {
  browser = await chromium.launch({ channel: 'chrome', headless: true })
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true, recordVideo: { dir: path.join(runDirectory, 'raw-video'), size: { width: 1440, height: 1000 } } })
  page = await context.newPage()
  report.video.page_created_at = new Date().toISOString()
  page.setDefaultTimeout(15000)
  page.on('pageerror', error => report.ui_errors.push(error.message))
  // Observe responses already fetched by the real UI. No interception or extra API polling.
  page.on('response', response => {
    const pathname = new URL(response.url()).pathname
    if (!['/api/health', '/api/catalog', '/api/photos', '/api/requests'].includes(pathname) && !pathname.startsWith('/api/requests/')) return
    const task = (async () => {
      if (!response.ok()) { apiErrors.push(`${response.status()} ${pathname}`); return }
      const data = await response.json()
      if (pathname === '/api/health') health = data
      else if (pathname === '/api/catalog') catalog = data
      else if (pathname === '/api/photos') { uploadCount += 1; uploadedPhotoId = data.photo_id }
      else if (pathname === '/api/requests' && response.request().method() === 'POST') {
        accepted.push({ id: data.request_id, body: response.request().postDataJSON(), acceptedAt: Date.now() })
      } else if (['completed', 'failed', 'superseded'].includes(data.status)) terminal.set(data.request_id, data)
    })()
    pending.add(task)
    task.catch(() => apiErrors.push(`Unreadable response ${pathname}`)).finally(() => pending.delete(task))
  })
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' })
  await until(() => health, 'UI health response', 20000)
  report.health = health
  assert.equal(health.worker_connected, true, 'Worker must be connected before any inference')
  // Hosted API configuration and sandbox metadata do not gate a self-hosted worker.
  await until(() => catalog, 'UI catalog response', 20000)
  const culturalPlace = catalog.places.find(place => place.place_id === expectedPlaceId && place.kind === 'heritage')
  assert(culturalPlace, 'Expected cultural place must be in the actual browser catalog')
  report.catalog_version = catalog.catalog_version
  report.catalog_anchor = culturalPlace
  await page.getByLabel('Read answers aloud', { exact: true }).uncheck()
  await page.locator(selectors.photo).setInputFiles(photoPath)
  await expect(page.locator('.photo-preview img')).toBeVisible()
  await expect(page.locator(selectors.anchor)).toHaveValue('')
  await page.locator(selectors.question).fill('What cultural place might this photo show? Ask me to confirm its identity before selecting a location. Explain the uncertainty and do not identify people.')
  await expect(page.locator(selectors.submit)).toBeEnabled()
  let result = await liveStep('Cultural photo identification without assumed location', () => page.locator(selectors.submit).click())
  assert.equal(uploadCount, 1, 'One actual photo upload expected')
  assert.equal(result.scene.confirmed_place_id ?? null, null, 'Photo alone must not confirm a place')
  const candidateData = result.scene.place_candidates?.find(place => place.id === expectedPlaceId)
  report.checks.place_candidate_inference = {
    response_status: result.status,
    returned_candidate_ids: (result.scene.place_candidates ?? []).map(place => place.id),
    expected_candidate_returned: Boolean(candidateData),
    note: 'A returned candidate is a model proposal, not verified photo identity. Catalog selection is user supplied.',
  }
  report.checks.place_confirmation = { status: 'PENDING', method: candidateData ? 'USER_CONFIRMS_RETURNED_CANDIDATE' : 'USER_EXPLICIT_CATALOG_SELECTION', selected_place_id: expectedPlaceId }
  await expect(page.locator(selectors.anchor)).toHaveValue('')
  await page.screenshot({ path: path.join(runDirectory, 'desktop-first-response.png'), fullPage: true })
  report.screenshots.first_response = 'desktop-first-response.png'
  report.timeline.push({ event: 'first_response_before_user_place_selection', at: new Date().toISOString(), expected_candidate_returned: Boolean(candidateData) })
  if (result.status !== 'need_confirmation') report.limits.push('The first photo response did not request confirmation; the subsequent place selection is explicitly user supplied, not evidence that model uncertainty handling passed.')
  if (candidateData) {
    const candidate = page.locator(selectors.confirmation).filter({ hasText: candidateData.name_ko })
    await expect(candidate).toHaveCount(1)
    result = await liveStep('User confirms an actual returned candidate and selects its catalog point', () => candidate.click(), culturalPlace)
  } else {
    report.limits.push('The expected cultural place was not returned as a candidate. The user explicitly selects the known archive-photo place from the existing catalog; this does not establish model recognition success.')
    await expect(page.locator(selectors.anchor)).toBeVisible()
    result = await liveStep('User explicitly selects the known cultural place from the catalog; no inferred candidate', () => page.locator(selectors.anchor).selectOption(expectedPlaceId), culturalPlace)
  }
  assert.equal(result.scene.confirmed_place_id, expectedPlaceId)
  await expect(page.locator(selectors.anchor)).toHaveValue(expectedPlaceId)
  await expect(page.locator('.map-caption')).toContainText(culturalPlace.name)
  assert(result.claims.some(claim => claim.scope === 'culture'), 'Actual cultural context required')
  await expect(page.locator(selectors.culture)).toBeVisible()
  await expect(page.locator('.anchor-picker')).toContainText('main gate of Gyeongbokgung')
  report.checks.place_confirmation.status = 'EXERCISED'
  await page.screenshot({ path: path.join(runDirectory, 'desktop-cultural-context.png'), fullPage: true })

  result = await liveStep('Cultural starting point to nearby meal', () => page.getByRole('button', { name: 'Find a meal nearby', exact: true }).click(), culturalPlace)
  const meal = result.places.find(place => place.kind === 'restaurant')
  assert(meal, 'Nearby meal follow-up must actually provide a restaurant')
  const restaurant = catalog.places.find(place => place.place_id === meal.place_id && place.kind === 'restaurant')
  assert(restaurant, 'Restaurant must match the actual approved catalog')
  await expect(page.locator('.place-marker').first()).toBeVisible()
  await expect(page.locator('.leaflet-tile-loaded').first()).toBeVisible()
  await expect(page.locator('.leaflet-control-attribution')).toContainText('OpenStreetMap')
  if (primaryOnly) {
    report.checks.culture_to_meal = { heritage_id: expectedPlaceId, restaurant_id: restaurant.place_id, request_id: result.request_id }
    report.checks.restaurant_menu = 'NOT_RUN_PRIMARY_SCOPE'
    report.checks.meal_to_culture = 'NOT_RUN_PRIMARY_SCOPE'
    await page.screenshot({ path: path.join(runDirectory, 'desktop-primary-nearby-meal.png'), fullPage: true })
  } else {
  result = await liveStep('Select the nearby restaurant and inspect its menu', () => page.locator(selectors.place).filter({ hasText: restaurant.name }).click(), restaurant)
  assert.equal(result.scene.confirmed_place_id, restaurant.place_id)
  assert.equal(result.scene.confirmed_shop_id, restaurant.place_id)
  assert(result.menus.length > 0, 'Actual menu cards required')
  await expect(page.locator(selectors.menus).first()).toBeVisible()
  report.checks.culture_to_meal = { heritage_id: expectedPlaceId, restaurant_id: restaurant.place_id, menu_count: result.menus.length }
  if (result.order_ko) {
    await expect(page.locator(selectors.korean)).toHaveText(result.order_ko)
    report.checks.korean_phrase = result.order_ko
  }
  await page.screenshot({ path: path.join(runDirectory, 'desktop-nearby-meal.png'), fullPage: true })
  result = await liveStep('Restaurant starting point to nearby history', () => page.getByRole('button', { name: 'Explore nearby history', exact: true }).click(), restaurant)
  assert(result.places.some(place => place.kind === 'heritage'), 'History follow-up must actually provide a heritage place')
  await expect(page.locator('.place-kind').filter({ hasText: 'History & culture' }).first()).toBeVisible()
  report.checks.meal_to_culture = { selected_start_id: restaurant.place_id, suggested_heritage_ids: result.places.filter(place => place.kind === 'heritage').map(place => place.place_id) }
  }
  if (result.order_ko) {
    await expect(page.locator(selectors.korean)).toHaveText(result.order_ko)
    report.checks.korean_phrase = result.order_ko
  }
  if (!report.checks.korean_phrase) report.limits.push('No Korean staff phrase was returned in this journey; its live interaction remains unverified.')
  await page.locator(`${selectors.sources} summary`).click()
  await expect(page.locator('.evidence-item').first()).toBeVisible()
  report.limits.push('Visible culture/menu/source checks do not prove factual accuracy, current opening/admission status, ingredient safety or source entailment; root reviews the saved response.')

  for (const format of ['html', 'json']) {
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator(selectors[format]).click()])
    assert.equal(await download.failure(), null, `${format} download must succeed`)
    const filename = `result.${format}`
    await download.saveAs(path.join(runDirectory, filename))
    const bytes = await readFile(path.join(runDirectory, filename))
    assert(bytes.length > 0, `${format} must be nonempty`)
    if (format === 'json') {
      const saved = JSON.parse(bytes.toString('utf8'))
      assert.equal(saved.request_id, result.request_id)
      assert.equal(saved.order_ko, result.order_ko)
      assert.equal(saved.dataset_mode, 'real_place')
    } else {
      assert(/<html[\s>]/i.test(bytes.toString('utf8')), 'HTML document required')
      if (result.order_ko) assert(bytes.toString('utf8').includes(result.order_ko), 'HTML must contain the current Korean phrase')
    }
    report.downloads[format] = { file: filename, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'), request_id: result.request_id, saved_at: new Date().toISOString() }
  }
  await screenshotLayouts()
  assert(report.checks.desktop_overflow.pass && report.checks.mobile_overflow.pass, 'No horizontal viewport overflow')
  assert.equal(report.ui_errors.length, 0, 'No uncaught browser JavaScript errors')
  assert.equal(apiErrors.length, 0, 'No observed API errors')
  report.status = primaryOnly ? 'PASS_PRIMARY_UI_JOURNEY' : report.checks.korean_phrase ? 'PASS_UI_JOURNEY' : 'REVIEW_REQUIRED'
} catch (error) {
  failure = error
  report.status = 'FAILED'
  report.failure = error.message
  if (page) await screenshotLayouts().catch(() => {})
} finally {
  const video = page?.video()
  try {
    await context?.close()
    if (video) { report.video.file = path.relative(runDirectory, await video.path()).replaceAll('\\', '/'); report.video.flushed = true }
    report.video.context_closed_at = new Date().toISOString()
  } catch (error) {
    report.video.flush_error = error.message
    report.limits.push('Backup video flush failed; do not claim a complete video artifact.')
  }
  await browser?.close().catch(() => {})
  await Promise.allSettled([...pending])
  report.finished_at = new Date().toISOString()
  report.inference_request_count = accepted.length
  await writeFile(path.join(runDirectory, 'receipt.json'), JSON.stringify(report, null, 2) + '\n', 'utf8')
  console.log(JSON.stringify({ status: report.status, directory: runDirectory, inference_requests: accepted.length, failure: report.failure || null }))
}
if (failure || !['PASS_UI_JOURNEY', 'PASS_PRIMARY_UI_JOURNEY'].includes(report.status)) process.exitCode = 1
