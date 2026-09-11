import { expect, test } from '@playwright/test'

test('creates an afnor_api target application and reveals OAuth credentials once', async ({
  page,
}) => {
  const unique = String(Date.now()).slice(-9)
  const companyName = `Société API ${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  await page.goto('/target-applications')
  await page.getByTestId('ta-name-input').fill(`Odoo ${unique}`)
  await page.getByTestId('ta-method-select').selectOption({ value: 'afnor_api' })
  await page.getByTestId('ta-company-select').selectOption({ label: companyName })
  await page.getByTestId('ta-submit-button').click()

  await expect(page.getByTestId('target-applications-list')).toContainText(`Odoo ${unique}`)
  await expect(page.getByTestId('ta-oauth-credentials')).toBeVisible()
  await expect(page.getByTestId('ta-oauth-client-id')).not.toBeEmpty()
  await expect(page.getByTestId('ta-oauth-client-secret')).not.toBeEmpty()
})
