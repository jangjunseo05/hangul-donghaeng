import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/browser', timeout: 20000, fullyParallel: false, workers: 1,
  use: { baseURL: 'http://127.0.0.1:5173', channel: 'chrome', headless: true, screenshot: 'only-on-failure' },
  projects: [{ name: 'desktop', use: { viewport: { width: 1280, height: 1000 } } }, { name: 'mobile', use: { viewport: { width: 390, height: 844 } } }],
  reporter: 'list',
})
