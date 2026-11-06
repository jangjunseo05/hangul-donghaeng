import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

// F2 source review + F3 sandbox probe against contract-shaped mocks (shared/api-contract.md). Not a live worker.
const SHOTS = process.env.HD_SHOTS_DIR
test.use({ deviceScaleFactor: 2 })
const evidence = {
  scope: 'stored_deployment_evidence', runtime: 'OpenShell 0.1.2', worker: 'hangul-worker-12', captured_at: '2026-10-07T06:56:03.227157+00:00',
  policy_hash: '55f944108939719c8089e13bdf68de06e004ef80ca3bf24a0ec878b6bebedaca', policy_loaded: true, boundary_verdict: 'PASS', boundary_sandbox: 'hangul-matrix-01', boundary_checks_passed: 11, boundary_checks_total: 11,
  policy_read_only: ['/app', '/usr', '/lib', '/lib64', '/etc', '/proc', '/dev/urandom', '/var/log'], policy_read_write: ['/tmp', '/dev/null'],
  policy_network_allow: ['GET :8000/api/health', 'GET :8000/worker/jobs/next', 'GET :8000/worker/photos/*', 'GET :8001/v1/models', 'POST :8000/worker/fail', 'POST :8000/worker/results', 'POST :8000/worker/search', 'POST :8001/v1/chat/completions'],
}
const files = [
  { id: 'input:001', path: '01-haeon-palace-notice-2026.md', sha256: '819690ee94d5a17e' + '0'.repeat(48), bytes: 612, as_of: '2026-09-01' },
  { id: 'input:002', path: '02-travel-blog-2019.md', sha256: 'c535ad3fa38ad82a' + '0'.repeat(48), bytes: 344, as_of: '2019-05-12' },
  { id: 'input:003', path: '03-heritage-guide-2024.md', sha256: '737f339f88733da7' + '0'.repeat(48), bytes: 401, as_of: '2024-03-15' },
  { id: 'input:004', path: '04-seaside-food-list.md', sha256: '8106b645114d77bd' + '0'.repeat(48), bytes: 288, as_of: '2025-07-02' },
  { id: 'input:005', path: '05-visitor-forum-post.txt', sha256: 'b3fc2675097ce21d' + '0'.repeat(48), bytes: 356, as_of: null },
]
const review = {
  status: 'answered', question: 'When is Haeon Palace open?', condition: 'Visiting on a Tuesday', input_label: 'review-demo', verified_input: true,
  sources: [
    { ...files[0], verdict: 'used', reason: null, note: null },
    { ...files[1], verdict: 'used', reason: null, note: 'A 2019 personal blog; the 2026 official notice supersedes its closing day.' },
    { ...files[2], verdict: 'used', reason: null, note: null },
    { ...files[3], verdict: 'excluded', reason: 'irrelevant', note: null },
    { ...files[4], verdict: 'excluded', reason: 'untrusted_instruction', note: null },
  ].map(({ bytes: _bytes, ...source }) => source),
  claims: [{ text: 'Haeon Palace is closed on Tuesdays, so a Tuesday visit is not possible; it is open 09:00–18:00 on other days.', source_ids: ['input:001'], quotes: [{ source_id: 'input:001', text: '해온궁은 매주 화요일 휴궁합니다.' }] }],
  conflicts: [{ source_ids: ['input:001', 'input:002'], quotes: [{ source_id: 'input:001', text: '해온궁은 매주 화요일 휴궁합니다.' }, { source_id: 'input:002', text: '해온궁은 매주 월요일 휴궁이라' }], reason: 'The closing day differs.', resolution: 'Follow the 2026 management office notice.' }],
  unknowns: ['Whether a public holiday falls on your Tuesday.'],
}
const ev = (t_ms: number, kind: string, name: string, ok = true, detail: string | null = null) => ({ t_ms, kind, name, ok, detail })
const reviewTrace = [ev(0, 'broker', 'request_accepted'), ev(150, 'sandbox', 'job_claimed'), ev(200, 'stage', 'observing'), ev(5200, 'tool', 'review_sources', true, '3 used · 2 excluded'), ev(5300, 'stage', 'writing'), ev(9800, 'check', 'grounding_check', true, '1 sources · 1 conflicts'), ev(9950, 'broker', 'result_saved')]
type Attempt = { id: string; observed: string; detail: string | null; broker_received: number | null }
const attempts = (rows: [string, string, string | null, number | null][]): Attempt[] => rows.map(([id, observed, detail, broker_received]) => ({ id, expected: 'denied', observed, detail, broker_received }) as Attempt)
const BLOCKED = attempts([['read_outside_allowlist', 'denied', 'EACCES', null], ['write_code_dir', 'denied', 'EROFS', null], ['egress_unlisted_host', 'denied', 'ConnectError', null], ['broker_unlisted_path', 'denied', '403', 0]])
const LOCAL = attempts([['read_outside_allowlist', 'denied', 'ENOENT', null], ['write_code_dir', 'allowed', null, null], ['egress_unlisted_host', 'error', 'ConnectError', null], ['broker_unlisted_path', 'allowed', '200', 1]])

async function mockApi(page: Page, probe: { attempts: Attempt[]; run_context: string; canary?: boolean } = { attempts: BLOCKED, run_context: 'openshell' }) {
  let reviewPolls = 0, probePolls = 0
  const posted: Record<string, unknown>[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path === '/api/sessions') return route.fulfill({ json: { session_id: 's-lab' } })
    if (path === '/api/health') return route.fulfill({ json: { status: 'ok', worker_connected: true, model_configured: true, sandbox_verified: false, sandbox_evidence: evidence, catalog_count: 6, version: 'lab-fixture' } })
    if (path === '/api/catalog') return route.fulfill({ json: { catalog_count: 0, scope_label: 'fixture', catalog_version: 'fixture', places: [] } })
    if (path === '/api/reviews/inputs') return route.fulfill({ json: { input_label: 'review-demo', sources: files } })
    if (path === '/api/reviews' && method === 'POST') { posted.push(route.request().postDataJSON()); return route.fulfill({ status: 202, json: { request_id: 'rv-1', poll_url: '/api/reviews/rv-1' } }) }
    if (path === '/api/reviews/rv-1') {
      reviewPolls++
      const done = reviewPolls > 2
      return route.fulfill({ json: { request_id: 'rv-1', status: done ? 'completed' : 'running', trace: done ? reviewTrace : reviewTrace.slice(0, 4), result: done ? review : null, error_code: null } })
    }
    if (path === '/api/sandbox-probe' && method === 'POST') return route.fulfill({ status: 202, json: { request_id: 'pb-1', poll_url: '/api/sandbox-probe/pb-1' } })
    if (path === '/api/sandbox-probe/pb-1') {
      probePolls++
      const done = probePolls > 1
      const trace = [ev(0, 'broker', 'request_accepted'), ev(120, 'sandbox', 'job_claimed'), ...probe.attempts.map((attempt, i) => ev(400 + i * 300, 'sandbox', 'probe_' + attempt.id, attempt.observed === 'denied', attempt.detail)), ...(probe.canary ? [ev(1300, 'broker', 'canary_received', false)] : [])]
      return route.fulfill({ json: { request_id: 'pb-1', status: done ? 'completed' : 'running', trace, result: done ? { run_context: probe.run_context, finished_at: '2026-11-06T08:30:00Z', attempts: probe.attempts } : null, error_code: null } })
    }
    return route.fulfill({ status: 404, json: { detail: 'Not Found' } })
  })
  return posted
}
async function shot(page: Page, name: string, project: string, crop?: string) {
  if (!SHOTS) return
  await page.evaluate(() => {
    if (!document.getElementById('shot-still')) { const still = document.createElement('style'); still.id = 'shot-still'; still.textContent = '*,*:before,*:after{transition:none!important;animation:none!important}'; document.head.appendChild(still) }
    document.getElementById('shot-ribbon')?.remove()
    const tag = document.createElement('div')
    tag.id = 'shot-ribbon'; tag.textContent = 'MOCK DATA · UI draft'; tag.setAttribute('popover', 'manual')
    tag.setAttribute('style', 'position:fixed;inset:58px 8px auto auto;margin:0;border:0;padding:3px 10px;border-radius:999px;background:#b5452f;color:#fff;font:700 10px/1.4 system-ui;pointer-events:none')
    document.body.appendChild(tag); (tag as HTMLElement & { showPopover(): void }).showPopover()
  })
  await page.screenshot({ path: `${SHOTS}/${project}-${name}.png` })
  if (crop) await page.locator(crop).first().screenshot({ path: `${SHOTS}/${project}-${name}-crop.png` })
}

test('F3: live block test shows "OpenShell blocked all 4" only on four denials and zero canary hits', async ({ page }, info) => {
  await mockApi(page)
  await page.goto('/')
  await page.locator('.sandbox-badge').click()
  const card = page.locator('.probe-card')
  await card.getByRole('button', { name: 'Run test' }).click()
  await expect(card.locator('.probe-verdict.blocked')).toContainText('OpenShell blocked all 4 attempts')
  await expect(card.locator('.probe-row.denied')).toHaveCount(4)
  await expect(card.locator('.probe-row').nth(0)).toContainText('Worker-reported · EACCES')
  await expect(card.locator('.probe-row').nth(3)).toContainText('broker observed: received 0')
  await expect(card.locator('.probe-meta')).toContainText('(a label, not proof)')
  await card.scrollIntoViewIfNeeded()
  await shot(page, 'f3-blocked', info.project.name, '.probe-card')
})

test('F3: a local worker is shown plainly as not sandboxed, even if it calls itself openshell', async ({ page }, info) => {
  await mockApi(page, { attempts: LOCAL, run_context: 'openshell' })
  await page.goto('/')
  await page.locator('.sandbox-badge').click()
  const card = page.locator('.probe-card')
  await card.getByRole('button', { name: 'Run test' }).click()
  await expect(card.locator('.probe-verdict.not_sandboxed')).toContainText('Not sandboxed: a forbidden action was allowed')
  await expect(card.locator('.probe-row.allowed')).toHaveCount(2)
  await expect(card.locator('.probe-row').nth(3)).toContainText('received 1')
  await card.scrollIntoViewIfNeeded()
  await shot(page, 'f3-local', info.project.name, '.probe-card')
})

test('F3: worker denials with a canary hit read as an evidence mismatch, never as blocked', async ({ page }) => {
  await mockApi(page, { attempts: BLOCKED, run_context: 'openshell', canary: true })
  await page.goto('/')
  await page.locator('.sandbox-badge').click()
  await page.locator('.probe-card').getByRole('button', { name: 'Run test' }).click()
  await expect(page.locator('.probe-verdict.mismatch')).toContainText('evidence mismatch')
  await expect(page.locator('.probe-verdict.blocked')).toHaveCount(0)
})

test('F2: source review lists inputs, takes an extra condition and shows per-source verdicts', async ({ page }, info) => {
  const posted = await mockApi(page)
  await page.goto('/')
  await page.locator('.sandbox-badge').click()
  await page.getByRole('button', { name: 'Open source review mode' }).click()
  const screen = page.locator('.review-screen')
  await expect(screen.locator('.review-banner')).toContainText('Fictional practice material')
  await expect(screen.locator('.review-inputs li')).toHaveCount(5)
  await screen.getByLabel('Extra condition (optional)').fill('Visiting on a Tuesday')
  await shot(page, 'f2-inputs', info.project.name)
  await screen.getByRole('button', { name: 'Review the sources' }).click()
  await expect(screen.locator('.reasoning.is-live')).toBeVisible()
  await expect(screen.locator('.review-status.answered')).toContainText('Answered from the sources it kept')
  expect(posted[0]).toMatchObject({ session_id: 's-lab', condition: 'Visiting on a Tuesday' })
  await expect(screen.locator('.review-unverified')).toHaveCount(0)
  const sources = screen.locator('.review-source')
  await expect(sources).toHaveCount(5)
  await expect(sources.nth(0)).toContainText('cited')
  await expect(sources.nth(1)).toContainText("Model's reason · not an official verdict")
  await expect(sources.nth(3)).toContainText('Irrelevant')
  await expect(sources.nth(4)).toHaveClass(/danger/)
  await expect(sources.nth(4)).toContainText('never sent to the model')
  await expect(screen.locator('.review-conflict .conflict-vs')).toContainText('02-travel-blog-2019.md')
  await expect(screen.locator('.download-link')).toHaveCount(2)
  await expect(screen.locator('.reasoning .reasoning-head')).not.toHaveCSS('position', 'sticky')
  await screen.locator('.reasoning').evaluate(element => element.scrollIntoView({ block: 'start' }))
  await shot(page, 'f2-result', info.project.name)
  await sources.nth(0).scrollIntoViewIfNeeded()
  await shot(page, 'f2-sources', info.project.name, '.review-sources')
  await screen.getByRole('button', { name: 'Back' }).click()
  await expect(screen).toHaveCount(0)
})

test('F2/F3 live: the local broker lists the demo inputs and accepts a probe (no worker)', async ({ page }) => {
  test.skip(process.env.HD_LIVE_BROKER !== '1', 'needs the local broker on :8000')
  await page.goto('/#review')
  await expect(page.locator('.review-inputs li')).toHaveCount(5)
  await expect(page.locator('.review-banner')).toBeVisible()
})

test('F2: the overlay takes focus, a tab tap closes it, and #review stops a running camera', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => {
      const canvas = document.createElement('canvas'); canvas.width = 320; canvas.height = 240
      canvas.getContext('2d')!.fillRect(0, 0, 320, 240)
      const stream = canvas.captureStream(5)
      ;(window as unknown as { tracks: MediaStreamTrack[] }).tracks = stream.getTracks()
      return stream
    } })
  })
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Start camera', exact: true }).click()
  await expect.poll(() => page.evaluate(() => (window as unknown as { tracks?: MediaStreamTrack[] }).tracks?.[0]?.readyState)).toBe('live')
  await page.evaluate(() => { location.hash = '#review' })
  await expect(page.locator('.review-screen')).toBeVisible()
  await expect.poll(() => page.evaluate(() => (window as unknown as { tracks: MediaStreamTrack[] }).tracks[0].readyState)).toBe('ended')
  await expect(page.getByRole('button', { name: 'Back' })).toBeFocused()
  await expect(page.locator('.look-screen')).toBeHidden()
  await page.getByRole('tab', { name: 'Routes' }).click()
  await expect(page.locator('.review-screen')).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Routes' })).toHaveAttribute('aria-selected', 'true')
})
