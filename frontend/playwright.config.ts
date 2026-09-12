import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  // Couverture de code e2e (monocart-coverage-reports) — cf. tests/e2e/fixtures.ts.
  globalSetup: './tests/e2e/global.setup.ts',
  globalTeardown: './tests/e2e/global-teardown.ts',
  use: {
    baseURL: 'http://localhost:5173',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          executablePath: process.env.PW_CHROMIUM_PATH,
        },
      },
    },
  ],
  webServer: {
    command: 'npm run dev -- --port 5173',
    port: 5173,
    reuseExistingServer: !process.env.CI,
  },
})
