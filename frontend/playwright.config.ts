import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 120000,
  expect: { timeout: 15000 },
  workers: 1,
  retries: 0,
  use: { actionTimeout: 15000, baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 }, locale: 'en-US', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
})
