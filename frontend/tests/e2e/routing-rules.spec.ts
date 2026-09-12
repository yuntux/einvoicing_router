import { expect, test } from '@playwright/test'

test('creates a mail target application and a routing rule for a new emitter', async ({ page }) => {
  const unique = String(Date.now()).slice(-9)
  const companyName = `Société Routage ${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  await page.goto('/target-applications')
  await expect(page.getByRole('heading', { name: 'Applications cibles' })).toBeVisible()

  await page.getByTestId('ta-name-input').fill(`Spendesk ${unique}`)
  // routing method already defaults to "mail"
  await page.getByTestId('ta-company-select').selectOption({ label: companyName })
  await page.getByTestId('ta-to-input').fill('ap@spendesk.example')
  await page.getByTestId('ta-submit-button').click()
  await expect(page.getByTestId('target-applications-list')).toContainText(`Spendesk ${unique}`)

  await page.goto('/routing-rules')
  await expect(page.getByRole('heading', { name: 'Règles de routage' })).toBeVisible()

  await page.getByTestId('partner-siren-input').fill(unique)
  await page.getByTestId('partner-name-input').fill(`Fournisseur ${unique}`)
  await page.getByTestId('partner-submit-button').click()

  const table = page.getByTestId('routing-rules-list')
  await expect(table).toContainText(`Fournisseur ${unique}`)
  await expect(table).toContainText(`Spendesk ${unique}`)

  const columnIndex = await table
    .locator('thead th')
    .evaluateAll((ths, name) => ths.findIndex((th) => th.textContent?.includes(name)), `Spendesk ${unique}`)
  const row = table.locator('tbody tr').filter({ hasText: `Fournisseur ${unique}` })
  const checkbox = row.locator('td').nth(columnIndex).locator('input[type="checkbox"]')
  await checkbox.check()
  await expect(checkbox).toBeChecked()
})
