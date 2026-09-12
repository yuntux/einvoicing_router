import { test as base, type Page } from '@playwright/test'
import MCR from 'monocart-coverage-reports'
import coverageOptions from './mcr.config'

// Étend le `test` de base avec une fixture automatique qui démarre/arrête la
// couverture V8 (JS + CSS) sur chaque page du test, puis l'ajoute au rapport
// global — un seul point d'import à changer dans chaque spec (`./fixtures` au
// lieu de `@playwright/test`) pour que la couverture soit mesurée.
export const test = base.extend<{ autoCoverageFixture: string }>({
  autoCoverageFixture: [
    async ({ context }, use) => {
      const isChromium = test.info().project.name === 'chromium'

      const handlePageEvent = async (page: Page) => {
        await Promise.all([
          page.coverage.startJSCoverage({ resetOnNavigation: false }),
          page.coverage.startCSSCoverage({ resetOnNavigation: false }),
        ])
      }

      // La Coverage API de Playwright n'existe que pour Chromium.
      if (isChromium) {
        context.on('page', handlePageEvent)
      }

      await use('autoCoverageFixture')

      if (isChromium) {
        context.off('page', handlePageEvent)
        const coverageList = await Promise.all(
          context.pages().map(async (page) => {
            const jsCoverage = await page.coverage.stopJSCoverage()
            const cssCoverage = await page.coverage.stopCSSCoverage()
            return [...jsCoverage, ...cssCoverage]
          }),
        )
        const mcr = MCR(coverageOptions)
        await mcr.add(coverageList.flat())
      }
    },
    { scope: 'test', auto: true },
  ],
})

export { expect } from '@playwright/test'
