import type { CoverageReportOptions } from 'monocart-coverage-reports'

// Couverture de code du parcours Playwright (e2e) — cf. README frontend.
// https://github.com/cenfun/monocart-coverage-reports
const coverageOptions: CoverageReportOptions = {
  name: 'Couverture e2e (Playwright)',
  outputDir: './coverage-reports',
  reports: ['v8', 'console-summary'],

  // Exclut les dépendances (node_modules) et le client HMR de Vite (`@vite/client`,
  // jamais exercé normalement — websocket de rechargement, overlay d'erreur) — pas du
  // code applicatif. Garde tout le reste (vues, composants, client API, styles).
  entryFilter: {
    '**/node_modules/**': false,
    '**/@vite/client': false,
    '**/**': true,
  },
  sourceFilter: {
    '**/node_modules/**': false,
    '**/@vite/client': false,
    '**/**': true,
  },
}

export default coverageOptions
