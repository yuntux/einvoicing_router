import { expect, test } from './fixtures'
import { uniqueValidSiren } from './helpers'

test('creates a company and sees it listed', async ({ page }) => {
  await page.goto('/companies')

  await expect(page.getByRole('heading', { name: 'Entreprises gérées' })).toBeVisible()

  const siren = uniqueValidSiren()
  await page.getByTestId('siren-input').fill(siren)
  await page.getByTestId('name-input').fill('Acme Test SAS')
  await page.getByTestId('submit-button').click()

  await expect(page.getByTestId('companies-list')).toContainText(siren)
  await expect(page.getByTestId('companies-list')).toContainText('Acme Test SAS')
})
