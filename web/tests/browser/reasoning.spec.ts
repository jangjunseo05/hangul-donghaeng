import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import resultStory from '../../../shared/examples/result.story.json' with { type: 'json' }

// Contract-shaped mock (shared/api-contract.md "Agent trace", health.sandbox_evidence). Not a live broker.
const SHOTS = process.env.HD_SHOTS_DIR
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0QAAAABJRU5ErkJggg==', 'base64')
// Same values as the broker's real stored evidence (docs/runtime/evidence: worker-12, 2026-10-07), so mock shots match the deck.
const evidence = {
  scope: 'stored_deployment_evidence', runtime: 'OpenShell 0.1.2', worker: 'hangul-worker-12', captured_at: '2026-10-07T06:56:03.227157+00:00',
  policy_hash: '55f944108939719c8089e13bdf68de06e004ef80ca3bf24a0ec878b6bebedaca', policy_loaded: true, boundary_verdict: 'PASS', boundary_sandbox: 'hangul-matrix-01', boundary_checks_passed: 11, boundary_checks_total: 11,
  policy_read_only: ['/app', '/usr', '/lib', '/lib64', '/etc', '/proc', '/dev/urandom', '/var/log'], policy_read_write: ['/tmp', '/dev/null'],
  policy_network_allow: ['GET :8000/api/health', 'GET :8000/worker/jobs/next', 'GET :8000/worker/photos/*', 'GET :8001/v1/models', 'POST :8000/worker/fail', 'POST :8000/worker/results', 'POST :8000/worker/search', 'POST :8001/v1/chat/completions'],
}
const ev = (t_ms: number, kind: string, name: string, ok = true, detail: string | null = null) => ({ t_ms, kind, name, ok, detail })
const fullTrace = [
  ev(0, 'broker', 'request_accepted', true, 'photo normalized, EXIF removed'), ev(210, 'sandbox', 'job_claimed'), ev(260, 'stage', 'observing'),
  ev(4880, 'stage', 'matching'), ev(4950, 'tool', 'landmark_candidates', true, '2 candidates'), ev(5300, 'tool', 'catalog_search', true, '1 results'),
  ev(5720, 'tool', 'wikipedia', true, '2 records'), ev(5900, 'tool', 'osm_live_search', false, 'RADIUS_MISMATCH'), ev(6010, 'stage', 'writing'),
  ev(11840, 'check', 'grounding_check', true, '3 sources · 1 conflicts'), ev(12060, 'broker', 'result_saved'),
]
const result = {
  ...resultStory, request_id: 'r-trace', session_id: 's-trace', captured_at: '2026-11-06T09:00:00Z',
  evidence: [
    { id: 'visitkorea:gwanghwamun', source: 'https://korean.visitkorea.or.kr/detail/ms_detail.do?cotid=gwanghwamun', as_of: '2026-10-07', type: 'document', dataset_id: 'catalog' },
    { id: 'wikipedia:Gwanghwamun', source: 'https://en.wikipedia.org/wiki/Gwanghwamun', as_of: '2025-03', type: 'document', dataset_id: 'public' },
    { id: 'seoul:notice-2016', source: 'https://www.seoul.go.kr/notice/2016-guard', as_of: '2016-08-16', type: 'document', dataset_id: 'catalog' },
  ],
  conflicts: [{ evidence_ids: ['seoul:notice-2016', 'visitkorea:gwanghwamun'], decision: 'Guard ceremony at 10:00 and 14:00 (2026 schedule)', reason: 'The 2016 notice lists an older timetable; the 2026 tourism page is newer.' }],
}

async function mockApi(page: Page, options: { holdAt?: number } = {}) {
  let polls = 0
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/sessions') return route.fulfill({ json: { session_id: 's-trace' } })
    if (path === '/api/health') return route.fulfill({ json: { status: 'ok', worker_connected: true, model_configured: true, sandbox_verified: false, sandbox_evidence: evidence, catalog_count: 3, version: 'trace-fixture' } })
    if (path === '/api/catalog') return route.fulfill({ json: { catalog_count: 0, scope_label: 'fixture', catalog_version: 'fixture', places: [] } })
    if (path === '/api/tts') return route.fulfill({ status: 503, json: { error_code: 'TTS_UNAVAILABLE' } })
    if (path === '/api/photos') return route.fulfill({ json: { photo_id: 'p-1', width: 1, height: 1 } })
    if (path === '/api/requests' && route.request().method() === 'POST') return route.fulfill({ status: 202, json: { request_id: 'r-trace', status: 'queued', poll_url: '/api/requests/r-trace' } })
    if (path.startsWith('/api/requests/')) {
      polls++
      const shown = Math.min(fullTrace.length, options.holdAt ?? polls * 4)
      const done = shown >= fullTrace.length && options.holdAt === undefined
      const stage = [...fullTrace.slice(0, shown)].reverse().find(event => event.kind === 'stage')?.name ?? null
      return route.fulfill({ json: { request_id: 'r-trace', status: done ? 'completed' : 'running', stage: done ? null : stage, trace: fullTrace.slice(0, shown), result: done ? result : null, error_code: null } })
    }
    return route.fulfill({ status: 404, json: { detail: 'Not Found' } })
  })
}
async function ask(page: Page) {
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.locator('input[type=file]').first().setInputFiles({ name: 'p.png', mimeType: 'image/png', buffer: png })
  await page.locator('#question').fill('What is this gate?')
  await page.locator('.ask-button').click()
}
test.use({ deviceScaleFactor: 2 })
/** Screenshots carry a visible ribbon: this data is a contract-shaped mock, not a live run. */
async function shot(page: Page, name: string, project: string, crop?: string, label = 'MOCK DATA · UI draft') {
  if (!SHOTS) return
  await page.evaluate(text => {
    if (!document.getElementById('shot-still')) {
      const still = document.createElement('style')
      still.id = 'shot-still'
      still.textContent = '*,*:before,*:after{transition:none!important;animation:none!important}'
      document.head.appendChild(still)
    }
    document.getElementById('shot-ribbon')?.remove()
    const ribbon = document.createElement('div')
    ribbon.id = 'shot-ribbon'
    ribbon.textContent = text
    ribbon.setAttribute('popover', 'manual')
    ribbon.setAttribute('style', 'position:fixed;inset:58px 8px auto auto;margin:0;border:0;white-space:nowrap;padding:3px 10px;border-radius:999px;background:#b5452f;color:#fff;font:700 10px/1.4 system-ui;letter-spacing:.04em;pointer-events:none')
    document.body.appendChild(ribbon)
    ;(ribbon as HTMLElement & { showPopover(): void }).showPopover()
  }, label)
  await page.screenshot({ path: `${SHOTS}/${project}-${name}.png` })
  if (!crop) return
  // Crops: a tall viewport so the sheet does not clip the element (still the same layout width).
  const size = page.viewportSize()!
  await page.setViewportSize({ width: size.width, height: 2400 })
  await page.locator(crop).first().screenshot({ path: `${SHOTS}/${project}-${name}-crop.png` })
  await page.setViewportSize(size)
}

test('U2: OpenShell badge opens the stored effective-policy summary', async ({ page }, info) => {
  await mockApi(page)
  await page.goto('/')
  const badge = page.locator('.sandbox-badge')
  await expect(badge).toHaveClass(/ok/)
  await expect(badge).toContainText('OpenShell sandbox')
  await expect(badge).toContainText('Nemotron 12B VL')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await shot(page, 'u2-topbar', info.project.name, '.top-bar')
  await badge.click()
  const card = page.locator('.sandbox-card')
  await expect(card).toContainText('11/11 PASS')
  await expect(card).toContainText('Stored policy for hangul-worker-12')
  await expect(card).toContainText('Network allowed (8)')
  await expect(card).toContainText('Everything not listed was denied by default.')
  await expect(card).toContainText('55f944108939')
  await expect(card).toContainText('probe sandbox hangul-matrix-01')
  await expect(card).toContainText('not a live check')
  await expect(page.locator('.session-blocked')).toContainText('Broker rejected 0 app calls this session')
  await shot(page, 'u2-policy', info.project.name, '.sandbox-card')
})

test('U1/U5: live timeline advances by real phases, no fixed estimate', async ({ page }, info) => {
  await mockApi(page, { holdAt: 8 })
  await page.goto('/')
  await ask(page)
  const live = page.locator('.reasoning.is-live')
  await expect(live).toBeVisible()
  await expect(live.locator('.reasoning-step.now .reasoning-step-head b')).toHaveText('Tools')
  await expect(live.locator('.reasoning-step.done')).toHaveCount(2)
  await expect(live).toContainText('blocked')
  await expect(live.locator('[aria-current="step"]')).toContainText('Tools')
  await expect(page.locator('.working-panel')).not.toContainText('Usually about')
  await shot(page, 'u1-live', info.project.name)
})

test('U1/U3: answer keeps the timeline, conflicts and freshness in view', async ({ page }, info) => {
  await mockApi(page)
  await page.goto('/')
  await ask(page)
  const timeline = page.locator('.result-panel .reasoning')
  await expect(timeline).toBeVisible()
  await expect(timeline.locator('.reasoning-total')).toHaveText(/^\d+(\.\d)?s$/)
  await expect(timeline.locator('.reasoning-step.done')).toHaveCount(5)
  await expect(timeline.locator('.reasoning-step').nth(0).locator('.reasoning-ms')).toHaveText('4.9s')
  await expect(timeline).toContainText('3 sources kept')
  await expect(timeline).toContainText('1 result')
  await expect(timeline).not.toContainText('1 results')
  await expect(timeline).toContainText('1 conflict resolved')
  const trust = page.locator('.trust-card')
  await expect(trust.locator('.conflict-vs')).toContainText('seoul.go.kr')
  await expect(trust.locator('.conflict-vs')).toContainText('korean.visitkorea.or.kr')
  await expect(trust).toContainText('Kept: Guard ceremony')
  await expect(trust.locator('.fresh-badge.fresh')).toHaveText('<1 mo ago')
  await expect(trust.locator('.fresh-badge.aging')).toHaveText('20 mo ago')
  await expect(trust.locator('.fresh-badge.stale')).toHaveText('10 yr ago')
  await timeline.scrollIntoViewIfNeeded()
  await shot(page, 'u1-result-timeline', info.project.name, '.result-panel .reasoning')
  await expect(trust).toContainText('broker-checked')
  await expect(trust.locator('.src-type').first()).toHaveText('Document')
  await trust.scrollIntoViewIfNeeded()
  await shot(page, 'u3-trust', info.project.name, '.trust-card')
  await page.locator('.sandbox-badge').click()
  await expect(page.locator('.session-blocked')).toContainText('Broker rejected 1 app call this session')
  await shot(page, 'u2-policy-after-ask', info.project.name, '.status-dialog')
})

test('U6: (i) tips are described, toggle by tap and close with Escape', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const button = page.locator('.idle-privacy .info-tip button')
  await expect(button).toHaveAccessibleDescription(/live preview stays on this device/)
  await button.click()
  await expect(page.locator('.info-tip-bubble')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.info-tip-bubble')).toHaveCount(0)
  await button.click()
  await page.locator('.stage-idle h2').click()
  await expect(page.locator('.info-tip-bubble')).toHaveCount(0)
})

test('U2 live: badge and policy card from the local broker (stored evidence, no worker)', async ({ page }, info) => {
  // Real /api/health through the Vite proxy. Run with HD_LIVE_BROKER=1 and the broker on 127.0.0.1:8000.
  test.skip(process.env.HD_LIVE_BROKER !== '1', 'needs the local broker on :8000')
  await page.goto('/')
  const badge = page.locator('.sandbox-badge')
  // No worker on the local broker: the badge must not look like a live sandbox.
  await expect(badge).not.toHaveClass(/ok/)
  await expect(badge).toContainText('Stored evidence · no worker')
  const label = 'LOCAL BROKER · stored evidence (no worker)'
  await shot(page, 'live-u2-topbar', info.project.name, '.top-bar', label)
  await badge.click()
  const card = page.locator('.sandbox-card')
  await expect(card).toContainText('not a live check')
  await expect(card).toContainText('hangul-worker-12')
  await shot(page, 'live-u2-policy', info.project.name, '.sandbox-card', label)
})
