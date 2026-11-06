import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import resultStory from '../../../shared/examples/result.story.json' with { type: 'json' }

// NVIDIA theme guard: brand green is identity only. Sandbox/evidence states keep their own semantic colors,
// and a local or unlabeled worker never renders green. Fixture-driven (contract-shaped mocks), not a live run.
const SHOTS = process.env.HD_SHOTS_DIR
test.use({ deviceScaleFactor: 2 })
const BRAND = 'rgb(118, 185, 0)'
const VERIFIED_BG = 'rgb(233, 244, 236)'
const evidence = {
  scope: 'stored_deployment_evidence', runtime: 'OpenShell 0.1.2', worker: 'hangul-worker-12', captured_at: '2026-10-07T06:56:03.227157+00:00',
  policy_hash: '55f944108939719c8089e13bdf68de06e004ef80ca3bf24a0ec878b6bebedaca', policy_loaded: true, boundary_verdict: 'PASS', boundary_sandbox: 'hangul-matrix-01', boundary_checks_passed: 11, boundary_checks_total: 11,
  policy_read_only: ['/app', '/usr'], policy_read_write: ['/tmp'], policy_network_allow: ['GET :8000/api/health', 'POST :8001/v1/chat/completions'],
}
const ev = (t_ms: number, kind: string, name: string, ok = true, detail: string | null = null) => ({ t_ms, kind, name, ok, detail })
const trace = [ev(0, 'broker', 'request_accepted'), ev(200, 'sandbox', 'job_claimed'), ev(260, 'stage', 'observing'), ev(3000, 'stage', 'matching'),
  ev(3300, 'tool', 'osm_live_search', false, 'RADIUS_MISMATCH'), ev(3500, 'stage', 'writing'), ev(6000, 'check', 'grounding_check', true, '1 sources · 0 conflicts'), ev(6100, 'broker', 'result_saved')]
const denied = (id: string) => ({ id, observed: 'denied', detail: 'EACCES', broker_received: id === 'broker_unlisted_path' ? 0 : null })
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0QAAAABJRU5ErkJggg==', 'base64')

async function mockApi(page: Page, runContext: string | null) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path === '/api/sessions') return route.fulfill({ json: { session_id: 's-theme' } })
    if (path === '/api/health') return route.fulfill({ json: { status: 'ok', worker_connected: true, model_configured: false, sandbox_verified: false, sandbox_evidence: evidence, worker_model: runContext === null ? null : { id: 'nvidia/nemotron-nano-12b-v2-vl', thinking: 'default', run_context: runContext }, catalog_count: 3, version: 'theme-fixture' } })
    if (path === '/api/catalog') return route.fulfill({ json: { catalog_count: 0, scope_label: 'fixture', catalog_version: 'fixture', places: [] } })
    if (path === '/api/tts') return route.fulfill({ status: 503, json: { error_code: 'TTS_UNAVAILABLE' } })
    if (path === '/api/photos') return route.fulfill({ json: { photo_id: 'p-1', width: 1, height: 1 } })
    if (path === '/api/requests' && method === 'POST') return route.fulfill({ status: 202, json: { request_id: 'r-1', status: 'queued', poll_url: '/api/requests/r-1' } })
    if (path === '/api/requests/r-1') return route.fulfill({ json: { request_id: 'r-1', status: 'completed', stage: null, trace, result: { ...resultStory, request_id: 'r-1', session_id: 's-theme' }, error_code: null } })
    if (path === '/api/sandbox-probe' && method === 'POST') return route.fulfill({ status: 202, json: { request_id: 'pb-1', poll_url: '/api/sandbox-probe/pb-1' } })
    if (path === '/api/sandbox-probe/pb-1') return route.fulfill({ json: { request_id: 'pb-1', status: 'completed', trace: [ev(0, 'broker', 'request_accepted')], result: { run_context: 'openshell', finished_at: '2026-11-06T08:30:00Z', attempts: ['read_outside_allowlist', 'write_code_dir', 'egress_unlisted_host', 'broker_unlisted_path'].map(denied) }, error_code: null } })
    return route.fulfill({ status: 404, json: { detail: 'Not Found' } })
  })
}

/** Hue-based green check on a computed rgb()/rgba(): catches pale tints (#e9f4ec, #f4f7ef) as well as saturated greens. */
function isGreenish(css: string) {
  const parts = css.match(/[\d.]+/g)
  if (!parts || (parts.length === 4 && Number(parts[3]) === 0)) return false
  const [r, g, b] = parts.slice(0, 3).map(value => Number(value) / 255)
  const max = Math.max(r, g, b), min = Math.min(r, g, b), delta = max - min
  if (delta < 0.02) return false
  const l = (max + min) / 2, sat = delta / (1 - Math.abs(2 * l - 1))
  const hue = max === g ? 60 * ((b - r) / delta + 2) : max === r ? 60 * (((g - b) / delta) % 6) : 60 * ((r - g) / delta + 4)
  return hue >= 65 && hue <= 170 && sat > 0.15
}
/** Every text, background and border color on the element and its descendants. */
const paints = (locator: Locator) => locator.evaluate(root => [root, ...root.querySelectorAll('*')].flatMap(element => {
  const style = getComputedStyle(element)
  const name = `${element.tagName.toLowerCase()}.${(element.getAttribute('class') ?? '').trim().replace(/\s+/g, '.')}`
  return [style.color, style.backgroundColor, style.borderTopColor, style.borderLeftColor].map(value => ({ name, value }))
}))
async function expectNoGreen(locator: Locator) {
  const green = (await paints(locator)).filter(paint => isGreenish(paint.value)).map(paint => `${paint.name} ${paint.value}`)
  expect(green, 'green paint on a non-verified state').toEqual([])
}

test('theme: the green check itself recognizes pale and saturated greens, and not amber or grey', () => {
  for (const green of ['rgb(233, 244, 236)', 'rgb(244, 247, 239)', BRAND, 'rgb(63, 107, 0)', 'rgb(31, 77, 46)']) expect(isGreenish(green), green).toBe(true)
  for (const other of ['rgb(253, 245, 230)', 'rgb(122, 74, 18)', 'rgb(77, 77, 77)', 'rgb(255, 255, 255)', 'rgba(0, 0, 0, 0)', 'rgb(155, 58, 39)']) expect(isGreenish(other), other).toBe(false)
})

test('theme: brand fills are NVIDIA green with dark text; focus ring is visible', async ({ page }) => {
  await mockApi(page, 'openshell')
  await page.goto('/')
  await expect(page.locator('.look-fab')).toHaveCSS('background-color', BRAND)
  await expect(page.locator('.brand-mark')).toHaveCSS('color', 'rgb(20, 20, 20)')
  await page.locator('#question').focus()
  await page.keyboard.press('Shift+Tab')
  const focused = page.locator(':focus-visible')
  await expect(focused).toHaveCount(1)
  expect(await focused.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe('none')
})

test('theme: status colors stay semantic, never brand; local and unlabeled are never green', async ({ page }, info) => {
  test.setTimeout(60000)
  const tiles: { label: string; png: Buffer }[] = []
  // PASS: stored evidence passed + worker labels itself openshell -> forest green, not brand
  await mockApi(page, 'openshell')
  await page.goto('/')
  const badge = page.locator('.sandbox-badge')
  await expect(badge).toHaveClass(/\bok\b/)
  await expect(badge).toHaveCSS('background-color', VERIFIED_BG)
  await expect(badge).toHaveCSS('color', 'rgb(31, 77, 46)')
  if (SHOTS) tiles.push({ label: 'PASS · stored evidence + worker label "openshell" (forest green, ShieldCheck, "Self-reported")', png: await badge.screenshot() })
  // Brand: the main action, filled #76B900 with dark text
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.locator('input[type=file]').first().setInputFiles({ name: 'p.png', mimeType: 'image/png', buffer: png })
  await page.locator('#question').fill('What is this gate?')
  await expect(page.locator('.ask-button')).toHaveCSS('background-color', BRAND)
  await expect(page.locator('.ask-button')).toHaveCSS('color', 'rgb(20, 20, 20)')
  if (SHOTS) tiles.push({ label: 'Brand · NVIDIA green #76B900 fill, #141414 text — actions only, never a status', png: await page.locator('.ask-button').screenshot() })
  // Blocked: a broker-rejected tool call in the timeline is red
  await page.locator('.ask-button').click()
  const blockedTag = page.locator('.reasoning:not(.is-live) .shield-tag.bad').first()
  await expect(blockedTag).toBeVisible()
  await expect(blockedTag).toHaveCSS('color', 'rgb(155, 58, 39)')
  if (SHOTS) tiles.push({ label: 'Blocked call · broker rejected a tool call (red)', png: await page.locator('.reasoning:not(.is-live) .reasoning-step.has-blocked').first().screenshot() })
  // Live test verdict "blocked all 4": forest green like PASS, never brand
  await badge.click()
  await page.locator('.probe-card').getByRole('button', { name: 'Run test' }).click()
  const verdict = page.locator('.probe-verdict.blocked')
  await expect(verdict).toBeVisible()
  await expect(verdict).toHaveCSS('background-color', VERIFIED_BG)
  if (SHOTS) tiles.push({ label: 'Live test · OpenShell blocked all 4 (forest green, ShieldCheck, words)', png: await verdict.screenshot() })
  // Local (label local-dev) and unlabeled (no worker_model): badge and the whole stored-policy card carry no green.
  for (const context of ['local-dev', null]) {
    const other = await page.context().newPage()
    await mockApi(other, context)
    await other.goto('/')
    const otherBadge = other.locator('.sandbox-badge')
    await expect(otherBadge).toHaveClass(/local/)
    await expectNoGreen(otherBadge)
    if (SHOTS && context) tiles.splice(2, 0, { label: 'Local worker · no sandbox (amber, ShieldOff) — never green', png: await otherBadge.screenshot() })
    await otherBadge.click()
    await expect(other.locator('.policy-chips code').first()).toBeVisible()
    await expectNoGreen(other.locator('.sandbox-card'))
    await other.close()
  }
  if (!SHOTS) return
  const sheet = await page.context().newPage()
  await sheet.setViewportSize({ width: 760, height: 200 })
  await sheet.setContent(`<body style="margin:0;padding:22px;background:#fff;font:14px/1.4 system-ui;color:#141414">
    <h1 style="font-size:18px;margin:0 0 4px">Status colors under the NVIDIA theme</h1>
    <p style="margin:0 0 16px;color:#5f5f5f;font-size:12px">Rendered from fixtures (contract-shaped mocks), not a live run. Brand green #76B900 marks actions; it is never a status.</p>
    ${tiles.map(tile => `<figure style="margin:0 0 16px"><figcaption style="font-weight:650;font-size:12.5px;margin-bottom:6px">${tile.label}</figcaption><img style="max-width:100%;height:auto;zoom:.5" src="data:image/png;base64,${tile.png.toString('base64')}"></figure>`).join('')}
  </body>`)
  await sheet.screenshot({ path: `${SHOTS}/${info.project.name}-theme-status-compare.png`, fullPage: true })
  await sheet.close()
})
