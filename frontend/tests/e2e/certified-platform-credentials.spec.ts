import { expect, test } from './fixtures'
import { uniqueValidSiren } from './helpers'

test('configures SuperPDP credentials for a company', async ({ page }) => {
  const unique = uniqueValidSiren()
  const companyName = `Société SuperPDP ${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()

  const row = page.getByTestId(new RegExp('company-row-\\d+')).filter({ hasText: companyName })
  await expect(row).toBeVisible()
  await expect(row).toContainText('Non configurés')

  // Identifiants uniques par exécution : oauth_applications.client_id est contraint
  // en unicité, et la base de dev n'est pas nécessairement réinitialisée entre deux
  // lancements manuels de la suite (contrairement à la CI, toujours à froid).
  const clientId = `sandbox-client-id-${unique}`

  await row.getByRole('button', { name: 'Configurer' }).click()
  await row.getByTestId('certified-platform-client-id-input').fill(clientId)
  await row.getByTestId('certified-platform-client-secret-input').fill('sandbox-client-secret')
  await row.getByTestId('certified-platform-credentials-submit-button').click()

  await expect(page.getByTestId('certified-platform-credentials-test-success')).toContainText('Test de connexion OK')
  await expect(row).toContainText(`Configurés (${clientId})`)
  await expect(row).not.toContainText('sandbox-client-secret')
})
