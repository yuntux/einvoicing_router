import { expect, test } from '@playwright/test'

test('configures SuperPDP credentials for a company', async ({ page }) => {
  const unique = String(Date.now()).slice(-9)
  const companyName = `Société SuperPDP ${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()

  const row = page.getByTestId(new RegExp('company-row-\\d+')).filter({ hasText: companyName })
  await expect(row).toBeVisible()
  await expect(row).toContainText('Identifiants SuperPDP non configurés')

  // Identifiants uniques par exécution : oauth_applications.client_id est contraint
  // en unicité, et la base de dev n'est pas nécessairement réinitialisée entre deux
  // lancements manuels de la suite (contrairement à la CI, toujours à froid).
  const clientId = `sandbox-client-id-${unique}`

  await row.getByRole('button', { name: 'Configurer' }).click()
  await row.getByTestId('superpdp-client-id-input').fill(clientId)
  await row.getByTestId('superpdp-client-secret-input').fill('sandbox-client-secret')
  await row.getByTestId('superpdp-credentials-submit-button').click()

  await expect(row).toContainText(`Identifiants SuperPDP configurés (${clientId})`)
  await expect(row).not.toContainText('sandbox-client-secret')
})
