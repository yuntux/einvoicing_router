import { expect, test } from './fixtures'

test('shows a validation error when the SIREN checksum is invalid', async ({ page }) => {
  await page.goto('/companies')
  await page.getByTestId('siren-input').fill('111111111')
  await page.getByTestId('name-input').fill('Société Invalide')
  await page.getByTestId('submit-button').click()

  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByTestId('companies-list')).not.toContainText('Société Invalide')
})
