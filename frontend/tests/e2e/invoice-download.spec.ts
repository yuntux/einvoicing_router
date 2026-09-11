import { expect, test } from '@playwright/test'

test('downloads an invoice file and sees the last download timestamp', async ({ page }) => {
  const unique = String(Date.now()).slice(-9)
  const companyName = `Société DL ${unique}`
  const invoiceNumber = `F-${unique}`

  await page.goto('/companies')
  await page.getByTestId('siren-input').fill(unique)
  await page.getByTestId('name-input').fill(companyName)
  await page.getByTestId('submit-button').click()
  await expect(page.getByTestId('companies-list')).toContainText(companyName)

  await page.goto('/invoices')
  await page.getByTestId('sim-company-select').selectOption({ label: `${unique} — ${companyName}` })
  await page.getByTestId('sim-emitter-siren-input').fill(unique)
  await page.getByTestId('sim-invoice-number-input').fill(invoiceNumber)
  await page.getByTestId('sim-invoice-date-input').fill('2026-03-01')
  await page.getByTestId('sim-submit-button').click()

  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()

  await expect(page.getByTestId('invoice-last-download')).toContainText('jamais')

  const downloadPromise = page.waitForEvent('download')
  await page.getByTestId('invoice-download-link').click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toContain(invoiceNumber)

  // Re-sélectionne la facture pour récupérer la fiche à jour (jointure AuditLog).
  await page.getByTestId('filter-invoice-number').fill(invoiceNumber)
  await page.getByTestId('filter-submit-button').click()
  await page.getByTestId(`invoice-row-${invoiceNumber}`).click()

  await expect(page.getByTestId('invoice-last-download')).not.toContainText('jamais')
})
