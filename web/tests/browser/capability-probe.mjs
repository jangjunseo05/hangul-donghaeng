import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await page.goto('http://127.0.0.1:5173/')
  const capabilities = await page.evaluate(() => ({ recognition: Boolean(window.SpeechRecognition || window.webkitSpeechRecognition), synthesis: 'speechSynthesis' in window, voices: window.speechSynthesis?.getVoices().map(v => v.lang) || [], secureContext: isSecureContext }))
  await page.getByRole('button', { name: 'Ask by voice', exact: true }).click()
  await page.waitForTimeout(3500)
  const notices = await page.locator('.inline-notice').allTextContents()
  const stillListening = await page.getByRole('button', { name: 'Stop listening', exact: true }).count()
  if (stillListening) await page.getByRole('button', { name: 'Stop listening', exact: true }).click()
  const input = page.getByRole('textbox', { name: /Ask your little local guide/ })
  await input.fill('Editable transcript check')
  await input.fill('Edited transcript check')
  const editable = await input.inputValue() === 'Edited transcript check'
  const health = await (await page.request.get('http://127.0.0.1:5173/api/health')).json()
  const report = { captured_at: new Date().toISOString(), browser: 'installed Chrome, headless, no fake microphone', capabilities, actual_voice_notice: notices, still_listening_after_3500ms: Boolean(stillListening), typed_transcript_editable: editable, note: 'Typed editing is verified; spoken recognition, audible TTS and physical-device permissions are not verified.', health }
  await mkdir('tests/artifacts', { recursive: true })
  await writeFile('tests/artifacts/runtime-capabilities.json', JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
} finally { await browser.close() }
