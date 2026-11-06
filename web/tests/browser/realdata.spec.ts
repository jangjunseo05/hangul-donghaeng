import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { userInfo } from 'node:os'
import { fileURLToPath } from 'node:url'

// Real-data screenshots against a running broker + worker (no route mocks). Opt-in only:
//   HD_REALDATA=1 HD_BASE=http://127.0.0.1:8000 HD_SHOTS_DIR=... HD_RIBBON='LOCAL WORKER · substitute model · no sandbox'
// The ribbon states the real run context; it is required so a shot cannot pass for an OpenShell deployment.
const SHOTS = process.env.HD_SHOTS_DIR
const RIBBON = process.env.HD_RIBBON ?? ''
const photoPath = fileURLToPath(new URL('../../../data/samples/heritage-demo.jpg', import.meta.url))
test.skip(process.env.HD_REALDATA !== '1' || !/LOCAL/i.test(RIBBON), 'real broker + worker only: set HD_REALDATA=1 and HD_RIBBON')
test.use({ deviceScaleFactor: 2, baseURL: process.env.HD_BASE ?? 'http://127.0.0.1:8000' })
test.describe.configure({ timeout: 240000 })

async function shot(page: Page, name: string, project: string, crop?: string, padTop = 0) {
  if (!SHOTS) return
  // Ribbon is an in-flow strip right under the top bar: the layout makes room for it, so it covers nothing.
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
    ribbon.setAttribute('style', 'flex:none;display:flex;align-items:center;height:22px;padding:0 12px;background:#7a4a12;color:#fff;font:700 10px/1 system-ui;letter-spacing:.06em;white-space:nowrap;overflow:hidden')
    ribbon.textContent = text
    document.querySelector('.top-bar')!.after(ribbon)
  }, RIBBON)
  const column = (await page.locator('.top-bar').boundingBox())!
  const size = page.viewportSize()!
  // Desktop: clip to the app column so the frame is not mostly empty margin.
  await page.screenshot({ path: `${SHOTS}/${project}-real-${name}.png`, clip: { x: column.x, y: 0, width: column.width, height: size.height } })
  await page.locator('#shot-ribbon').evaluate(element => element.remove())
  if (!crop) return
  // Tall viewport so long cards are not clipped; camera crops (padTop) keep the real viewport so the feed is not rescaled.
  if (!padTop) await page.setViewportSize({ width: size.width, height: 2400 })
  // Crops carry the run context in-frame: a strip in the page color right under the element hides whatever follows it.
  const target = page.locator(crop).first()
  await target.scrollIntoViewIfNeeded()
  const box = (await target.boundingBox())!
  await page.evaluate(([text, left, top, width]) => {
    const strip = document.createElement('div')
    strip.id = 'shot-crop-tag'
    strip.setAttribute('popover', 'manual')
    strip.setAttribute('style', `position:fixed;left:${left}px;top:${top}px;width:${width}px;height:28px;margin:0;border:0;padding:6px 0 0;background:#ffffff;overflow:hidden`)
    const pill = document.createElement('span')
    pill.textContent = text
    pill.setAttribute('style', 'display:inline-block;white-space:nowrap;padding:2px 8px;border-radius:999px;background:#7a4a12;color:#fff;font:700 9.5px/1.4 system-ui;letter-spacing:.04em')
    strip.appendChild(pill)
    document.body.appendChild(strip)
    ;(strip as HTMLElement & { showPopover(): void }).showPopover()
  }, [RIBBON, box.x, box.y + box.height, box.width] as const)
  const top = Math.max(0, box.y - padTop)
  await page.screenshot({ path: `${SHOTS}/${project}-real-${name}-crop.png`, clip: { x: box.x, y: top, width: box.width, height: box.y - top + box.height + 28 } })
  await page.locator('#shot-crop-tag').evaluate(element => element.remove())
  await page.setViewportSize(size)
}

/** Fails the shot if anything secret-looking or a personal path is visible. */
async function assertClean(page: Page) {
  const text = await page.evaluate(() => document.body.innerText)
  expect(text).not.toMatch(/nvapi-|Bearer |WORKER_TOKEN|NVIDIA_API_KEY|C:[\\/]Users|\/Users\/|\/home\/|\/mnt\/c|\\\\wsl|\bsk-[A-Za-z0-9]|ghp_/i)
  expect(text.toLowerCase()).not.toContain(userInfo().username.toLowerCase())
}

async function badgeIsLocal(page: Page) {
  const badge = page.locator('.sandbox-badge')
  await expect(badge).toContainText('Local worker')
  await expect(badge).not.toHaveClass(/\bok\b/)
}

test('real: ask about a photo → live timeline, finished timeline, trust card', async ({ page }, info) => {
  await page.goto('/')
  await badgeIsLocal(page)
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.locator('input[type=file]').first().setInputFiles(photoPath)
  await page.locator('#question').fill('What is this place?')
  await page.locator('.ask-button').click()
  const live = page.locator('.reasoning.is-live')
  await expect(live).toBeVisible({ timeout: 15000 })
  // Live shot only if the run is still in flight once a phase has finished (fast runs skip it).
  await expect(page.locator('.reasoning.is-live .reasoning-step.done, .result-panel:not(.is-stale), .error-panel').first()).toBeVisible({ timeout: 120000 })
  if (await live.count() && await live.locator('.reasoning-step.done').count()) {
    await assertClean(page)
    await shot(page, 'u1-live', info.project.name)
  }
  await expect(page.locator('.result-panel:not(.is-stale), .error-panel').first()).toBeVisible({ timeout: 180000 })
  await expect(page.locator('.error-panel')).toHaveCount(0)
  const confirm = page.locator('.place-confirmation > div button')
  if (await confirm.count()) {
    await assertClean(page)
    await shot(page, 'confirm', info.project.name)
    await confirm.first().click()
    await expect(page.locator('.reasoning.is-live')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.reasoning.is-live')).toHaveCount(0, { timeout: 180000 })
    await expect(page.locator('.error-panel')).toHaveCount(0)
  }
  const done = page.locator('.reasoning:not(.is-live)')
  await expect(done).toBeVisible()
  await assertClean(page)
  await done.evaluate(element => element.scrollIntoView({ block: 'start' }))
  await shot(page, 'u1-result', info.project.name, '.reasoning:not(.is-live)')
  // A run that answered from no sources is not a usable shot (the retry gets a fresh model run).
  const trust = page.locator('.trust-card')
  await expect(trust.locator('.trust-sources li').first()).toBeVisible()
  await trust.scrollIntoViewIfNeeded()
  await shot(page, 'u3-trust', info.project.name, '.trust-card')
})

test('real: F2 source review on the fictional inputs', async ({ page }, info) => {
  await page.goto('/')
  await badgeIsLocal(page)
  await page.locator('.sandbox-badge').click()
  await page.getByRole('button', { name: 'Open source review mode' }).click()
  const screen = page.locator('.review-screen')
  await expect(screen.locator('.review-inputs li')).toHaveCount(5, { timeout: 15000 })
  await assertClean(page)
  await shot(page, 'f2-inputs', info.project.name)
  await screen.getByRole('button', { name: 'Review the sources' }).click()
  await expect(screen.locator('.review-result, .review-error, [role=alert]').first()).toBeVisible({ timeout: 180000 })
  await expect(screen.locator('.review-result')).toBeVisible()
  await assertClean(page)
  await screen.locator('.reasoning').evaluate(element => element.scrollIntoView({ block: 'start' }))
  await shot(page, 'f2-result', info.project.name)
  await screen.locator('.review-sources').scrollIntoViewIfNeeded()
  await shot(page, 'f2-sources', info.project.name, '.review-sources')
  if (await screen.locator('.review-conflict').count()) await shot(page, 'f2-conflict', info.project.name, '.review-conflict')
})

test('real: F3 live block test on a local worker shows "not sandboxed"', async ({ page }, info) => {
  await page.goto('/')
  await badgeIsLocal(page)
  await page.locator('.sandbox-badge').click()
  const card = page.locator('.probe-card')
  await card.getByRole('button', { name: 'Run test' }).click()
  await expect(card.locator('.probe-verdict, .probe-error').first()).toBeVisible({ timeout: 120000 })
  await expect(card.locator('.probe-verdict')).toHaveClass(/not_sandboxed/)
  await assertClean(page)
  await card.scrollIntoViewIfNeeded()
  await shot(page, 'f3-local', info.project.name, '.probe-card')
})

test('real: U4 caption from an automatic observation of the sample photo', async ({ page }, info) => {
  const dataUrl = 'data:image/jpeg;base64,' + readFileSync(photoPath).toString('base64')
  await page.addInitScript(src => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => {
      const canvas = document.createElement('canvas')
      canvas.width = 960; canvas.height = 720
      const context = canvas.getContext('2d')!
      const image = new Image()
      await new Promise(resolve => { image.onload = resolve; image.src = src })
      const draw = () => {
        const scale = Math.max(canvas.width / image.width, canvas.height / image.height)
        context.drawImage(image, (canvas.width - image.width * scale) / 2, (canvas.height - image.height * scale) / 2, image.width * scale, image.height * scale)
      }
      draw()
      setInterval(draw, 100)
      return canvas.captureStream(10)
    } })
  }, dataUrl)
  await page.goto('/')
  await badgeIsLocal(page)
  await page.getByRole('checkbox', { name: 'Read answers aloud' }).uncheck()
  await page.getByRole('button', { name: 'Start camera', exact: true }).click()
  await expect.poll(() => page.locator('video').evaluate((video: HTMLVideoElement) => video.videoWidth > 0 && video.readyState >= 2)).toBe(true)
  await page.getByRole('checkbox', { name: 'Automatic companion' }).check()
  const caption = page.locator('.live-caption')
  await expect(caption).toHaveClass(/is-working/, { timeout: 60000 })
  await assertClean(page)
  await shot(page, 'u4-watching', info.project.name)
  await expect(page.locator('.answer-sheet.is-open, .error-panel').first()).toBeVisible({ timeout: 180000 })
  await expect(page.locator('.error-panel')).toHaveCount(0)
  await page.locator('.answer-sheet .sheet-grab').click()
  await expect(caption).not.toHaveClass(/is-working/)
  await expect(caption.locator('.live-ms')).toBeVisible()
  await assertClean(page)
  // Include part of the camera frame above the caption so the crop explains itself.
  await shot(page, 'u4-caption', info.project.name, '.live-caption', 260)
  await page.getByRole('checkbox', { name: 'Automatic companion' }).uncheck()
})
